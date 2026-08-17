"""Worker process entry point for Copilot Python sandbox execution.

This module is launched as a standalone script (``python <path>/sandbox_worker.py``)
rather than with ``python -m qdash.copilot.tooling.sandbox_worker``: importing it as
part of the ``qdash`` package would execute ``qdash.copilot.__init__``, which pulls in
litellm and costs ~2.3s of interpreter startup on every sandbox call. ``sandbox_core``
is therefore imported as a sibling module from this file's own directory.
"""

from __future__ import annotations

import json
import logging
import resource
import signal
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sandbox_core import (
    EXECUTION_TIMEOUT_SECONDS,
    MAX_WORKER_INPUT_BYTES,
    MAX_WORKER_OUTPUT_BYTES,
    MEMORY_LIMIT_BYTES,
    WORKER_STARTUP_GRACE_SECONDS,
    execute_python_analysis_in_process,
)

if TYPE_CHECKING:
    from qdash.copilot.tooling.sandbox_core import SandboxResult

logger = logging.getLogger(__name__)


def _error(message: str) -> SandboxResult:
    return {"output": None, "chart": None, "error": message}


def _apply_resource_limits() -> None:
    try:
        cpu_seconds = max(1, EXECUTION_TIMEOUT_SECONDS + WORKER_STARTUP_GRACE_SECONDS)
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
    except (OSError, ValueError) as exc:
        logger.warning("Failed to apply CPU limit: %s", exc)

    try:
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))
    except (OSError, ValueError) as exc:
        logger.warning("Failed to apply memory limit: %s", exc)

    if hasattr(signal, "SIGXFSZ"):
        try:
            signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
        except (OSError, ValueError) as exc:
            logger.warning("Failed to ignore SIGXFSZ: %s", exc)
    try:
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    except (OSError, ValueError) as exc:
        logger.warning("Failed to apply file size limit: %s", exc)


def _read_request() -> tuple[str | None, dict[str, Any] | None, str | None]:
    raw_input = sys.stdin.buffer.read(MAX_WORKER_INPUT_BYTES + 1)
    if len(raw_input) > MAX_WORKER_INPUT_BYTES:
        return None, None, "Sandbox input is too large"

    try:
        request = json.loads(raw_input.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, None, f"Invalid sandbox JSON input: {exc}"

    if not isinstance(request, dict):
        return None, None, "Sandbox input must be a JSON object"
    code = request.get("code")
    context_data = request.get("context_data", {})
    if not isinstance(code, str):
        return None, None, "Sandbox input field 'code' must be a string"
    if not isinstance(context_data, dict):
        return None, None, "Sandbox input field 'context_data' must be an object"
    return code, context_data, None


def _write_result(result: SandboxResult) -> int:
    encoded = json.dumps(result, ensure_ascii=False, default=str).encode("utf-8")
    if len(encoded) > MAX_WORKER_OUTPUT_BYTES:
        fallback = _error(f"Sandbox output is too large (limit {MAX_WORKER_OUTPUT_BYTES} bytes)")
        encoded = json.dumps(fallback, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()
    return 0


def main() -> int:
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    _apply_resource_limits()
    code, context_data, error = _read_request()
    if error is not None:
        return _write_result(_error(error))
    if code is None:
        return _write_result(_error("Sandbox input did not include code"))
    return _write_result(execute_python_analysis_in_process(code, context_data))


if __name__ == "__main__":
    raise SystemExit(main())
