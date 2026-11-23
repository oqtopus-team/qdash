"""A saved multi-step workflow is one run of one calibration session, end to end on Fake1Q.

The flow is saved and executed through the API exactly as the workflow editor does. The test
records what the API hands to Prefect, then runs the saved entrypoint in-process with exactly
those parameters and that flow-run context, as the worker would. Two calibration steps run
the fake backend's tasks for real (FakeBringUp, then CheckRabi) on qubit 0 of a fake chip
created through the API, and each step records its own execution in the in-memory MongoDB of
``tests/conftest.py``.

What is stubbed: Prefect (the dispatch is recorded and the flow function runs in-process with
a flow-run context carrying the recorded context and a flow run ID), deployment registration,
and the execution repository's own MongoDB client for claiming a pre-created execution (the
claim runs on the in-memory database instead). No hardware is involved.
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from qdash.dbmodel.calibration_session import (
    CalibrationPipelineRunDocument,
    CalibrationSessionDocument,
)
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.repository import MongoExecutionRepository
from tests.qdash.workflow.test_fake_chip_preset import (  # noqa: F401 - pytest fixtures
    CHIP_ID,
    HEADERS,
    PROJECT_ID,
    USERNAME,
    _create_fake_chip,
    fake_deployment,
    project,
)
from tests.qdash.workflow.test_two_qubit_pairs_fake_e2e import (  # noqa: F401 - fixture
    coordinator,
)

if TYPE_CHECKING:
    from pathlib import Path

    from fastapi.testclient import TestClient

    from tests.qdash.workflow.test_two_qubit_pairs_fake_e2e import _RecordingCoordinator

FLOW_NAME = "two_step_fake"
FLOW_SOURCE = """
from prefect import flow

from qdash.workflow import TaskCall
from qdash.workflow.service import CalibService, resolve_calib_context
from qdash.workflow.service.steps import CustomOneQubit
from qdash.workflow.service.targets import QubitTargets


@flow
def two_step_fake(
    username: str,
    chip_id: str,
    qids: list[str] | None = None,
    second_task: str = "CheckRabi",
    flow_name: str | None = None,
    project_id: str | None = None,
    tags: list[str] | None = None,
):
    context = resolve_calib_context(username, chip_id, project_id=project_id, backend="fake")
    cal = CalibService.from_context(context, flow_name=flow_name, tags=tags)
    return cal.run(
        QubitTargets(qids=qids or ["0"]),
        steps=[
            CustomOneQubit(
                step_name="bringup",
                tasks=[TaskCall(name="FakeBringUp")],
                execution_mode="sequential",
            ),
            CustomOneQubit(
                step_name="second",
                tasks=[TaskCall(name=second_task)],
                execution_mode="sequential",
            ),
        ],
    )
"""


def _save_flow(client: TestClient) -> None:
    response = client.post(
        "/flows",
        headers=HEADERS,
        json={
            "name": FLOW_NAME,
            "description": "",
            "code": FLOW_SOURCE,
            "flow_function_name": FLOW_NAME,
            "chip_id": CHIP_ID,
            "tags": [],
            "default_parameters": {"username": USERNAME, "chip_id": CHIP_ID, "qids": ["0"]},
        },
    )
    assert response.status_code == 200, response.text


def _run_as_worker(
    run: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    *,
    flow_run_id: str,
    context: dict[str, Any] | None = None,
    auto_scheduled: bool = False,
    flow_name: str = FLOW_NAME,
) -> Any:
    """Run the saved entrypoint as the worker runs the flow run QDash or Prefect created."""
    from qdash.dbmodel.flow import FlowDocument
    from qdash.workflow.service._internal import session as session_module

    flow_run = SimpleNamespace(
        id=flow_run_id,
        name="dancing-fox",
        context=run.get("context") or {} if context is None else context,
        auto_scheduled=auto_scheduled,
    )
    run_context = SimpleNamespace(flow_run=flow_run, flow=SimpleNamespace(name=flow_name))
    monkeypatch.setitem(
        sys.modules,
        "prefect.context",
        SimpleNamespace(
            FlowRunContext=SimpleNamespace(get=lambda: run_context),
            get_run_context=lambda: run_context,
        ),
    )
    monkeypatch.setattr(session_module, "read_flow_run_id_from_context", lambda: flow_run_id)
    monkeypatch.setattr(MongoExecutionRepository, "claim_scheduled_execution", _claim_in_memory)
    flow = FlowDocument.find_one({"project_id": PROJECT_ID, "name": FLOW_NAME}).run()
    assert flow is not None
    spec = importlib.util.spec_from_file_location(f"user_flow_{uuid.uuid4().hex}", flow.file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    entrypoint = getattr(module, FLOW_NAME)
    return getattr(entrypoint, "fn", entrypoint)(**run["parameters"])


def _claim_in_memory(_: Any, *, project_id: str, flow_run_id: str) -> str | None:
    """The repository's claim of a pre-created execution, on the in-memory database.

    The repository opens its own client to the deployment's MongoDB host; the test database
    is the in-memory one the documents use.
    """
    from pymongo import ReturnDocument

    doc = ExecutionHistoryDocument.get_motor_collection().find_one_and_update(
        {
            "project_id": project_id,
            "note.flow_run_id": flow_run_id,
            "status": "scheduled",
            "note.claimed_at": {"$exists": False},
        },
        {"$set": {"note.claimed_at": "claimed"}},
        return_document=ReturnDocument.AFTER,
    )
    return None if doc is None else str(doc["execution_id"])


def _steps_of(flow_run_id: str) -> list[ExecutionHistoryDocument]:
    return list(
        ExecutionHistoryDocument.find(
            {"project_id": PROJECT_ID, "note.flow_run_id": flow_run_id}
        ).run()
    )


@pytest.fixture
def saved(
    project: None,  # noqa: F811
    fake_deployment: Path,  # noqa: F811
    test_client: TestClient,
    coordinator: _RecordingCoordinator,  # noqa: F811
) -> None:
    from qdash.workflow.service._internal import run_identity

    run_identity._resolved.clear()
    _create_fake_chip(test_client)
    _save_flow(test_client)


@pytest.mark.usefixtures("saved")
class TestSavedWorkflowRun:
    def test_every_step_execution_belongs_to_one_session_and_one_run(
        self,
        test_client: TestClient,
        coordinator: _RecordingCoordinator,  # noqa: F811
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        response = test_client.post(
            f"/flows/{FLOW_NAME}/execute", headers=HEADERS, json={"idempotency_key": "click-1"}
        )
        assert response.status_code == 200, response.text
        body = response.json()
        session_id = body["calibration_session_id"]
        run_id = body["calibration_run_id"]
        assert session_id.startswith("cs-auto-")
        [run] = coordinator.runs
        handed = run["context"]["qdash_calibration_run"]
        assert (handed["calibration_session_id"], handed["run_id"]) == (session_id, run_id)
        # The flow run QDash created also receives the launch's dispatch token, and only it.
        assert handed["dispatch_token"]
        assert handed["dispatch_token"] not in response.text

        _run_as_worker(run, monkeypatch, flow_run_id="flow-run-1")

        steps = _steps_of("flow-run-1")
        # Two calibration steps, each with its own execution, ran the fake backend's tasks.
        assert sorted(step.note["step_name"] for step in steps) == ["bringup", "second"]
        assert all(step.status == "completed" for step in steps), [s.status for s in steps]
        for step in steps:
            assert step.note["calibration_session_id"] == session_id
            assert step.note["calibration_run_id"] == run_id
        [session] = CalibrationSessionDocument.find_all().to_list()
        assert session.origin == "automatic"
        assert session.created_by == USERNAME
        [recorded] = CalibrationPipelineRunDocument.find_all().to_list()
        assert recorded.run_id == run_id
        assert recorded.run_kind == "workflow"
        assert recorded.run_name == FLOW_NAME

        # The session lists the run with every step execution.
        detail = test_client.get(f"/calibration-sessions/{session_id}", headers=HEADERS).json()
        [listed] = detail["pipeline_runs"]
        assert listed["run_kind"] == "workflow"
        assert sorted(e["execution_id"] for e in listed["executions"]) == sorted(
            step.execution_id for step in steps
        )

        # The grouped Execution list shows the whole run as one row, nothing twice.
        groups = test_client.get(
            "/executions/groups", headers=HEADERS, params={"chip_id": CHIP_ID}
        ).json()
        [row] = groups["items"]
        assert row["kind"] == "calibration_session"
        assert row["calibration_session"]["origin"] == "automatic"
        [group_run] = row["pipeline_runs"]
        assert group_run["run_kind"] == "workflow"
        assert group_run["executions_total"] == len(steps) == 2
        assert groups["grouped_executions"] == groups["total_executions"] == 2

        # Each execution links back to the session and run.
        for step in steps:
            link = test_client.get(f"/executions/{step.execution_id}", headers=HEADERS).json()
            assert link["calibration_session"]["calibration_session_id"] == session_id
            assert link["calibration_session"]["pipeline_run_id"] == run_id

        # The audit says QDash opened the session for the user's run, and links each step's
        # measured tasks to the run that recorded them.
        audit = test_client.get(f"/calibration-sessions/{session_id}/audit", headers=HEADERS)
        assert audit.status_code == 200, audit.text
        events = audit.json()["events"]
        created_event = next(e for e in events if e["kind"] == "session_created")
        assert created_event["actor_kind"] == "server"
        assert created_event["data"]["origin"] == "automatic"
        requested = next(e for e in events if e["kind"] == "pipeline_requested")
        assert requested["summary"] == f"{USERNAME} requested workflow '{FLOW_NAME}'"
        assert requested["data"]["run_kind"] == "workflow"
        assert "requested_spec" not in requested["missing"]
        measured = [e for e in events if e["kind"] == "measurement"]
        assert {e["pipeline_run_id"] for e in measured} == {run_id}
        assert {e["execution_id"] for e in measured} == {step.execution_id for step in steps}

        # A retry of the click returns the same run and launches nothing.
        again = test_client.post(
            f"/flows/{FLOW_NAME}/execute", headers=HEADERS, json={"idempotency_key": "click-1"}
        )
        assert again.status_code == 200, again.text
        assert again.json()["calibration_run_id"] == run_id
        assert again.json()["replayed"] is True
        assert len(coordinator.runs) == 1

    def test_a_named_session_takes_repeated_trials_as_separate_runs(
        self,
        test_client: TestClient,
        coordinator: _RecordingCoordinator,  # noqa: F811
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        created = test_client.post(
            "/calibration-sessions",
            headers=HEADERS,
            json={"chip_id": CHIP_ID, "objective": "Tune qubit 0"},
        )
        assert created.status_code == 201, created.text
        session_id = created.json()["calibration_session_id"]
        run_ids = []
        flow_run_ids = []
        for index in range(2):
            response = test_client.post(
                f"/flows/{FLOW_NAME}/execute",
                headers=HEADERS,
                json={"calibration_session_id": session_id, "idempotency_key": f"trial-{index}"},
            )
            assert response.status_code == 200, response.text
            assert response.json()["calibration_session_id"] == session_id
            run_ids.append(response.json()["calibration_run_id"])
            flow_run_ids.append(response.json()["flow_run_id"])
            _run_as_worker(coordinator.runs[-1], monkeypatch, flow_run_id=flow_run_ids[-1])

        assert len(set(run_ids)) == 2
        # No automatic session was made: the trials share the named purpose.
        assert CalibrationSessionDocument.find_all().count() == 1
        detail = test_client.get(f"/calibration-sessions/{session_id}", headers=HEADERS).json()
        assert [run["run_id"] for run in detail["pipeline_runs"]] == run_ids
        assert len(set(flow_run_ids)) == 2
        for run, flow_run_id in zip(detail["pipeline_runs"], flow_run_ids, strict=True):
            assert {e["execution_id"] for e in run["executions"]} == {
                step.execution_id for step in _steps_of(flow_run_id)
            }
        [row] = test_client.get(
            "/executions/groups", headers=HEADERS, params={"chip_id": CHIP_ID}
        ).json()["items"]
        assert [r["executions_total"] for r in row["pipeline_runs"]] == [2, 2]


@pytest.mark.usefixtures("saved")
class TestScheduledRun:
    def test_a_cron_run_is_recorded_by_the_worker_once_per_flow_run(
        self,
        test_client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from qdash.workflow.service._internal import run_identity

        # What a cron schedule hands the worker: the deployment's saved parameters, no context.
        parameters = {
            "username": USERNAME,
            "chip_id": CHIP_ID,
            "qids": ["0"],
            "flow_name": FLOW_NAME,
            "project_id": PROJECT_ID,
        }
        _run_as_worker(
            {"parameters": parameters},
            monkeypatch,
            flow_run_id="cron-run-1",
            context={},
            auto_scheduled=True,
        )
        steps = _steps_of("cron-run-1")
        assert len(steps) == 2
        [session] = CalibrationSessionDocument.find_all().to_list()
        assert session.calibration_session_id == "cs-flow-cron-run-1"
        assert session.origin == "automatic"
        assert session.created_by == USERNAME
        [run] = CalibrationPipelineRunDocument.find_all().to_list()
        assert (run.run_id, run.trigger, run.run_kind) == (
            "cpr-flow-cron-run-1",
            "schedule",
            "workflow",
        )
        assert run.status == "dispatched" and run.flow_run_id == "cron-run-1"
        assert {step.note["calibration_run_id"] for step in steps} == {run.run_id}

        # A Prefect retry of the same flow run, in a fresh process, finds the same records.
        run_identity._resolved.clear()
        _run_as_worker(
            {"parameters": parameters},
            monkeypatch,
            flow_run_id="cron-run-1",
            context={},
            auto_scheduled=True,
        )
        assert CalibrationSessionDocument.find_all().count() == 1
        assert CalibrationPipelineRunDocument.find_all().count() == 1
        assert {s.note["calibration_run_id"] for s in _steps_of("cron-run-1")} == {run.run_id}

        # The next cron occurrence is a new flow run: a new session and run.
        _run_as_worker(
            {"parameters": parameters},
            monkeypatch,
            flow_run_id="cron-run-2",
            context={},
            auto_scheduled=True,
        )
        assert CalibrationSessionDocument.find_all().count() == 2
        groups = test_client.get(
            "/executions/groups", headers=HEADERS, params={"chip_id": CHIP_ID}
        ).json()
        assert groups["calibration_sessions"] == 2
        assert groups["grouped_executions"] == groups["total_executions"]

    def test_a_run_naming_an_unrecorded_run_fails_before_any_step(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from qdash.repository.calibration_run import CalibrationRunMismatch

        parameters = {
            "username": USERNAME,
            "chip_id": CHIP_ID,
            "qids": ["0"],
            "flow_name": FLOW_NAME,
            "project_id": PROJECT_ID,
        }
        forged = {"qdash_calibration_run": {"calibration_session_id": "cs-x", "run_id": "cpr-x"}}
        with pytest.raises(CalibrationRunMismatch):
            _run_as_worker(
                {"parameters": parameters}, monkeypatch, flow_run_id="forged", context=forged
            )
        assert _steps_of("forged") == []


@pytest.mark.usefixtures("saved")
class TestRunClaims:
    """Only the flow run QDash launched for a run carries it out; IDs alone claim nothing."""

    def _launch(self, client: TestClient, recorder: _RecordingCoordinator) -> Any:
        response = client.post(
            f"/flows/{FLOW_NAME}/execute", headers=HEADERS, json={"idempotency_key": "claim-1"}
        )
        assert response.status_code == 200, response.text
        return response.json(), recorder.runs[-1]

    @pytest.mark.parametrize(
        "forge",
        [
            pytest.param(lambda handed: handed, id="same-context-other-flow-run"),
            pytest.param(lambda handed: {**handed, "dispatch_token": "guessed"}, id="wrong-token"),
            pytest.param(
                lambda handed: {k: v for k, v in handed.items() if k != "dispatch_token"},
                id="no-token",
            ),
        ],
    )
    def test_another_flow_run_naming_a_launched_run_fails_before_any_step(
        self,
        test_client: TestClient,
        coordinator: _RecordingCoordinator,  # noqa: F811
        monkeypatch: pytest.MonkeyPatch,
        forge: Any,
    ) -> None:
        from qdash.repository.calibration_run import CalibrationRunMismatch

        body, run = self._launch(test_client, coordinator)
        forged = {"qdash_calibration_run": forge(run["context"]["qdash_calibration_run"])}
        with pytest.raises(CalibrationRunMismatch):
            _run_as_worker(run, monkeypatch, flow_run_id="flow-run-other", context=forged)
        assert _steps_of("flow-run-other") == []
        recorded = CalibrationPipelineRunDocument.find_one(
            {"run_id": body["calibration_run_id"]}
        ).run()
        assert recorded is not None and recorded.flow_run_id == body["flow_run_id"]

    def test_the_launched_flow_run_binds_its_run_when_the_api_never_learned_it(
        self,
        test_client: TestClient,
        coordinator: _RecordingCoordinator,  # noqa: F811
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        body, run = self._launch(test_client, coordinator)
        # The launch's response was lost: the API recorded no flow run, and the outcome is
        # unknown. The flow run it created still starts, and proves itself with the token.
        CalibrationPipelineRunDocument.get_motor_collection().update_one(
            {"run_id": body["calibration_run_id"]},
            {"$set": {"flow_run_id": None, "status": "unknown"}},
        )
        _run_as_worker(run, monkeypatch, flow_run_id="flow-run-lost")
        steps = _steps_of("flow-run-lost")
        assert len(steps) == 2
        assert {step.note["calibration_run_id"] for step in steps} == {body["calibration_run_id"]}
        recorded = CalibrationPipelineRunDocument.find_one(
            {"run_id": body["calibration_run_id"]}
        ).run()
        assert recorded is not None
        assert (recorded.flow_run_id, recorded.status) == ("flow-run-lost", "unknown")


@pytest.mark.usefixtures("saved")
class TestLaunchChecks:
    def _execute(self, client: TestClient, **body: Any) -> Any:
        return client.post(f"/flows/{FLOW_NAME}/execute", headers=HEADERS, json=body)

    def test_a_named_session_must_be_open_on_the_chip_and_in_the_project(
        self,
        test_client: TestClient,
        coordinator: _RecordingCoordinator,  # noqa: F811
    ) -> None:
        from qdash.datamodel.system_info import SystemInfoModel
        from qdash.dbmodel.chip import ChipDocument

        ChipDocument(
            project_id=PROJECT_ID,
            chip_id="other-chip",
            username=USERNAME,
            size=4,
            system_info=SystemInfoModel(),
        ).insert()
        elsewhere = test_client.post(
            "/calibration-sessions",
            headers=HEADERS,
            json={"chip_id": "other-chip", "objective": "Another chip"},
        ).json()["calibration_session_id"]
        assert self._execute(test_client, calibration_session_id=elsewhere).status_code == 422
        assert self._execute(test_client, calibration_session_id="cs-unknown").status_code == 404

        closed = test_client.post(
            "/calibration-sessions",
            headers=HEADERS,
            json={"chip_id": CHIP_ID, "objective": "Done"},
        ).json()["calibration_session_id"]
        assert (
            test_client.post(
                f"/calibration-sessions/{closed}/close", headers=HEADERS, json={}
            ).status_code
            == 200
        )
        assert self._execute(test_client, calibration_session_id=closed).status_code == 409
        # Nothing was launched and no run was recorded for any refused request.
        assert coordinator.runs == []
        assert CalibrationPipelineRunDocument.find_all().count() == 0

    def test_an_unknown_launch_is_never_launched_again_with_its_key(
        self,
        test_client: TestClient,
        coordinator: _RecordingCoordinator,  # noqa: F811
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from qdash.api.services.flow_service.execution import FlowDispatchError

        async def lost(**_: Any) -> Any:
            raise FlowDispatchError("connection reset after the request was sent")

        original = coordinator.dispatch_run
        monkeypatch.setattr(coordinator, "dispatch_run", lost)
        failed = self._execute(test_client, idempotency_key="click-1")
        assert failed.status_code == 500
        assert "may have started anyway" in failed.json()["detail"]
        [run] = CalibrationPipelineRunDocument.find_all().to_list()
        assert run.status == "unknown"

        monkeypatch.setattr(coordinator, "dispatch_run", original)
        retried = self._execute(test_client, idempotency_key="click-1")
        assert retried.status_code == 409
        assert "unknown" in retried.json()["detail"]
        assert coordinator.runs == []
        assert CalibrationSessionDocument.find_all().count() == 1

    def test_a_busy_chip_is_a_refusal_the_same_key_can_retry(
        self,
        test_client: TestClient,
        coordinator: _RecordingCoordinator,  # noqa: F811
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from fastapi import HTTPException

        async def busy(**_: Any) -> Any:
            raise HTTPException(status_code=409, detail="busy")

        original = coordinator.dispatch_run
        monkeypatch.setattr(coordinator, "dispatch_run", busy)
        assert self._execute(test_client, idempotency_key="click-1").status_code == 409
        [run] = CalibrationPipelineRunDocument.find_all().to_list()
        assert run.status == "rejected"

        monkeypatch.setattr(coordinator, "dispatch_run", original)
        retried = self._execute(test_client, idempotency_key="click-1")
        assert retried.status_code == 200, retried.text
        [run] = CalibrationPipelineRunDocument.find_all().to_list()
        assert (run.status, run.attempts) == ("dispatched", 2)
        assert retried.json()["calibration_run_id"] == run.run_id
        assert len(coordinator.runs) == 1
