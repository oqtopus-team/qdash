from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import Any

import pytest

from qdash.copilot.agent_runtime.execution import execute_tool_executor, wrap_tool_executors
from qdash.copilot.tooling.sandbox import WORKER_SCRIPT, execute_python_analysis
from qdash.copilot.tooling.sandbox_core import EXECUTION_TIMEOUT_SECONDS, MAX_OUTPUT_BYTES

# The worker must stay a standalone script: importing it through the qdash package
# executes qdash.copilot.__init__ (litellm), which adds ~2.3s to every call.
MAX_STARTUP_OVERHEAD_SECONDS = 1.5


@pytest.mark.asyncio
async def test_execute_python_analysis_runs_python_code() -> None:
    result = await execute_python_analysis('print("hello")')

    assert result == {"output": "hello\n", "chart": None, "error": None}


@pytest.mark.asyncio
async def test_execute_python_analysis_exposes_context_data_as_data() -> None:
    result = await execute_python_analysis(
        'result = {"output": sum(data["values"])}',
        {"values": [1, 2, 3]},
    )

    assert result["output"] == "6"
    assert result["error"] is None


@pytest.mark.asyncio
async def test_execute_python_analysis_rejects_forbidden_ast_call() -> None:
    result = await execute_python_analysis('eval("1 + 1")')

    assert result["output"] is None
    assert result["chart"] is None
    assert result["error"] == "Call to 'eval' is not allowed"


@pytest.mark.asyncio
async def test_execute_python_analysis_rejects_unapproved_import() -> None:
    result = await execute_python_analysis("import os")

    assert result["output"] is None
    assert result["chart"] is None
    assert result["error"] == "Import of 'os' is not allowed"


@pytest.mark.asyncio
async def test_execute_python_analysis_rejects_syntax_error() -> None:
    result = await execute_python_analysis("result = (")

    assert result["output"] is None
    assert result["error"] is not None
    assert result["error"].startswith("SyntaxError:")


@pytest.mark.asyncio
async def test_execute_python_analysis_rejects_invalid_code_without_spawning_worker(
    monkeypatch,
) -> None:
    async def fail_create_subprocess_exec(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("worker must not be spawned for statically rejected code")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fail_create_subprocess_exec)

    assert (await execute_python_analysis('eval("1 + 1")'))[
        "error"
    ] == "Call to 'eval' is not allowed"
    assert (await execute_python_analysis("import os"))["error"] == "Import of 'os' is not allowed"


@pytest.mark.asyncio
async def test_worker_revalidates_code_independently() -> None:
    """The worker keeps its own validation layer even though the parent validates first."""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(WORKER_SCRIPT),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _stderr = await process.communicate(json.dumps({"code": "import os"}).encode())

    assert json.loads(stdout)["error"] == "Import of 'os' is not allowed"


@pytest.mark.asyncio
async def test_execute_python_analysis_kills_worker_on_timeout() -> None:
    result = await execute_python_analysis("while True:\n    pass")

    assert result["output"] is None
    assert result["chart"] is None
    assert result["error"] == f"Execution timed out after {EXECUTION_TIMEOUT_SECONDS} seconds"


@pytest.mark.asyncio
async def test_execute_python_analysis_returns_error_for_worker_crash(monkeypatch) -> None:
    async def fake_create_subprocess_exec(*_args: Any, **_kwargs: Any) -> Any:
        return _FakeProcess(returncode=2, stdout=b"", stderr=b"boom")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = await execute_python_analysis("print('unused')")

    assert result["output"] is None
    assert result["chart"] is None
    assert result["error"] == "Sandbox worker exited with code 2: boom"


@pytest.mark.asyncio
async def test_execute_python_analysis_returns_error_for_invalid_worker_json(monkeypatch) -> None:
    async def fake_create_subprocess_exec(*_args: Any, **_kwargs: Any) -> Any:
        return _FakeProcess(returncode=0, stdout=b"not json", stderr=b"")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = await execute_python_analysis("print('unused')")

    assert result["output"] is None
    assert result["chart"] is None
    assert result["error"] is not None
    assert result["error"].startswith("Invalid sandbox JSON response")


@pytest.mark.asyncio
async def test_execute_python_analysis_applies_output_size_limit() -> None:
    result = await execute_python_analysis(f'result = {{"output": "x" * {MAX_OUTPUT_BYTES + 1}}}')

    assert result["output"] is not None
    assert len(result["output"].encode("utf-8")) <= MAX_OUTPUT_BYTES + len(
        b"\n... (output truncated)"
    )
    assert result["output"].endswith("\n... (output truncated)")
    assert result["error"] is None


@pytest.mark.asyncio
async def test_execute_python_analysis_returns_plotly_chart() -> None:
    result = await execute_python_analysis(
        "import plotly.graph_objects as go\n"
        "result = {'output': 'chart ready', 'chart': go.Figure(data=[go.Scatter(y=[1, 2])])}"
    )

    assert result["output"] == "chart ready"
    assert isinstance(result["chart"], dict)
    assert "data" in result["chart"]
    assert result["error"] is None


@pytest.mark.asyncio
async def test_execute_python_analysis_does_not_block_event_loop() -> None:
    ticker_ran = asyncio.Event()

    async def ticker() -> None:
        await asyncio.sleep(0.1)
        ticker_ran.set()

    sandbox_task = asyncio.create_task(execute_python_analysis("while True:\n    pass"))
    ticker_task = asyncio.create_task(ticker())

    await asyncio.wait_for(ticker_task, timeout=1)
    result = await sandbox_task

    assert ticker_ran.is_set()
    assert result["error"] == f"Execution timed out after {EXECUTION_TIMEOUT_SECONDS} seconds"


def test_worker_script_exists() -> None:
    assert WORKER_SCRIPT.is_file()


@pytest.mark.asyncio
async def test_execute_python_analysis_starts_worker_without_qdash_imports() -> None:
    started = time.perf_counter()
    result = await execute_python_analysis('result = {"output": "ok"}')
    elapsed = time.perf_counter() - started

    assert result["error"] is None
    assert elapsed < MAX_STARTUP_OVERHEAD_SECONDS


@pytest.mark.asyncio
async def test_execute_python_analysis_reaps_worker_process() -> None:
    result = await execute_python_analysis('result = {"output": "done"}')

    assert result["error"] is None

    current_process = await asyncio.create_subprocess_exec(
        "pgrep",
        "-f",
        WORKER_SCRIPT.name,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _stderr = await current_process.communicate()
    worker_pids = [pid for pid in stdout.decode().splitlines() if pid]
    assert worker_pids == []


@pytest.mark.asyncio
async def test_execute_tool_executor_awaits_awaitable_result() -> None:
    async def async_executor(args: dict[str, Any]) -> dict[str, Any]:
        return {"value": args["value"]}

    result = await execute_tool_executor(async_executor, {"value": 42})

    assert result == {"value": 42}


@pytest.mark.asyncio
async def test_wrap_tool_executors_collects_chart_from_async_python_executor() -> None:
    wrapped, charts = wrap_tool_executors({}, {"values": [1, 2]})

    result = await execute_tool_executor(
        wrapped["execute_python_analysis"],
        {
            "code": (
                "result = {'output': len(data['values']), "
                "'chart': {'data': [{'y': data['values']}], 'layout': {}}}"
            )
        },
    )

    assert result["output"] == "2"
    assert result["chart"] is None
    assert charts == [{"data": [{"y": [1, 2]}], "layout": {}}]


class _FakeProcess:
    def __init__(self, *, returncode: int, stdout: bytes, stderr: bytes) -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self.killed = False

    async def communicate(self, _input: bytes) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr

    def kill(self) -> None:
        self.killed = True

    async def wait(self) -> int:
        return self.returncode
