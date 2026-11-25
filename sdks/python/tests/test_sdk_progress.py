"""The progress display of the run handles' ``wait``: targets, deduplication and endings."""

from __future__ import annotations

import io
import sys
import types
from typing import Any

import httpx
import pytest
import test_sdk_calibration_session as sessions
import test_sdk_tasks as tasks
import test_sdk_workflows as workflows
from test_sdk_session import CHIP, Server, execute_body, pipeline

from qdash.calibration import CalibrationRunError, TaskCall
from qdash.sdk import CalibrationSession, QDash, QDashAuthError

EXEC_PATH = ("GET", "/executions/exec-1")
PIPELINE_EXECUTE = ("POST", "/calibration-pipelines/execute")


def step(
    index: int,
    status: str,
    *,
    total: int | None = None,
    finished: int | None = None,
    failed: int | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"index": index, "name": f"s{index}", "status": status}
    if total is not None:
        body.update(task_total=total, task_finished=finished or 0, task_failed=failed or 0)
    return body


def pipeline_detail(
    run_status: str, steps: list[dict[str, Any]], *, execution_status: str = "running"
) -> dict[str, Any]:
    return {
        "name": "coherence",
        "status": execution_status,
        "task": [],
        "note": {},
        "pipeline": {
            "name": "coherence",
            "flow_run_id": "run-1",
            "root_execution_id": "exec-1",
            "status": run_status,
            "steps": steps,
        },
    }


def ok(body: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json=body)


def timed(qdash: QDash) -> list[float]:
    """Drive the session's polling by a fake clock that each sleep advances."""
    now = [0.0]
    executions = qdash._executions

    def sleep(seconds: float) -> None:
        now[0] += seconds

    executions._clock = lambda: now[0]
    executions._sleep = sleep
    return now


def pipeline_server(*details: dict[str, Any]) -> Server:
    return Server(
        {
            PIPELINE_EXECUTE: [httpx.Response(202, json=execute_body())],
            EXEC_PATH: [ok(d) for d in details],
        }
    )


class TtyStream(io.StringIO):
    def isatty(self) -> bool:
        return True


class BrokenStream(io.StringIO):
    def write(self, text: str) -> int:
        raise OSError("stderr closed")

    def isatty(self) -> bool:
        return False


class FakeHandle:
    def __init__(self, log: list[tuple[str, Any]]) -> None:
        self.log = log

    def update(self, bundle: Any, **kwargs: Any) -> None:
        self.log.append(("update", bundle["text/plain"]))


@pytest.fixture
def notebook(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any]]:
    """A fake Jupyter kernel: IPython is imported and its shell has a kernel."""
    log: list[tuple[str, Any]] = []

    def display(bundle: Any, **kwargs: Any) -> FakeHandle:
        assert kwargs == {"raw": True, "display_id": True}
        log.append(("display", bundle["text/plain"]))
        return FakeHandle(log)

    def clear_output(*args: Any, **kwargs: Any) -> None:  # pragma: no cover - must not run
        log.append(("clear_output", None))

    shell = types.SimpleNamespace(kernel=object())
    ipython = types.ModuleType("IPython")
    ipython.get_ipython = lambda: shell  # type: ignore[attr-defined]
    display_module = types.ModuleType("IPython.display")
    display_module.display = display  # type: ignore[attr-defined]
    display_module.clear_output = clear_output  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "IPython", ipython)
    monkeypatch.setitem(sys.modules, "IPython.display", display_module)
    return log


RUNNING_STEPS = [
    pipeline_detail("running", [step(1, "running", total=4, finished=1), step(2, "pending")]),
    # Elapsed time alone changed: nothing new is written on redirected stderr.
    pipeline_detail("running", [step(1, "running", total=4, finished=1), step(2, "pending")]),
    pipeline_detail(
        "running",
        [step(1, "completed", total=4, finished=4, failed=1), step(2, "running", total=2)],
        execution_status="completed",
    ),
    pipeline_detail(
        "completed",
        [step(1, "completed", total=4, finished=4, failed=1), step(2, "completed", total=2)],
        execution_status="completed",
    ),
]


def test_redirected_stderr_gets_one_line_per_change_by_default(
    capsys: pytest.CaptureFixture[str],
) -> None:
    server = pipeline_server(*RUNNING_STEPS)
    with server.session() as qdash:
        timed(qdash)
        run = qdash.pipelines.execute(pipeline(), chip_id=CHIP)
        detail = run.wait(poll_interval_seconds=5)

    assert detail.pipeline is not None and detail.pipeline.status == "completed"
    assert capsys.readouterr().err.splitlines() == [
        "qdash: pipeline run exec-1: running | steps 0/2 ended | "
        "step 1 s1 running, tasks 1/4 finished | elapsed 0s",
        # The first step's execution completed; the whole run is still running.
        "qdash: pipeline run exec-1: running | steps 1/2 ended | "
        "step 2 s2 running, tasks 0/2 finished | elapsed 10s",
        "qdash: pipeline run exec-1: completed | steps 2/2 ended | elapsed 15s",
    ]
    # Exactly the reads the wait makes anyway: one per poll.
    assert server.paths().count(EXEC_PATH) == 4


def test_progress_false_writes_nothing_and_reads_the_same(
    capsys: pytest.CaptureFixture[str], notebook: list[tuple[str, Any]]
) -> None:
    server = pipeline_server(*RUNNING_STEPS)
    with server.session() as qdash:
        run = qdash.pipelines.execute(pipeline(), chip_id=CHIP)
        run.wait(poll_interval_seconds=0, progress=False)

    assert capsys.readouterr() == ("", "")
    assert notebook == []
    assert server.paths().count(EXEC_PATH) == 4


def test_an_interactive_terminal_rewrites_one_line_and_ends_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = TtyStream()
    monkeypatch.setattr(sys, "stderr", stream)
    server = pipeline_server(*RUNNING_STEPS)
    with server.session() as qdash:
        timed(qdash)
        result = qdash.run("exec-1").wait(poll_interval_seconds=5)

    assert result.succeeded
    out = stream.getvalue()
    # Every poll redraws the same line, the elapsed time included; only the end adds a newline.
    assert out.count("\r") == 5
    assert out.count("\n") == 1 and out.endswith("\x1b[K\n")
    assert "run exec-1: running | steps 0/2 ended" in out
    assert "elapsed 5s" in out
    assert out.rsplit("\r", 1)[1].startswith("qdash: run exec-1: completed | steps 2/2 ended")


def test_a_notebook_updates_its_own_display_only(
    capsys: pytest.CaptureFixture[str], notebook: list[tuple[str, Any]]
) -> None:
    server = pipeline_server(*RUNNING_STEPS)
    with server.session() as qdash:
        timed(qdash)
        qdash.run("exec-1").wait(poll_interval_seconds=5)

    assert capsys.readouterr() == ("", "")
    kinds = [kind for kind, _ in notebook]
    assert kinds[0] == "display" and set(kinds[1:]) == {"update"}
    assert "clear_output" not in kinds
    assert notebook[-1][1].startswith("qdash: run exec-1: completed")


def test_a_failing_notebook_display_falls_back_to_stderr(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def display(bundle: Any, **kwargs: Any) -> Any:
        raise RuntimeError("no frontend")

    ipython = types.ModuleType("IPython")
    ipython.get_ipython = lambda: types.SimpleNamespace(kernel=object())  # type: ignore[attr-defined]
    display_module = types.ModuleType("IPython.display")
    display_module.display = display  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "IPython", ipython)
    monkeypatch.setitem(sys.modules, "IPython.display", display_module)
    server = pipeline_server(RUNNING_STEPS[-1])
    with server.session() as qdash:
        assert qdash.run("exec-1").wait().succeeded

    assert capsys.readouterr().err.startswith("qdash: run exec-1: completed")


def test_ipython_outside_a_kernel_is_not_a_notebook(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    ipython = types.ModuleType("IPython")
    ipython.get_ipython = lambda: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "IPython", ipython)
    server = pipeline_server(RUNNING_STEPS[-1])
    with server.session() as qdash:
        qdash.run("exec-1").wait()

    assert capsys.readouterr().err.startswith("qdash: run exec-1: completed")


def test_a_timeout_ends_the_display_and_still_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = TtyStream()
    monkeypatch.setattr(sys, "stderr", stream)
    server = pipeline_server(RUNNING_STEPS[0])
    with server.session() as qdash:
        timed(qdash)
        with pytest.raises(TimeoutError, match="did not reach a terminal state within 10"):
            qdash.run("exec-1").wait(timeout_seconds=10, poll_interval_seconds=5)

    last = stream.getvalue().rsplit("\r", 1)[1]
    assert last == (
        "qdash: run exec-1: running | steps 0/2 ended | step 1 s1 running, tasks 1/4 "
        "finished | stopped waiting: timed out (the run was not cancelled) | elapsed 10s\x1b[K\n"
    )
    assert not any("cancel" in path for _, path in server.paths())


def test_a_narrow_terminal_cuts_the_live_line_but_not_the_final_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = TtyStream()
    monkeypatch.setattr(sys, "stderr", stream)
    monkeypatch.setenv("COLUMNS", "40")
    server = pipeline_server(RUNNING_STEPS[0], RUNNING_STEPS[-1])
    with server.session() as qdash:
        qdash.run("exec-1").wait(poll_interval_seconds=0)

    # The first read, the second read, then the final line.
    _, live, _, final = stream.getvalue().split("\r")
    assert live == "qdash: run exec-1: running | steps 0/2~\x1b[K"
    assert final.startswith("qdash: run exec-1: completed | steps 2/2 ended | elapsed ")


def test_an_interrupt_ends_the_display_and_propagates(
    capsys: pytest.CaptureFixture[str],
) -> None:
    server = pipeline_server(RUNNING_STEPS[0])
    with server.session() as qdash:
        executions = qdash._executions

        def interrupt(seconds: float) -> None:
            raise KeyboardInterrupt

        executions._sleep = interrupt
        with pytest.raises(KeyboardInterrupt):
            qdash.run("exec-1").wait()

    lines = capsys.readouterr().err.splitlines()
    assert len(lines) == 2
    assert "stopped waiting: interrupted (the run was not cancelled)" in lines[1]
    assert not any("cancel" in path for _, path in server.paths())


def test_a_read_error_ends_the_display_and_propagates(
    capsys: pytest.CaptureFixture[str],
) -> None:
    server = Server({EXEC_PATH: [httpx.Response(403, json={"detail": "forbidden"})]})
    with server.session() as qdash, pytest.raises(QDashAuthError):
        qdash.run("exec-1").wait()

    assert capsys.readouterr().err == (
        "qdash: run exec-1: stopped waiting: QDashAuthError | elapsed 0s\n"
    )


def test_a_run_not_listed_yet_is_shown_as_not_found(capsys: pytest.CaptureFixture[str]) -> None:
    server = Server(
        {EXEC_PATH: [httpx.Response(404, json={"detail": "missing"}), ok(RUNNING_STEPS[-1])]}
    )
    with server.session() as qdash:
        assert qdash.run("exec-1").wait(poll_interval_seconds=0).succeeded

    lines = capsys.readouterr().err.splitlines()
    assert lines[0] == "qdash: run exec-1: not found yet | elapsed 0s"
    assert lines[1].startswith("qdash: run exec-1: completed")


def test_invalid_arguments_and_a_broken_stream_never_show_or_fail(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    server = pipeline_server(RUNNING_STEPS[-1])
    with server.session() as qdash:
        with pytest.raises(ValueError, match="non-negative"):
            qdash.run("exec-1").wait(timeout_seconds=-1)
        assert capsys.readouterr().err == ""
        monkeypatch.setattr(sys, "stderr", BrokenStream())
        assert qdash.run("exec-1").wait().succeeded


def test_a_single_execution_counts_its_own_tasks(capsys: pytest.CaptureFixture[str]) -> None:
    detail = {
        "name": "quick-run:CheckT1",
        "status": "running",
        "note": {},
        "task": [
            {"task_id": "t-c", "name": "Configure", "qid": "0", "status": "completed"},
            {"task_id": "t-1", "name": "CheckT1", "qid": "0", "status": "failed"},
            {"task_id": "t-2", "name": "CheckT2", "qid": "0", "status": "running"},
        ],
    }
    server = Server(
        {
            tasks.EXECUTE: [ok(tasks.execute_response())],
            EXEC_PATH: [ok(detail), ok({**detail, "status": "completed"})],
        }
    )
    with server.session() as qdash:
        run = qdash.tasks.run(TaskCall(name="CheckT1"), chip_id=CHIP, qid="0")
        run.wait(poll_interval_seconds=0)

    lines = capsys.readouterr().err.splitlines()
    assert lines[0] == (
        "qdash: task CheckT1 on 0 (run exec-1): running | tasks 2/3 finished (1 failed) | "
        "elapsed 0s"
    )
    assert lines[1].startswith("qdash: task CheckT1 on 0 (run exec-1): completed")


def test_a_workflow_shows_the_whole_flow_not_its_first_execution(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def server() -> Server:
        return Server(
            workflows.routes(
                **workflows.run_states(
                    ok(
                        workflows.state_body(
                            "running", executions=[("exec-1", "completed"), ("exec-2", "running")]
                        )
                    ),
                    ok(workflows.state_body("unavailable", reason="Prefect is down")),
                    ok(workflows.state_body("completed", executions=[("exec-1", "completed")])),
                ),
                **workflows.executions(ok(RUNNING_STEPS[-1])),
            )
        )

    shown, silent = server(), server()
    shown.session().workflows.run(workflows.NAME).wait(poll_interval_seconds=0)
    lines = capsys.readouterr().err.splitlines()
    silent.session().workflows.run(workflows.NAME).wait(poll_interval_seconds=0, progress=False)

    assert capsys.readouterr().err == ""
    label = f"qdash: workflow {workflows.NAME} run cpr-1"
    assert lines == [
        f"{label}: running | 2 executions (1 open) | elapsed 0s",
        f"{label}: unavailable | Prefect is down | elapsed 0s",
        f"{label}: completed | 1 executions | elapsed 0s",
    ]
    # The display adds no request.
    assert shown.paths() == silent.paths()


def test_a_session_run_forwards_progress_and_shows_a_failed_end(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def server() -> Server:
        return Server(
            {
                sessions.SESSION_PATH: [ok(sessions.record())],
                sessions.EXECUTE: [httpx.Response(202, json=sessions.launched())],
                sessions.run_state_path(): [
                    ok(
                        sessions.state("running", executions=("exec-1",), steps=(("t1", "exec-1"),))
                    ),
                    ok(sessions.state("failed", reason="flow said so")),
                ],
            }
        )

    for progress in (True, False):
        with server().session() as client:
            session = CalibrationSession.open(client, session_id="cs-1")
            with pytest.raises(CalibrationRunError, match="ended failed"):
                session.run(
                    sessions.targets(),
                    sessions.steps(),
                    poll_interval_seconds=0,
                    progress=progress,
                )
        err = capsys.readouterr().err
        if not progress:
            assert err == ""
            continue
        assert err.splitlines() == [
            "qdash: calibration run cpr-1: running | steps 1/1 ended | elapsed 0s",
            # The run's own end, not a failure of the wait.
            "qdash: calibration run cpr-1: failed | flow said so | elapsed 0s",
        ]


def test_a_calibration_launch_and_chip_run_can_be_silenced(
    capsys: pytest.CaptureFixture[str],
) -> None:
    server = Server(
        {
            sessions.SESSION_PATH: [ok(sessions.record())],
            sessions.EXECUTE: [httpx.Response(202, json=sessions.launched())],
            sessions.run_state_path(): [ok(sessions.state("completed"))],
            EXEC_PATH: [ok(RUNNING_STEPS[-1])],
        }
    )
    with server.session() as client:
        session = CalibrationSession.open(client, session_id="cs-1")
        launch = session.submit(sessions.targets(), sessions.steps())
        assert launch.wait(progress=False).succeeded
        assert capsys.readouterr().err == ""
        chip_run = client.chip(CHIP).calibrate(sessions.targets(), sessions.steps())
        assert chip_run.wait(progress=False).succeeded
        assert capsys.readouterr().err == ""
        assert chip_run.wait().succeeded
    assert capsys.readouterr().err.startswith("qdash: calibration run exec-1: completed")
