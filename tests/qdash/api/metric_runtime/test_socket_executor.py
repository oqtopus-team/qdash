"""Socket-mode executor tests against a scripted fake metric runner.

The fake serves one Unix socket connection the way ``agent-runtime/metric-runner/runner.ts``
does: it reads the request line, then replays a per-test script of lines to send and
answers to read. No worker process runs.
"""

from __future__ import annotations

import json
import shutil
import socket
import tempfile
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from qdash.api.metric_runtime import executor
from qdash.api.metric_runtime.executor import (
    QueueFullError,
    RunnerUnavailableError,
    RuntimeSettings,
    ScriptFailure,
    WorkerFailure,
    WorkerOutcome,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

ACCEPTED = {"type": "accepted", "job_id": "0123456789abcdef"}
OK_RESULT = {
    "type": "result",
    "ok": True,
    "result": {"metric": {"id": "m"}, "cells": []},
    "log": "hello\n",
    "log_truncated": False,
    "skipped_limits": ["RLIMIT_AS"],
}


class Runner:
    """A fake runner connection: ``play(conn)`` drives it after the request line."""

    def __init__(self, conn: socket.socket) -> None:
        self.conn = conn
        self.file = conn.makefile("rb")

    def send(self, *messages: dict[str, Any] | bytes) -> None:
        data = b"".join(
            m if isinstance(m, bytes) else json.dumps(m).encode() + b"\n" for m in messages
        )
        self.conn.sendall(data)

    def read(self) -> dict[str, Any] | None:
        line = self.file.readline()
        if not line:
            return None
        message: dict[str, Any] = json.loads(line)
        return message

    def closed_by_client(self, timeout: float = 5) -> bool:
        """True once the API closed its end (EOF on read)."""
        self.conn.settimeout(timeout)
        try:
            return self.file.readline() == b""
        except OSError:
            return True


class FakeRunner:
    def __init__(self, path: str, play: Callable[[Runner], None]) -> None:
        self.path = path
        self.play = play
        self.request: dict[str, Any] | None = None
        self.error: BaseException | None = None
        self.closed_by_client = False
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(path)
        self.server.listen(1)
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self) -> None:
        try:
            conn, _ = self.server.accept()
            with conn:
                runner = Runner(conn)
                self.request = runner.read()
                self.play(runner)
        except BaseException as exc:  # surfaced by join()
            self.error = exc

    def join(self) -> None:
        self.thread.join(timeout=10)
        self.server.close()
        assert not self.thread.is_alive(), "fake runner did not finish"
        if self.error is not None:
            raise self.error


class FakeBroker:
    def __init__(self, answers: dict[str, Any] | None = None) -> None:
        self.answers = answers or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def handle(self, op: str, args: dict[str, Any]) -> Any:
        self.calls.append((op, args))
        answer = self.answers.get(op)
        if isinstance(answer, BaseException):
            raise answer
        if callable(answer):
            return answer()
        return answer


@pytest.fixture
def socket_dir() -> Iterator[Path]:
    # Short path: AF_UNIX paths are limited to ~104 bytes on macOS, and pytest's tmp_path
    # there is longer.
    path = Path(tempfile.mkdtemp(prefix="qdmr-", dir="/tmp"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def serve(socket_dir: Path) -> Iterator[Callable[[Callable[[Runner], None]], FakeRunner]]:
    runners: list[FakeRunner] = []

    def start(play: Callable[[Runner], None]) -> FakeRunner:
        runner = FakeRunner(str(socket_dir / f"m{len(runners)}.sock"), play)
        runners.append(runner)
        return runner

    yield start
    for runner in runners:
        runner.server.close()


def settings_for(runner: FakeRunner, **overrides: Any) -> RuntimeSettings:
    return RuntimeSettings(
        **{"mode": "socket", "socket_path": runner.path, "timeout_seconds": 5, **overrides}
    )


def evaluate(runner: FakeRunner, broker: FakeBroker | None = None, **overrides: Any) -> Any:
    return executor.evaluate(
        source="SOURCE",
        metric_id="m",
        chip_id="chip-1",
        start="2026-11-01T00:00:00+00:00",
        end="2026-11-20T00:00:00+00:00",
        params={"factor": 2.0},
        broker=broker or FakeBroker(),
        settings=settings_for(runner, **overrides),
    )


def test_call_relay_and_result(serve):
    answers: list[dict[str, Any] | None] = []

    def play(runner: Runner) -> None:
        runner.send(ACCEPTED, {"type": "call", "op": "topology", "args": {"chip": "x"}})
        answers.append(runner.read())
        runner.send({"type": "call", "op": "latest", "args": {"metric": "t1"}})
        answers.append(runner.read())
        runner.send(OK_RESULT)

    runner = serve(play)
    broker = FakeBroker({"topology": {"qubits": [0, 1]}, "latest": {"0": 1.5}})
    outcome = evaluate(runner, broker, memory_mb=512)
    runner.join()

    assert isinstance(outcome, WorkerOutcome)
    assert outcome.result == {"metric": {"id": "m"}, "cells": []}
    assert outcome.log == "hello\n"
    assert outcome.skipped_limits == ["RLIMIT_AS"]
    assert broker.calls == [("topology", {"chip": "x"}), ("latest", {"metric": "t1"})]
    assert answers == [
        {"type": "answer", "ok": True, "data": {"qubits": [0, 1]}},
        {"type": "answer", "ok": True, "data": {"0": 1.5}},
    ]
    assert runner.request == {
        "v": 1,
        "mode": "evaluate",
        "source": "SOURCE",
        "metric_id": "m",
        "chip_id": "chip-1",
        "start": "2026-11-01T00:00:00+00:00",
        "end": "2026-11-20T00:00:00+00:00",
        "params": {"factor": 2.0},
        "memory_mb": 512,
        "timeout_seconds": 5,
    }


def test_catalog_request_line(serve):
    runner = serve(lambda r: r.send(ACCEPTED, {**OK_RESULT, "result": {"metrics": []}}))
    outcome = executor.catalog("SOURCE", settings_for(runner))
    runner.join()
    assert outcome.result == {"metrics": []}
    assert runner.request == {
        "v": 1,
        "mode": "catalog",
        "source": "SOURCE",
        "memory_mb": executor.DEFAULT_MEMORY_MB,
        "timeout_seconds": 5,
    }


def test_catalog_answers_calls_without_data_access(serve):
    answers: list[dict[str, Any] | None] = []

    def play(runner: Runner) -> None:
        runner.send(ACCEPTED, {"type": "call", "op": "topology", "args": {}})
        answers.append(runner.read())
        runner.send(OK_RESULT)

    runner = serve(play)
    executor.catalog("SOURCE", settings_for(runner))
    runner.join()
    assert answers[0] == {
        "type": "answer",
        "ok": False,
        "error": "Data access is not available while validating a script",
    }


def test_broker_exception_becomes_error_answer(serve):
    answers: list[dict[str, Any] | None] = []

    def play(runner: Runner) -> None:
        runner.send(ACCEPTED, {"type": "call", "op": "history", "args": {"metric": "x"}})
        answers.append(runner.read())
        runner.send({"type": "call", "op": "latest", "args": {}})
        answers.append(runner.read())
        runner.send(OK_RESULT)

    runner = serve(play)
    broker = FakeBroker({"history": ValueError("Unknown metric 'x'"), "latest": float("nan")})
    evaluate(runner, broker)
    runner.join()
    assert answers == [
        {"type": "answer", "ok": False, "error": "Unknown metric 'x'"},
        {"type": "answer", "ok": False, "error": "Non-finite broker data"},
    ]


def test_script_failure_result(serve):
    failure = {
        "type": "result",
        "ok": False,
        "error": "Metric 'm' raised ZeroDivisionError",
        "diagnostics": [{"message": "division by zero", "line": 7}, "junk"],
        "log": "partial output\n",
    }
    runner = serve(lambda r: r.send(ACCEPTED, failure))
    with pytest.raises(ScriptFailure, match="ZeroDivisionError") as caught:
        evaluate(runner)
    runner.join()
    assert caught.value.diagnostics == [{"message": "division by zero", "line": 7}]
    assert caught.value.log == "partial output\n"


def test_queue_full(serve):
    runner = serve(
        lambda r: r.send({"type": "error", "code": "queue_full", "message": "Queue is full"})
    )
    with pytest.raises(QueueFullError, match="queue is full"):
        evaluate(runner)
    runner.join()


def test_invalid_request(serve):
    runner = serve(
        lambda r: r.send(
            {"type": "error", "code": "invalid_request", "message": "Unknown request field: x"}
        )
    )
    with pytest.raises(WorkerFailure, match="refused the request: Unknown request field"):
        evaluate(runner)
    runner.join()


def failed(code: str, message: str = "", stderr_tail: str = "") -> dict[str, Any]:
    return {
        "type": "failed",
        "code": code,
        "message": message,
        "exit_code": None,
        "signal": "SIGKILL" if code == "timeout" else None,
        "stderr_tail": stderr_tail,
    }


def test_failed_timeout_keeps_the_time_limit_wording(serve):
    runner = serve(lambda r: r.send(ACCEPTED, failed("timeout", "exceeded the 5 s time limit")))
    with pytest.raises(WorkerFailure) as caught:
        evaluate(runner, timeout_seconds=7.5)
    runner.join()
    assert caught.value.message == (
        "Metric script exceeded the 7.5 s time limit (METRIC_SCRIPT_TIMEOUT_SECONDS) "
        "and was stopped"
    )


def test_failed_output_limit(serve):
    runner = serve(lambda r: r.send(ACCEPTED, failed("output_limit", "output exceeded 8 MiB")))
    with pytest.raises(WorkerFailure) as caught:
        evaluate(runner)
    runner.join()
    assert caught.value.message == "Metric script output exceeded 8 MiB and was stopped"


def test_failed_crash_includes_the_stderr_tail(serve):
    crash = failed(
        "crash",
        "The metric script worker exited (1) without a result",
        stderr_tail="Traceback (most recent call last):\n  ...\nMemoryError: out of memory\n",
    )
    runner = serve(lambda r: r.send(ACCEPTED, crash))
    with pytest.raises(WorkerFailure) as caught:
        evaluate(runner)
    runner.join()
    assert caught.value.message == (
        "The metric script worker exited (1) without a result: MemoryError: out of memory"
    )


def test_failed_runner_error_is_an_unavailable_runner(serve):
    """A runner that cannot start the worker is an infrastructure fault (503), not a script result."""
    runner = serve(lambda r: r.send(ACCEPTED, failed("runner_error", "could not start the worker")))
    with pytest.raises(RunnerUnavailableError) as caught:
        evaluate(runner)
    runner.join()
    assert caught.value.message.startswith("could not start the worker")


@pytest.mark.parametrize(
    "line",
    [
        b"not json\n",
        b"[1, 2]\n",
        b'{"no": "type"}\n',
        b'{"type": "bogus"}\n',
        b'{"type": "accepted", "job_id": "again"}\n',
        b"\xff\xfe\n",
    ],
)
def test_malformed_or_unexpected_line(serve, line):
    runner = serve(lambda r: r.send(ACCEPTED, line))
    with pytest.raises(WorkerFailure, match=r"malformed|unexpected"):
        evaluate(runner)
    runner.join()


def test_unexpected_first_line(serve):
    runner = serve(lambda r: r.send({"type": "call", "op": "topology", "args": {}}))
    with pytest.raises(WorkerFailure, match="unexpected 'call'"):
        evaluate(runner)
    runner.join()


def test_oversized_message(serve):
    big = {"type": "call", "op": "x" * (executor.MESSAGE_LIMIT_BYTES + 10), "args": {}}
    runner = serve(lambda r: r.send(ACCEPTED, big))
    with pytest.raises(WorkerFailure, match="oversized"):
        evaluate(runner)
    runner.join()


def test_close_after_acceptance_is_unavailable(serve):
    """The runner stopped mid-job (crash or shutdown): an infrastructure fault, not a result."""
    runner = serve(lambda r: r.send(ACCEPTED))
    with pytest.raises(RunnerUnavailableError, match="stopped before the job finished"):
        evaluate(runner)
    runner.join()


def test_close_before_acceptance_is_unavailable(serve):
    runner = serve(lambda r: None)
    with pytest.raises(RunnerUnavailableError):
        evaluate(runner)
    runner.join()


def test_missing_socket_is_unavailable(socket_dir):
    settings = RuntimeSettings(mode="socket", socket_path=str(socket_dir / "missing.sock"))
    with pytest.raises(RunnerUnavailableError, match="not available"):
        executor.catalog("x = 1\n", settings)


def test_refused_connection_is_unavailable(socket_dir):
    # A socket file nobody listens on (the runner died without removing it).
    path = str(socket_dir / "stale.sock")
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stale.bind(path)
    stale.close()
    settings = RuntimeSettings(mode="socket", socket_path=path)
    with pytest.raises(RunnerUnavailableError, match="not available"):
        executor.catalog("x = 1\n", settings)


def test_non_finite_params_fail_before_connecting(socket_dir):
    settings = RuntimeSettings(mode="socket", socket_path=str(socket_dir / "missing.sock"))
    with pytest.raises(WorkerFailure, match="finite"):
        executor.evaluate(
            source="SOURCE",
            metric_id="m",
            chip_id="c",
            start="s",
            end="e",
            params={"factor": float("inf")},
            broker=FakeBroker(),
            settings=settings,
        )


def test_deadline_closes_a_silent_runner(serve, monkeypatch):
    monkeypatch.setattr(executor, "DEADLINE_GRACE_SECONDS", 0.2)
    observed: list[bool] = []

    def play(runner: Runner) -> None:
        runner.send(ACCEPTED)
        # Silent: the API must give up and close the connection (the cancel signal).
        observed.append(runner.closed_by_client(timeout=5))

    runner = serve(play)
    started = time.monotonic()
    with pytest.raises(WorkerFailure, match="time limit"):
        evaluate(runner, timeout_seconds=0.3)
    elapsed = time.monotonic() - started
    runner.join()
    assert observed == [True]
    assert elapsed < 3


def test_call_after_the_deadline_is_refused(serve, monkeypatch):
    monkeypatch.setattr(executor, "DEADLINE_GRACE_SECONDS", 0.1)
    answers: list[dict[str, Any] | None] = []

    def play(runner: Runner) -> None:
        # Both calls arrive together; the first broker answer takes past the deadline.
        runner.send(
            ACCEPTED,
            {"type": "call", "op": "slow", "args": {}},
            {"type": "call", "op": "late", "args": {}},
        )
        answers.append(runner.read())
        answers.append(runner.read())
        answers.append(runner.read())

    def slow() -> str:
        time.sleep(0.5)
        return "done"

    runner = serve(play)
    broker = FakeBroker({"slow": slow, "late": "never"})
    with pytest.raises(WorkerFailure, match="time limit"):
        evaluate(runner, broker, timeout_seconds=0.2)
    runner.join()
    assert [op for op, _ in broker.calls] == ["slow"]
    assert answers[0] == {"type": "answer", "ok": True, "data": "done"}
    assert answers[1] == {"type": "answer", "ok": False, "error": "Time limit exceeded"}
    assert answers[2] is None  # then the API closed the connection


def test_socket_mode_does_not_use_local_slots(serve, monkeypatch):
    def no_local(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("local mode must not run")

    monkeypatch.setattr(executor, "_run_local_bounded", no_local)
    runner = serve(lambda r: r.send(ACCEPTED, OK_RESULT))
    evaluate(runner)
    runner.join()
