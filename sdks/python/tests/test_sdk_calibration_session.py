"""``CalibrationSession``: create or open a session through a client and run calibrations in it."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from test_sdk_session import CHIP, Server, execute_body, validate_body

from qdash.calibration import (
    CalibrationResult,
    CalibrationRunError,
    CustomOneQubit,
    MuxTargets,
    QubitTargets,
    TaskCall,
    TwoQubitCalibration,
    sweep,
)
from qdash.sdk import (
    CalibrationSession,
    CalibrationSessionClosedError,
    QDashConfigError,
    QDashConflictError,
    QDashNotFoundError,
    QDashTransportError,
)

SESSION_PATH = ("GET", "/calibration-sessions/cs-1")
CREATE = ("POST", "/calibration-sessions")
CLOSE = ("POST", "/calibration-sessions/cs-1/close")
EXECUTE = ("POST", "/calibration-pipelines/execute")
VALIDATE = ("POST", "/calibration-pipelines/validate")


def record(status: str = "open", *, objective: str = "Coherence check") -> dict[str, Any]:
    return {
        "calibration_session_id": "cs-1",
        "project_id": "project-a",
        "chip_id": CHIP,
        "objective": objective,
        "created_by": "alice",
        "status": status,
        "created_at": "2026-11-24T00:00:00Z",
        "updated_at": "2026-11-24T00:00:00Z",
    }


def launched(run_id: str = "cpr-1", execution_id: str = "exec-1") -> dict[str, Any]:
    return {
        **execute_body(),
        "execution_id": execution_id,
        "calibration_session_id": "cs-1",
        "pipeline_run_id": run_id,
    }


def state(
    flow_status: str,
    *,
    run_id: str = "cpr-1",
    executions: tuple[str, ...] = (),
    reason: str = "",
    steps: tuple[tuple[str, str], ...] = (),
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "run_id": run_id,
        "calibration_session_id": "cs-1",
        "chip_id": CHIP,
        "run_kind": "pipeline",
        "idempotency_key": "k",
        "requested_by": "alice",
        "dispatch_status": "dispatched",
        "attempts": 1,
        "pipeline_name": "pipeline",
        "backend_name": "qubex",
        "flow_run_id": "run-1",
        "requested_at": "2026-11-24T00:00:00Z",
        "updated_at": "2026-11-24T00:00:00Z",
        "executions": [
            {"name": "pipeline", "execution_id": eid, "status": "completed", "tags": [], "note": {}}
            for eid in executions
        ],
        "flow_status": flow_status,
        "flow_status_reason": reason,
        "observed_at": "2026-11-24T00:01:00Z",
    }
    if steps:
        body["pipeline"] = {
            "name": "pipeline",
            "flow_run_id": "run-1",
            "root_execution_id": executions[0] if executions else "exec-1",
            "status": flow_status,
            "steps": [
                {
                    "index": index,
                    "name": name,
                    "step_id": name,
                    "execution_id": eid,
                    "status": "completed",
                }
                for index, (name, eid) in enumerate(steps, start=1)
            ],
        }
    return body


def run_state_path(run_id: str = "cpr-1") -> tuple[str, str]:
    return ("GET", f"/calibration-sessions/cs-1/runs/{run_id}")


def targets() -> QubitTargets:
    return QubitTargets(["0", "1"])


def steps() -> list[CustomOneQubit]:
    return [
        CustomOneQubit(
            step_name="t1",
            tasks=[TaskCall(name="CheckT1", run={"time_range": sweep.linspace(0, 10, 3)})],
        )
    ]


def json_body(request: httpx.Request) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(request.content)
    return body


def test_create_maps_the_name_to_the_objective_and_open_reads_the_session() -> None:
    server = Server(
        {
            CREATE: [httpx.Response(201, json=record())],
            SESSION_PATH: [httpx.Response(200, json=record())],
        }
    )
    with server.session() as client:
        created = CalibrationSession.create(client, chip_id=CHIP, name="Coherence check")
        opened = CalibrationSession.open(client, session_id="cs-1")

    assert json_body(server.requests[0]) == {"chip_id": CHIP, "objective": "Coherence check"}
    for session in (created, opened):
        assert (session.session_id, session.chip_id, session.name) == (
            "cs-1",
            CHIP,
            "Coherence check",
        )
        assert session.status == "open" and not session.closed
    with pytest.raises(TypeError, match=r"CalibrationSession\.create"):
        CalibrationSession(client, record())  # type: ignore[arg-type]


def test_create_checks_its_input_and_project_before_any_request() -> None:
    server = Server()
    with (
        server.session(project_id=None) as client,
        pytest.raises(QDashConfigError, match="project"),
    ):
        CalibrationSession.create(client, chip_id=CHIP, name="x")
    with server.session() as client:
        with pytest.raises(ValueError, match="name"):
            CalibrationSession.create(client, chip_id=CHIP, name="  ")
        with pytest.raises(ValueError, match="500"):
            CalibrationSession.create(client, chip_id=CHIP, name="x" * 501)
    assert server.requests == []


def test_a_response_for_another_session_or_chip_is_not_trusted() -> None:
    other = {**record(), "calibration_session_id": "cs-2"}
    server = Server(
        {
            SESSION_PATH: [httpx.Response(200, json=other)],
            CREATE: [httpx.Response(201, json={**record(), "chip_id": "other"})],
        }
    )
    with server.session() as client:
        with pytest.raises(QDashTransportError, match="cs-2"):
            CalibrationSession.open(client, session_id="cs-1")
        with pytest.raises(QDashTransportError, match="chip"):
            CalibrationSession.create(client, chip_id=CHIP, name="x")


def test_open_a_missing_session_raises_not_found() -> None:
    server = Server({SESSION_PATH: [httpx.Response(404, json={"detail": "not found"})]})
    with server.session() as client, pytest.raises(QDashNotFoundError):
        CalibrationSession.open(client, session_id="cs-1")


def test_repeated_runs_stay_in_the_session_and_wait_for_the_whole_run() -> None:
    server = Server(
        {
            SESSION_PATH: [httpx.Response(200, json=record())],
            EXECUTE: [
                httpx.Response(202, json=launched("cpr-1", "exec-1")),
                httpx.Response(202, json=launched("cpr-2", "exec-3")),
            ],
            run_state_path("cpr-1"): [
                # The first execution completed, but the run goes on: not done yet.
                httpx.Response(200, json=state("running", executions=("exec-1",))),
                httpx.Response(
                    200,
                    json=state(
                        "completed",
                        executions=("exec-1", "exec-2"),
                        steps=(("t1", "exec-1"), ("t2", "exec-2")),
                    ),
                ),
            ],
            run_state_path("cpr-2"): [
                httpx.Response(200, json=state("completed", run_id="cpr-2", executions=("exec-3",)))
            ],
        }
    )
    with server.session() as client:
        session = CalibrationSession.open(client, session_id="cs-1")
        first = session.run(
            targets(),
            steps(),
            default_run_parameters={"shots": 1024},
            name="coherence",
            idempotency_key="trial-1",
            poll_interval_seconds=2,
        )
        second = session.run(targets=MuxTargets([0]), steps=steps(), poll_interval_seconds=2)

    assert isinstance(first, CalibrationResult) and first.succeeded
    assert (first.calibration_session_id, first.run_id) == ("cs-1", "cpr-1")
    assert first.execution_ids == ("exec-1", "exec-2")
    assert set(first.steps) == {"t1", "t2"}
    assert (second.run_id, second.execution_ids) == ("cpr-2", ("exec-3",))
    executes = [json_body(r) for r in server.requests if (r.method, r.url.path) == EXECUTE]
    assert [body["calibration_session_id"] for body in executes] == ["cs-1", "cs-1"]
    assert executes[0]["idempotency_key"] == "trial-1"
    assert executes[0]["spec"] == {
        "spec_version": 2,
        "targets": {"qids": ["0", "1"]},
        "steps": [
            {
                "type": "CustomOneQubit",
                "step_name": "t1",
                "tasks": [
                    {
                        "name": "CheckT1",
                        "run": {"time_range": {"value": [0, 10, 3], "value_type": "np.linspace"}},
                    }
                ],
            }
        ],
        "name": "coherence",
        "default_run_parameters": {"shots": 1024},
    }
    assert executes[1]["spec"]["targets"] == {"mux_ids": [0]}
    assert server.sleeps == [2]


@pytest.mark.parametrize("ended", ["failed", "cancelled", "crashed", "not_launched"])
def test_a_run_that_does_not_complete_raises_with_its_result(ended: str) -> None:
    server = Server(
        {
            SESSION_PATH: [httpx.Response(200, json=record())],
            EXECUTE: [httpx.Response(202, json=launched())],
            # It ended before creating any execution: still seen to end.
            run_state_path(): [httpx.Response(200, json=state(ended, reason="flow said so"))],
        }
    )
    with server.session() as client:
        session = CalibrationSession.open(client, session_id="cs-1")
        with pytest.raises(CalibrationRunError, match=f"ended {ended}") as raised:
            session.run(targets(), steps())
    assert raised.value.result.status == ended
    assert not raised.value.result.succeeded
    assert raised.value.result.execution_ids == ()


def test_submit_returns_at_once_and_a_timeout_cancels_nothing() -> None:
    server = Server(
        {
            SESSION_PATH: [httpx.Response(200, json=record())],
            EXECUTE: [httpx.Response(202, json=launched())],
            run_state_path(): [httpx.Response(200, json=state("unavailable"))],
        }
    )
    with server.session() as client:
        session = CalibrationSession.open(client, session_id="cs-1")
        launch = session.submit(targets(), steps())
        assert (launch.calibration_session_id, launch.run_id, launch.execution_id) == (
            "cs-1",
            "cpr-1",
            "exec-1",
        )
        assert launch.get().status == "unavailable"
        with pytest.raises(TimeoutError, match="not cancelled"):
            launch.wait(timeout_seconds=0, poll_interval_seconds=0)
    methods = {(r.method, r.url.path) for r in server.requests}
    assert not any("cancel" in path for _, path in methods)
    assert CLOSE not in methods


def test_a_closed_session_admits_no_run_and_is_never_reopened() -> None:
    server = Server({SESSION_PATH: [httpx.Response(200, json=record("closed"))]})
    with server.session() as client:
        session = CalibrationSession.open(client, session_id="cs-1")
        assert session.closed
        with pytest.raises(CalibrationSessionClosedError):
            session.submit(targets(), steps())
        with pytest.raises(CalibrationSessionClosedError):
            session.run(targets(), steps())
    assert [(r.method, r.url.path) for r in server.requests] == [SESSION_PATH]


def test_close_ends_admission_without_closing_the_client() -> None:
    closed = {**record("closed"), "pipeline_runs": [], "agent_sessions": []}
    server = Server(
        {
            SESSION_PATH: [httpx.Response(200, json=record())],
            CLOSE: [httpx.Response(200, json=closed)],
        }
    )
    with server.session() as client:
        session = CalibrationSession.open(client, session_id="cs-1")
        session.close(note="done")
        assert session.closed
        with pytest.raises(CalibrationSessionClosedError):
            session.submit(targets(), steps())
        # The client still works after the session closed.
        assert CalibrationSession.open(client, session_id="cs-1").session_id == "cs-1"
    assert json_body(server.requests[1]) == {
        "closing_note": "done",
        "acknowledge_unknown_runs": False,
    }


def test_a_session_closed_since_it_was_read_is_refused_by_the_server() -> None:
    server = Server(
        {
            SESSION_PATH: [httpx.Response(200, json=record())],
            EXECUTE: [httpx.Response(409, json={"detail": "Calibration session cs-1 is closed"})],
        }
    )
    with server.session() as client:
        session = CalibrationSession.open(client, session_id="cs-1")
        with pytest.raises(QDashConflictError, match="closed"):
            session.submit(targets(), steps())


def test_an_unconfirmed_association_is_unknown_not_retried() -> None:
    unlinked = {**execute_body(), "calibration_session_id": None, "pipeline_run_id": None}
    server = Server(
        {
            SESSION_PATH: [httpx.Response(200, json=record())],
            EXECUTE: [httpx.Response(202, json=unlinked)],
        }
    )
    with server.session() as client:
        session = CalibrationSession.open(client, session_id="cs-1")
        with pytest.raises(RuntimeError, match="result unknown"):
            session.submit(targets(), steps(), idempotency_key="k-1")
    assert [(r.method, r.url.path) for r in server.requests].count(EXECUTE) == 1


def test_validate_reports_problems_and_dispatches_nothing() -> None:
    server = Server(
        {
            SESSION_PATH: [httpx.Response(200, json=record())],
            VALIDATE: [httpx.Response(200, json=validate_body(valid=False))],
        }
    )
    with server.session() as client:
        session = CalibrationSession.open(client, session_id="cs-1")
        result = session.validate(
            targets(), [TwoQubitCalibration(execution_mode="manual", rounds=[[("0", "1")]])]
        )
    assert not result.valid
    assert result.problems == ("targets.qids[0]: unknown qubit",)
    body = json_body(server.requests[-1])
    assert body["chip_id"] == CHIP
    assert body["spec"]["steps"] == [
        {"type": "TwoQubitCalibration", "execution_mode": "manual", "rounds": [[["0", "1"]]]}
    ]
    assert EXECUTE not in [(r.method, r.url.path) for r in server.requests]


def test_every_step_occurrence_is_a_result_step_with_its_recorded_outcome() -> None:
    body = state("completed", executions=("exec-1", "exec-2", "exec-3"))
    body["pipeline"] = {
        "name": "pipeline",
        "flow_run_id": "run-1",
        "root_execution_id": "exec-1",
        "status": "completed",
        "steps": [
            {
                "index": 1,
                "name": "t1",
                "step_id": "t1",
                "key": "t1",
                "kind": "calibration",
                "execution_id": "exec-1",
                "status": "completed",
            },
            *(
                {
                    "index": index,
                    "name": "filter_by_status",
                    "key": f"filter_by_status_{index}",
                    "type": "FilterByStatus",
                    "kind": "transform",
                    "execution_id": f"exec-{index}",
                    "status": "completed",
                    "transform": {
                        "kind": "filter",
                        "input_qids": ["0", "1"],
                        "output_qids": ["0"],
                        "excluded": [{"target": "1", "reason": "step t1 failed"}],
                    },
                }
                for index in (2, 3)
            ),
        ],
    }
    server = Server(
        {
            SESSION_PATH: [httpx.Response(200, json=record())],
            EXECUTE: [httpx.Response(202, json=launched("cpr-1", "exec-1"))],
            run_state_path("cpr-1"): [httpx.Response(200, json=body)],
        }
    )
    with server.session() as client:
        result = CalibrationSession.open(client, session_id="cs-1").run(
            targets(), steps(), poll_interval_seconds=2
        )

    # Repeated filters stay apart instead of one replacing the other.
    assert list(result.steps) == ["t1", "filter_by_status_2", "filter_by_status_3"]
    outcome = result.steps["filter_by_status_3"].transform
    assert outcome is not None and outcome.output_qids == ["0"]
    assert [(e.target, e.reason) for e in outcome.excluded or []] == [("1", "step t1 failed")]
    assert result.execution_ids == ("exec-1", "exec-2", "exec-3")
