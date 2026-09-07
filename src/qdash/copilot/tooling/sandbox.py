"""Subprocess-backed Python sandbox for AI-driven data analysis."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shutil
import signal
import sys
import sysconfig
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

WORKER_SCRIPT = Path(__file__).resolve().parent / "sandbox_worker.py"
WORKER_WALL_TIMEOUT_SECONDS = EXECUTION_TIMEOUT_SECONDS + WORKER_STARTUP_GRACE_SECONDS

# The OS-enforced security boundary. The worker only ever runs inside bubblewrap; if bwrap
# is missing the sandbox is fail-closed (see ``_bwrap_path`` / ``execute_python_analysis``).
BWRAP = "bwrap"


def _bwrap_path() -> str | None:
    """Return the bubblewrap executable path, or ``None`` if it is not installed."""
    return shutil.which(BWRAP)


def _read_only_binds() -> list[str]:
    """Read-only paths the worker needs to import the interpreter and curated libraries."""
    candidates = {
        sys.base_prefix,
        sys.prefix,
        sysconfig.get_paths()["stdlib"],
        sysconfig.get_paths()["purelib"],
        str(Path(sys.executable).resolve().parent.parent),
        str(WORKER_SCRIPT.parent),
        "/usr",
        "/lib",
        "/lib64",
        "/bin",
        "/sbin",
    }
    args: list[str] = []
    for path in sorted(p for p in candidates if p and Path(p).exists()):
        args += ["--ro-bind", path, path]
    return args


def _bwrap_argv(bwrap: str, workdir: str) -> list[str]:
    """Build the bubblewrap command that runs the worker in an isolated namespace."""
    return [
        bwrap,
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        *_read_only_binds(),
        "--bind",
        workdir,
        workdir,
        "--chdir",
        workdir,
        "--",
        sys.executable,
        str(WORKER_SCRIPT),
    ]


__all__ = ["SandboxChartSpec", "SandboxResult", "execute_python_analysis"]


def _error(message: str) -> SandboxResult:
    return {"output": None, "chart": None, "error": message}


def _worker_env(workdir: str) -> dict[str, str]:
    """Build the minimal environment for the worker process."""

    return {
        "PATH": "/usr/bin:/bin",
        "HOME": workdir,
        "TMPDIR": workdir,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "VECLIB_MAXIMUM_THREADS": "1",
    }


def _serialize_request(code: str, context_data: dict[str, Any]) -> bytes:
    return json.dumps(
        {"code": code, "context_data": context_data},
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


async def execute_python_analysis(
    code: str,
    context_data: dict[str, Any] | None = None,
) -> SandboxResult:
    """Execute Python analysis code in a disposable sandbox worker process."""
    validation_error = validate_code(code)
    if validation_error is not None:
        return _error(validation_error)

    bwrap = _bwrap_path()
    if bwrap is None:
        # Fail-closed: the OS boundary is mandatory, never fall back to running code
        # without isolation.
        logger.error("Python sandbox is disabled: bubblewrap (bwrap) is not installed")
        return _error(
            "Python sandbox is unavailable: the isolation runtime (bubblewrap) is not "
            "installed on the server."
        )

    try:
        request_bytes = await asyncio.to_thread(_serialize_request, code, context_data or {})
    except (TypeError, ValueError) as exc:
        return _error(f"Sandbox input is not JSON serializable: {exc}")

    if len(request_bytes) > MAX_WORKER_INPUT_BYTES:
        return _error(
            f"Sandbox input is too large ({len(request_bytes) / 1024 / 1024:.1f} MB, limit "
            f"{MAX_WORKER_INPUT_BYTES / 1024 / 1024:.0f} MB). Fetch fewer parameters, or use "
            "a smaller last_n or a qids subset, before running the analysis."
        )

    with tempfile.TemporaryDirectory(
        prefix="qdash-sandbox-", ignore_cleanup_errors=True
    ) as workdir:
        return await _run_worker(_bwrap_argv(bwrap, workdir), request_bytes, workdir)


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


_SIGNAL_HINTS = {
    "SIGXCPU": (
        " (the sandbox CPU budget was exhausted; the analysis is too CPU-heavy - reduce the "
        "data volume or vectorize the computation)"
    ),
    "SIGKILL": " (killed by the operating system, most likely out of memory)",
    "SIGSEGV": " (the worker crashed; this is a sandbox bug, not an error in the analysis code)",
}


def _exit_status_text(returncode: int | None) -> str:
    """Describe how the worker terminated."""
    if returncode is None:
        return "did not report an exit status"
    if returncode >= 0:
        return f"exited with code {returncode}"
    try:
        name = signal.Signals(-returncode).name
    except ValueError:
        return f"was killed by signal {-returncode}"
    return f"was killed by {name}{_SIGNAL_HINTS.get(name, '')}"


async def _run_worker(argv: list[str], request_bytes: bytes, workdir: str) -> SandboxResult:
    """Run the sandbox worker process (under bubblewrap) and decode its response."""
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=workdir,
        env=_worker_env(workdir),
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
        logger.info("Python sandbox worker cancelled; killing pid %d", process.pid)
        _kill_worker(process)
        raise

    stderr_text = stderr.decode("utf-8", errors="replace").strip()
    if stderr_text:
        logger.warning("Python sandbox worker stderr: %s", stderr_text[:MAX_OUTPUT_BYTES])

    returncode = process.returncode
    if returncode != 0:
        detail = f": {stderr_text[:1000]}" if stderr_text else ""
        status = _exit_status_text(returncode)
        if returncode is None or returncode < 0:
            logger.warning("Python sandbox worker pid %d %s", process.pid, status)
        return _error(f"Sandbox worker {status}{detail}")

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
