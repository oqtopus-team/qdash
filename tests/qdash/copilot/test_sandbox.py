from __future__ import annotations

import asyncio
import json
import signal
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from qdash.copilot.agent_runtime.execution import execute_tool_executor, wrap_tool_executors
from qdash.copilot.tooling import sandbox
from qdash.copilot.tooling.sandbox import WORKER_SCRIPT, _worker_env, execute_python_analysis
from qdash.copilot.tooling.sandbox_core import (
    EXECUTION_TIMEOUT_SECONDS,
    MAX_OUTPUT_BYTES,
    MEMORY_LIMIT_BYTES,
)

if TYPE_CHECKING:
    from collections.abc import Callable

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
async def test_execute_python_analysis_allows_submodules_of_allowed_packages() -> None:
    """The module boundary must not break the whitelisted APIs the analysis code relies on."""
    result = await execute_python_analysis(
        "import numpy as np\n"
        "import plotly.express as px\n"
        "from plotly.subplots import make_subplots\n"
        "value = np.linalg.norm([3.0, 4.0])\n"
        "palette = len(px.colors.qualitative.Plotly)\n"
        "fig = make_subplots(rows=1, cols=1)\n"
        'result = {"output": f"{value}|{palette}", "chart": fig}'
    )

    assert result["error"] is None
    assert result["output"] == "5.0|10"
    assert result["chart"] is not None


@pytest.mark.asyncio
async def test_execute_python_analysis_accepts_multi_megabyte_context_data() -> None:
    """The data store accumulates per stored tool call; a few MB must not break analysis."""
    context_data = {
        f"param_{p}": {
            "qubits": [
                {
                    "qid": str(q),
                    "timeseries": [
                        {"value": 45.234567, "timestamp": "2026-01-01T12:00:00Z"} for _ in range(50)
                    ],
                }
                for q in range(144)
            ]
        }
        for p in range(6)
    }
    assert len(json.dumps(context_data).encode()) > 2 * 1024 * 1024

    result = await execute_python_analysis(
        'rows = [t["value"] for v in data.values() for q in v["qubits"] for t in q["timeseries"]]\n'
        'result = {"output": str(len(rows))}',
        context_data,
    )

    assert result["error"] is None
    assert result["output"] == str(6 * 144 * 50)


@pytest.mark.asyncio
async def test_execute_python_analysis_rejects_oversized_context_data(monkeypatch) -> None:
    monkeypatch.setattr(sandbox, "MAX_WORKER_INPUT_BYTES", 1024)

    result = await execute_python_analysis(
        'result = {"output": "ok"}', {"big": ["x" * 100 for _ in range(100)]}
    )

    assert result["output"] is None
    assert result["error"] is not None
    assert result["error"].startswith("Sandbox input is too large")
    assert "last_n" in result["error"]


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
async def test_execute_python_analysis_reports_signal_name_for_killed_worker(monkeypatch) -> None:
    """A signalled worker reports its signal: '-24' alone reads like an exit code, not SIGXCPU."""

    async def fake_create_subprocess_exec(*_args: Any, **_kwargs: Any) -> Any:
        return _FakeProcess(returncode=-signal.SIGXCPU, stdout=b"", stderr=b"")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = await execute_python_analysis("print('unused')")

    assert result["output"] is None
    assert result["error"] is not None
    assert "SIGXCPU" in result["error"]
    assert "CPU budget" in result["error"]
    assert "code -24" not in result["error"]


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


def test_worker_env_drops_parent_environment(monkeypatch) -> None:
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "super-secret")
    monkeypatch.setenv("PYTHONPATH", "/app:/app/qdash")

    env = _worker_env("/tmp/workdir")

    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert "PYTHONPATH" not in env
    assert env["HOME"] == "/tmp/workdir"
    assert env["TMPDIR"] == "/tmp/workdir"


def test_worker_env_pins_blas_thread_counts() -> None:
    """Unpinned BLAS reserves per-core buffers that overshoot RLIMIT_AS and end in SIGXCPU.

    Asserted on the env rather than on an observed thread count so the guard also holds on
    the few-core CI runners, where an unpinned worker still fits under the memory limit.
    """
    env = _worker_env("/tmp/workdir")

    for name in (
        "OPENBLAS_NUM_THREADS",
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        assert env[name] == "1", name


@pytest.mark.skipif(not Path("/proc/self/environ").exists(), reason="requires procfs")
@pytest.mark.asyncio
async def test_worker_does_not_leak_parent_environment(monkeypatch) -> None:
    """Allowed libraries can read /proc/self/environ, so the worker must not inherit secrets."""
    monkeypatch.setenv("QDASH_TEST_SECRET", "super-secret-value")

    result = await execute_python_analysis(
        "import pandas as pd\n"
        'env = pd.read_csv("/proc/self/environ", sep="\\x00", header=None, engine="python")\n'
        'result = {"output": str(env.values.tolist())}'
    )

    assert result["error"] is None
    assert result["output"] is not None
    assert "super-secret-value" not in result["output"]
    assert "PATH=/usr/bin:/bin" in result["output"]
    assert "OPENBLAS_NUM_THREADS=1" in result["output"]


@pytest.mark.asyncio
async def test_worker_cannot_write_files() -> None:
    result = await execute_python_analysis(
        "import pandas as pd\n"
        'pd.DataFrame({"a": list(range(100))}).to_csv("evil.csv")\n'
        'result = {"output": "wrote file"}'
    )

    assert result["output"] is None
    assert result["error"] is not None
    assert "File too large" in result["error"]


_TRACEBACK_ESCAPE_PREAMBLE = (
    "import json\n"
    '_bi = "__buil" + "tins__"\n'
    '_im = "__imp" + "ort__"\n'
    "try:\n"
    '    json.loads("{bad")\n'
    "except Exception as _e:\n"
    "    _tb = _e.__traceback__\n"
    "    while _tb.tb_next is not None:\n"
    "        _tb = _tb.tb_next\n"
    "    _b = _tb.tb_frame.f_globals[_bi]\n"
    "    _imp = _b[_im]\n"
    '    _ga = _b["getattr"]\n'
)


@pytest.mark.skipif(sandbox._bwrap_path() is None, reason="requires bubblewrap")
@pytest.mark.asyncio
async def test_traceback_escape_cannot_read_host_files(tmp_path: Path) -> None:
    """A traceback-recovered ``os`` cannot read a file outside the OS sandbox."""
    secret = tmp_path / "secret.txt"
    canary = "escape-canary-1251"
    secret.write_text(canary, encoding="utf-8")

    code = _TRACEBACK_ESCAPE_PREAMBLE + (
        '    _os = _imp("o" + "s")\n'
        f'    _fd = _ga(_os, "open")({str(secret)!r}, _ga(_os, "O_RDONLY"))\n'
        '    _blob = _ga(_os, "read")(_fd, 1024)\n'
        '    result = {"output": _blob.decode("utf-8", "ignore")}\n'
    )
    result = await execute_python_analysis(code)

    assert result["output"] is None
    assert canary not in (result["error"] or "")


@pytest.mark.asyncio
async def test_sandbox_is_fail_closed_without_bubblewrap(monkeypatch) -> None:
    """With no isolation runtime, code must be refused, never run unsandboxed."""
    monkeypatch.setattr(sandbox, "_bwrap_path", lambda: None)

    async def fail_create_subprocess_exec(*_args: Any, **_kwargs: Any) -> Any:
        msg = "worker must not be spawned without bubblewrap"
        raise AssertionError(msg)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fail_create_subprocess_exec)

    result = await execute_python_analysis('print("hello")')

    assert result["output"] is None
    assert result["error"] is not None
    assert "bubblewrap" in result["error"]


@pytest.mark.skipif(not Path("/proc/self/status").exists(), reason="requires procfs")
@pytest.mark.asyncio
async def test_worker_analysis_with_scipy_stays_single_threaded() -> None:
    """scipy analysis must run, and stay well inside RLIMIT_AS, whatever the host core count.

    Importing scipy used to fail outright on many-core hosts: OpenBLAS reserved a per-core
    buffer set that overshot RLIMIT_AS, then spun retrying the mmap until SIGXCPU. The peak
    address space is asserted as the canary for that failure mode, since a thread count is
    only conclusive on a machine with cores to spare.
    """
    result = await execute_python_analysis(
        "import numpy as np\n"
        "import pandas as pd\n"
        "import scipy.stats as st\n"
        "df = pd.DataFrame({'x': np.arange(200.0), 'y': np.arange(200.0) * 2})\n"
        "r = st.pearsonr(df['x'], df['y'])\n"
        "status = pd.read_csv('/proc/self/status', sep='\\x00', header=None, engine='python')\n"
        "lines = [x for x in status[0].tolist() if x.startswith(('Threads', 'VmPeak'))]\n"
        'result = {"output": f"{round(float(r[0]), 3)} | " + " ".join(lines)}'
    )

    assert result["error"] is None
    assert result["output"] is not None
    assert result["output"].startswith("1.0 |")
    threads = int(result["output"].split("Threads:")[1].split()[0])
    vm_peak_bytes = int(result["output"].split("VmPeak:")[1].split()[0]) * 1024
    assert threads <= 2, f"BLAS thread pinning is not in effect: {result['output']}"
    assert vm_peak_bytes < MEMORY_LIMIT_BYTES * 0.6, result["output"]


@pytest.mark.asyncio
async def test_execute_python_analysis_starts_worker_without_qdash_imports() -> None:
    started = time.perf_counter()
    result = await execute_python_analysis('result = {"output": "ok"}')
    elapsed = time.perf_counter() - started

    assert result["error"] is None
    assert elapsed < MAX_STARTUP_OVERHEAD_SECONDS


async def _worker_pids() -> set[str]:
    process = await asyncio.create_subprocess_exec(
        "pgrep",
        "-f",
        WORKER_SCRIPT.name,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _stderr = await process.communicate()
    return {pid for pid in stdout.decode().splitlines() if pid}


async def _wait_until(condition: Callable[[set[str]], bool], timeout: float = 5.0) -> set[str]:
    deadline = time.monotonic() + timeout
    pids = await _worker_pids()
    while not condition(pids) and time.monotonic() < deadline:
        await asyncio.sleep(0.05)
        pids = await _worker_pids()
    return pids


@pytest.mark.asyncio
async def test_execute_python_analysis_reaps_worker_process() -> None:
    before = await _worker_pids()

    result = await execute_python_analysis('result = {"output": "done"}')

    assert result["error"] is None
    remaining = await _wait_until(lambda pids: not (pids - before))
    assert not (remaining - before)


@pytest.mark.asyncio
async def test_execute_python_analysis_kills_worker_on_cancellation() -> None:
    """A disconnected caller must not leave the worker spinning until its own alarm fires."""
    task = asyncio.create_task(execute_python_analysis("while True:\n    pass"))
    running = await _wait_until(bool)
    assert running, "worker did not start"

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    remaining = await _wait_until(lambda pids: not (pids & running))
    assert not (remaining & running)


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
        self.pid = 424242
        self._stdout = stdout
        self._stderr = stderr
        self.killed = False

    async def communicate(self, _input: bytes) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr

    def kill(self) -> None:
        self.killed = True

    async def wait(self) -> int:
        return self.returncode
