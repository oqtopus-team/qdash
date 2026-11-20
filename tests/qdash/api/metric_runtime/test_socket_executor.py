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
from types import SimpleNamespace
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

ACCEPTED = {
    "type": "accepted",
    "v": 2,
    "job_id": "0123456789abcdef",
    "timeout_seconds": 5,
    "queue_seconds": 0,
}
OK_RESULT = {
    "type": "result",
    "ok": True,
    "result": {"metric": {"id": "m"}, "cells": []},
    "log": "hello\n",
    "log_truncated": False,
    "skipped_limits": ["RLIMIT_AS"],
}
TIME_LIMIT = {"type": "answer", "ok": False, "error": "Time limit exceeded"}
BUSY = {"type": "answer", "ok": False, "error": "Metric data access is busy; try again shortly"}


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
        self.timeouts: list[float] = []

    def handle(self, op: str, args: dict[str, Any], *, timeout: float) -> Any:
        self.calls.append((op, args))
        self.timeouts.append(timeout)
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
        "v": 2,
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
        "v": 2,
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
        "Metric script exceeded the 5 s time limit (METRIC_SCRIPT_TIMEOUT_SECONDS) and was stopped"
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
    # The slow answer finished past the time limit: its data is never sent.
    assert answers[0] == TIME_LIMIT
    assert answers[1] is None  # then the API closed the connection
    assert answers[2] is None


def test_socket_mode_does_not_use_local_slots(serve, monkeypatch):
    def no_local(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("local mode must not run")

    monkeypatch.setattr(executor, "_run_local_bounded", no_local)
    runner = serve(lambda r: r.send(ACCEPTED, OK_RESULT))
    evaluate(runner)
    runner.join()


# -- time limit of data requests (controlled clock) ------------------------------------


class FakeClock:
    """``time.monotonic`` for the executor module; only moves when a test moves it."""

    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def monotonic(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(executor, "time", SimpleNamespace(monotonic=fake.monotonic))
    return fake


def test_data_requests_get_the_time_left(serve, clock):
    """Each call's timeout is the time left until the job's limit, counted from `accepted`."""
    answers: list[dict[str, Any] | None] = []

    def play(runner: Runner) -> None:
        runner.send(ACCEPTED, {"type": "call", "op": "first", "args": {}})
        answers.append(runner.read())
        runner.send({"type": "call", "op": "second", "args": {}})
        answers.append(runner.read())
        runner.send(OK_RESULT)

    def first() -> int:
        clock.now += 1.5
        return 1

    runner = serve(play)
    broker = FakeBroker({"first": first, "second": 2})
    evaluate(runner, broker, timeout_seconds=5)
    runner.join()
    assert broker.timeouts == pytest.approx([5.0, 3.5])
    assert answers == [
        {"type": "answer", "ok": True, "data": 1},
        {"type": "answer", "ok": True, "data": 2},
    ]


def test_data_ready_after_the_time_limit_is_not_sent(serve, clock):
    answers: list[dict[str, Any] | None] = []

    def play(runner: Runner) -> None:
        runner.send(
            ACCEPTED,
            {"type": "call", "op": "slow", "args": {}},
            {"type": "call", "op": "late", "args": {}},
        )
        answers.append(runner.read())
        answers.append(runner.read())

    def slow() -> str:
        clock.now += 5.01  # the broker finishes just past the 5 s limit
        return "secret"

    runner = serve(play)
    broker = FakeBroker({"slow": slow, "late": "never"})
    with pytest.raises(WorkerFailure) as caught:
        evaluate(runner, broker, timeout_seconds=5)
    runner.join()
    assert caught.value.message == (
        "Metric script exceeded the 5 s time limit (METRIC_SCRIPT_TIMEOUT_SECONDS) and was stopped"
    )
    assert [op for op, _ in broker.calls] == ["slow"]
    assert answers == [TIME_LIMIT, None]


def test_answer_encoded_after_the_time_limit_is_not_sent(serve, clock, monkeypatch):
    answers: list[dict[str, Any] | None] = []
    encode = executor._encode_answer

    def slow_encode(answer: dict[str, Any], envelope: dict[str, Any]) -> bytes:
        if answer.get("ok"):
            clock.now += 10  # a huge answer takes past the limit to encode
        return encode(answer, envelope)

    def play(runner: Runner) -> None:
        runner.send(ACCEPTED, {"type": "call", "op": "big", "args": {}})
        answers.append(runner.read())
        answers.append(runner.read())

    monkeypatch.setattr(executor, "_encode_answer", slow_encode)
    runner = serve(play)
    with pytest.raises(WorkerFailure, match="time limit"):
        evaluate(runner, FakeBroker({"big": "secret"}), timeout_seconds=5)
    runner.join()
    assert answers == [TIME_LIMIT, None]


# -- data request slots ----------------------------------------------------------------


def test_busy_broker_slots_refuse_the_call_and_the_run_goes_on(serve, monkeypatch):
    monkeypatch.setattr(executor, "BROKER_WAIT_SECONDS", 0.05)
    answers: list[dict[str, Any] | None] = []

    def play(runner: Runner) -> None:
        runner.send(ACCEPTED, {"type": "call", "op": "latest", "args": {}})
        answers.append(runner.read())
        runner.send(OK_RESULT)

    slots = executor._broker_semaphore(1)
    assert slots.acquire(blocking=False)
    try:
        runner = serve(play)
        broker = FakeBroker({"latest": {"0": 1.0}})
        started = time.monotonic()
        outcome = evaluate(runner, broker, broker_concurrency=1)
        elapsed = time.monotonic() - started
        runner.join()
    finally:
        slots.release()
    assert answers == [BUSY]
    assert broker.calls == []
    assert outcome.result == OK_RESULT["result"]
    assert elapsed < 2

    # Once the slot is free again the same call is served.
    answers.clear()
    runner = serve(play)
    evaluate(runner, broker, broker_concurrency=1)
    runner.join()
    assert answers == [{"type": "answer", "ok": True, "data": {"0": 1.0}}]


def test_broker_slot_is_released_after_a_failure():
    slots = executor._broker_semaphore(1)
    broker = FakeBroker({"boom": RuntimeError("database down"), "ok": 7})
    deadline = time.monotonic() + 5
    failed = executor._answer(broker, {"op": "boom", "args": {}}, deadline=deadline, concurrency=1)
    assert failed == {"ok": False, "error": "database down"}
    assert slots.acquire(blocking=False)
    slots.release()
    served = executor._answer(broker, {"op": "ok", "args": {}}, deadline=deadline, concurrency=1)
    assert served == {"ok": True, "data": 7}


def test_broker_concurrency_from_environment(monkeypatch):
    monkeypatch.delenv("METRIC_BROKER_CONCURRENCY", raising=False)
    assert executor.load_settings().broker_concurrency == executor.DEFAULT_BROKER_CONCURRENCY == 4
    monkeypatch.setenv("METRIC_BROKER_CONCURRENCY", "8")
    assert executor.load_settings().broker_concurrency == 8
    monkeypatch.setenv("METRIC_BROKER_CONCURRENCY", "0")
    assert executor.load_settings().broker_concurrency == 1
    monkeypatch.setenv("METRIC_BROKER_CONCURRENCY", "bogus")
    assert executor.load_settings().broker_concurrency == 4


# -- local mode relay (no subprocess) --------------------------------------------------


def test_local_reply_passes_the_time_left(clock):
    broker = FakeBroker({"latest": {"0": 1.5}})
    reply = executor._local_reply(
        'CALL {"op": "latest", "args": {"kind": "qubit"}}', broker, clock.now + 4, 4
    )
    assert reply is not None and reply.endswith(b"\n")
    assert json.loads(reply) == {"ok": True, "data": {"0": 1.5}}
    assert broker.calls == [("latest", {"kind": "qubit"})]
    assert broker.timeouts == pytest.approx([4.0])


def test_local_reply_after_the_time_limit_serves_nothing(clock):
    broker = FakeBroker({"latest": {"0": 1.5}})
    assert executor._local_reply('CALL {"op": "latest", "args": {}}', broker, clock.now, 4) is None
    assert broker.calls == []


def test_local_reply_finished_past_the_time_limit_is_dropped(clock):
    def slow() -> str:
        clock.now += 3
        return "secret"

    broker = FakeBroker({"slow": slow})
    assert (
        executor._local_reply('CALL {"op": "slow", "args": {}}', broker, clock.now + 2, 4) is None
    )
    assert [op for op, _ in broker.calls] == ["slow"]


def test_expired_inflight_broker_keeps_its_slot_until_return(clock, monkeypatch):
    """A driver that returns late cannot accumulate overlapping background DB calls."""
    monkeypatch.setattr(executor, "BROKER_WAIT_SECONDS", 0.01)
    entered = threading.Event()
    release = threading.Event()
    results: list[bytes | None] = []

    def stalled() -> str:
        entered.set()
        assert release.wait(5)
        return "late data"

    broker = FakeBroker({"stalled": stalled, "next": 7})
    deadline = clock.now + 1
    worker = threading.Thread(
        target=lambda: results.append(
            executor._serve_call(broker, {"op": "stalled"}, deadline, 1, {})
        )
    )
    worker.start()
    try:
        assert entered.wait(5)
        clock.now += 2
        answer = executor._serve_call(broker, {"op": "next"}, clock.now + 5, 1, {})
        assert answer is not None
        assert json.loads(answer) == executor.BUSY_ANSWER
        assert [op for op, _ in broker.calls] == ["stalled"]
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive()
    assert results == [None]
    answer = executor._serve_call(broker, {"op": "next"}, clock.now + 5, 1, {})
    assert answer is not None
    assert json.loads(answer) == {"ok": True, "data": 7}


@pytest.mark.parametrize(
    "fields",
    [
        {"v": 1},
        {"v": True},
        {"timeout_seconds": None},
        {"timeout_seconds": True},
        {"timeout_seconds": float("nan")},
        {"timeout_seconds": float("inf")},
        {"timeout_seconds": -1},
        {"timeout_seconds": 0},
        {"queue_seconds": None},
        {"queue_seconds": True},
        {"queue_seconds": -1},
        {"queue_seconds": float("nan")},
        {"queue_seconds": 1000},
    ],
)
def test_invalid_acceptance_limits_fail_closed(serve, fields):
    runner = serve(lambda r: r.send({**ACCEPTED, **fields}, OK_RESULT))
    with pytest.raises(WorkerFailure, match="malformed acceptance"):
        evaluate(runner)
    runner.join()


def test_old_acceptance_without_limits_fails_closed(serve):
    runner = serve(lambda r: r.send({"type": "accepted", "job_id": "old"}, OK_RESULT))
    with pytest.raises(WorkerFailure, match="malformed acceptance"):
        evaluate(runner)
    runner.join()


@pytest.mark.parametrize("queue,delay,expected", [(0, 0.4, 0.6), (2, 2.4, 0.6)])
def test_adopted_budget_deducts_transport_but_not_queue(serve, clock, queue, delay, expected):
    def play(runner):
        clock.now += delay
        runner.send(
            {**ACCEPTED, "timeout_seconds": 1, "queue_seconds": queue},
            {"type": "call", "op": "history", "args": {}},
        )
        runner.read()
        runner.send(OK_RESULT)

    runner = serve(play)
    broker = FakeBroker()
    evaluate(runner, broker, timeout_seconds=3)
    runner.join()
    assert broker.timeouts == pytest.approx([expected])


def test_delayed_acceptance_cannot_restart_expired_data_budget(serve, clock):
    answers = []

    def play(runner):
        clock.now += 1.1
        runner.send(
            {**ACCEPTED, "timeout_seconds": 1}, {"type": "call", "op": "history", "args": {}}
        )
        answers.append(runner.read())

    runner = serve(play)
    broker = FakeBroker()
    with pytest.raises(WorkerFailure, match="1 s time limit"):
        evaluate(runner, broker, timeout_seconds=3)
    runner.join()
    assert broker.calls == []
    assert answers == [TIME_LIMIT]
