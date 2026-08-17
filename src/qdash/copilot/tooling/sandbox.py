"""Subprocess-backed Python sandbox for AI-driven data analysis."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import signal
import sys
import tempfile
from pathlib import Path
from typing import Any

from qdash.copilot.tooling.sandbox_core import (
    EXECUTION_TIMEOUT_SECONDS,
    MAX_OUTPUT_BYTES,
    MAX_WORKER_INPUT_BYTES,
    MAX_WORKER_OUTPUT_BYTES,
    WORKER_STARTUP_GRACE_SECONDS,
    SandboxChartSpec,
    SandboxResult,
    validate_code,
)

logger = logging.getLogger(__name__)

# Run the worker as a standalone script, not as ``-m qdash.copilot.tooling.sandbox_worker``:
# importing it through the package would execute ``qdash.copilot.__init__`` (litellm) and
# add ~2.3s to every sandbox call, which used to eat the whole timeout budget.
WORKER_SCRIPT = Path(__file__).resolve().parent / "sandbox_worker.py"
WORKER_WALL_TIMEOUT_SECONDS = EXECUTION_TIMEOUT_SECONDS + WORKER_STARTUP_GRACE_SECONDS

__all__ = ["SandboxChartSpec", "SandboxResult", "execute_python_analysis"]


def _error(message: str) -> SandboxResult:
    return {"output": None, "chart": None, "error": message}


def _worker_env(workdir: str) -> dict[str, str]:
    """Build the minimal environment for the worker process.

    The API process holds database and cloud credentials in its environment, and sandboxed
    code can read ``/proc/self/environ`` through allowed libraries (``pandas.read_csv``
    and friends), so the worker inherits nothing from the parent. Interpreter and package
    resolution come from ``sys.executable``, not from ``PYTHONPATH``.
    """
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": workdir,
        "TMPDIR": workdir,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        # Writes are blocked by RLIMIT_FSIZE; skip bytecode writes rather than fail them.
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    }


async def execute_python_analysis(
    code: str,
    context_data: dict[str, Any] | None = None,
) -> SandboxResult:
    """Execute Python analysis code in a disposable sandbox worker process."""
    # Reject statically-detectable violations here: validation is pure, and returning
    # early avoids serializing the data store and spawning a process the code can never use.
    validation_error = validate_code(code)
    if validation_error is not None:
        return _error(validation_error)

    try:
        request_bytes = json.dumps(
            {"code": code, "context_data": context_data or {}},
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        return _error(f"Sandbox input is not JSON serializable: {exc}")

    if len(request_bytes) > MAX_WORKER_INPUT_BYTES:
        return _error(f"Sandbox input is too large (limit {MAX_WORKER_INPUT_BYTES} bytes)")

    # A throwaway directory per call: it is the worker's cwd, HOME and TMPDIR, so relative
    # paths and library scratch files never resolve into the API process's own directories.
    with tempfile.TemporaryDirectory(
        prefix="qdash-sandbox-", ignore_cleanup_errors=True
    ) as workdir:
        return await _run_worker(request_bytes, workdir)


def _kill_worker(process: asyncio.subprocess.Process) -> None:
    """Kill the worker and anything it spawned.

    The worker leads its own session (``start_new_session=True``), so its pid doubles as a
    process group id and one ``killpg`` covers descendants too.
    """
    if process.returncode is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError) as exc:
        logger.debug(
            "killpg on sandbox worker %d failed (%s); killing the process", process.pid, exc
        )
        with contextlib.suppress(ProcessLookupError):
            process.kill()


async def _run_worker(request_bytes: bytes, workdir: str) -> SandboxResult:
    """Run the sandbox worker process and decode its response."""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(WORKER_SCRIPT),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=workdir,
        env=_worker_env(workdir),
        # Detach from the API process group so terminal/process-group signals are not
        # delivered to sandboxed code, and the worker can be signalled independently.
        start_new_session=True,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(request_bytes),
            timeout=WORKER_WALL_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        _kill_worker(process)
        await process.wait()
        logger.warning(
            "Python sandbox worker exceeded the %ds wall-clock budget (execution timeout %ds "
            "+ %ds startup grace)",
            WORKER_WALL_TIMEOUT_SECONDS,
            EXECUTION_TIMEOUT_SECONDS,
            WORKER_STARTUP_GRACE_SECONDS,
        )
        return _error(f"Execution timed out after {EXECUTION_TIMEOUT_SECONDS} seconds")
    except asyncio.CancelledError:
        # The caller went away (e.g. the SSE client disconnected). Without this the worker
        # keeps burning CPU until its own alarm fires. Kill without awaiting: the event loop
        # reaps the child, and awaiting while cancelled is not guaranteed to resume.
        logger.info("Python sandbox worker cancelled; killing pid %d", process.pid)
        _kill_worker(process)
        raise

    stderr_text = stderr.decode("utf-8", errors="replace").strip()
    if stderr_text:
        logger.warning("Python sandbox worker stderr: %s", stderr_text[:MAX_OUTPUT_BYTES])

    if process.returncode != 0:
        detail = f": {stderr_text[:1000]}" if stderr_text else ""
        return _error(f"Sandbox worker exited with code {process.returncode}{detail}")

    if len(stdout) > MAX_WORKER_OUTPUT_BYTES:
        return _error(f"Sandbox response is too large (limit {MAX_WORKER_OUTPUT_BYTES} bytes)")

    try:
        result = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _error(f"Invalid sandbox JSON response: {exc}")

    if not isinstance(result, dict):
        return _error("Invalid sandbox response: expected a JSON object")
    return {
        "output": result.get("output") if isinstance(result.get("output"), str) else None,
        "chart": result.get("chart"),
        "error": result.get("error") if isinstance(result.get("error"), str) else None,
    }
