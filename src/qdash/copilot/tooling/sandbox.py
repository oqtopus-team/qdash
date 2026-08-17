"""Subprocess-backed Python sandbox for AI-driven data analysis."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

from qdash.copilot.tooling.sandbox_core import (
    EXECUTION_TIMEOUT_SECONDS,
    MAX_OUTPUT_BYTES,
    MAX_WORKER_INPUT_BYTES,
    MAX_WORKER_OUTPUT_BYTES,
    SandboxChartSpec,
    SandboxResult,
)

logger = logging.getLogger(__name__)

__all__ = ["SandboxChartSpec", "SandboxResult", "execute_python_analysis"]


def _error(message: str) -> SandboxResult:
    return {"output": None, "chart": None, "error": message}


async def execute_python_analysis(
    code: str,
    context_data: dict[str, Any] | None = None,
) -> SandboxResult:
    """Execute Python analysis code in a disposable sandbox worker process."""
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

    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "qdash.copilot.tooling.sandbox_worker",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(request_bytes),
            timeout=EXECUTION_TIMEOUT_SECONDS + 1,
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        return _error(f"Execution timed out after {EXECUTION_TIMEOUT_SECONDS} seconds")

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
