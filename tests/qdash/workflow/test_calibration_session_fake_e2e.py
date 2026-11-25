"""``CalibrationSession`` in a saved workflow, end to end on the fake backend.

The flow is written as the templates are: ``@calibration_flow(session_name=...)``, an explicit
context and ``CalibrationSession.from_context(context).run(targets=..., steps=...)`` with the
shared ``qdash.calibration`` definitions. It runs two calibrations in one flow run. The
harness of ``test_calibration_run_grouping_fake_e2e`` saves and launches it through the API and
runs the saved entrypoint in-process as the worker would.
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from qdash.calibration import CalibrationResult
from qdash.dbmodel.calibration_session import (
    CalibrationPipelineRunDocument,
    CalibrationSessionDocument,
)
from qdash.repository import MongoExecutionRepository
from tests.qdash.workflow.test_calibration_run_grouping_fake_e2e import (
    _claim_in_memory,
    _steps_of,
)
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

FLOW_NAME = "session_two_runs"
SESSION_NAME = "Qubit 0 bring-up check"
FLOW_SOURCE = f"""
from qdash.calibration import CustomOneQubit, QubitTargets, TaskCall
from qdash.workflow import CalibrationSession, calibration_flow, resolve_calib_context


@calibration_flow(session_name="{SESSION_NAME}")
def {FLOW_NAME}(
    username: str,
    chip_id: str,
    qids: list[str] | None = None,
    flow_name: str | None = None,
    project_id: str | None = None,
    tags: list[str] | None = None,
):
    context = resolve_calib_context(username, chip_id, project_id=project_id, backend="fake")
    session = CalibrationSession.from_context(context)
    targets = QubitTargets(qids or ["0"])
    first = session.run(
        targets=targets,
        steps=[
            CustomOneQubit(
                step_name="bringup",
                tasks=[TaskCall(name="FakeBringUp")],
                execution_mode="sequential",
            )
        ],
        name=flow_name,
        tags=tags,
    )
    second = session.run(
        targets=targets,
        steps=[
            CustomOneQubit(
                step_name="rabi",
                tasks=[TaskCall(name="CheckRabi")],
                execution_mode="sequential",
            )
        ],
        name=flow_name,
        tags=tags,
    )
    return first, second
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
) -> tuple[CalibrationResult, CalibrationResult]:
    """Run the saved entrypoint as the worker does, with the loaded flow in the context."""
    from qdash.dbmodel.flow import FlowDocument
    from qdash.workflow.service._internal import session as session_module

    flow = FlowDocument.find_one({"project_id": PROJECT_ID, "name": FLOW_NAME}).run()
    assert flow is not None
    spec = importlib.util.spec_from_file_location(f"user_flow_{uuid.uuid4().hex}", flow.file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    entrypoint = getattr(module, FLOW_NAME)

    flow_run = SimpleNamespace(
        id=flow_run_id,
        name="dancing-fox",
        context=run.get("context") or {} if context is None else context,
        auto_scheduled=context is not None,
    )
    # The worker's flow-run context holds the flow object the deployment loaded; the session
    # name is the attribute @calibration_flow set on it.
    loaded_flow = SimpleNamespace(
        name=FLOW_NAME, qdash_session_name=getattr(entrypoint, "qdash_session_name", None)
    )
    run_context = SimpleNamespace(flow_run=flow_run, flow=loaded_flow)
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
    result: tuple[CalibrationResult, CalibrationResult] = getattr(entrypoint, "fn", entrypoint)(
        **run["parameters"]
    )
    return result


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
class TestCalibrationSessionInASavedFlow:
    def test_the_declared_name_names_the_automatic_session_before_it_is_created(
        self,
        test_client: TestClient,
        coordinator: _RecordingCoordinator,  # noqa: F811
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        response = test_client.post(
            f"/flows/{FLOW_NAME}/execute", headers=HEADERS, json={"idempotency_key": "click-1"}
        )
        assert response.status_code == 200, response.text
        session_id = response.json()["calibration_session_id"]
        run_id = response.json()["calibration_run_id"]
        [session] = CalibrationSessionDocument.find_all().to_list()
        # Applied when the API created the session, before the worker ran anything.
        assert (session.calibration_session_id, session.objective) == (session_id, SESSION_NAME)
        assert session.origin == "automatic"

        flow_run_id = response.json()["flow_run_id"]
        first, second = _run_as_worker(coordinator.runs[0], monkeypatch, flow_run_id=flow_run_id)

        steps = _steps_of(flow_run_id)
        assert sorted(step.note["step_name"] for step in steps) == ["bringup", "rabi"]
        assert all(step.status == "completed" for step in steps), [s.status for s in steps]
        # Both runs of the flow run joined the launch's session and run; none was created.
        for result in (first, second):
            assert isinstance(result, CalibrationResult)
            assert result.status == "completed" and result.succeeded
            assert (result.calibration_session_id, result.run_id) == (session_id, run_id)
            assert result.candidate_qids == ("0",)
        assert {first.execution_ids, second.execution_ids} == {
            (step.execution_id,) for step in steps
        }
        assert set(first.steps) == {"bringup"} and set(second.steps) == {"rabi"}
        assert first["candidate_qids"] == ["0"]  # the legacy result dictionary stays readable
        assert CalibrationSessionDocument.find_all().count() == 1
        assert CalibrationPipelineRunDocument.find_all().count() == 1

    def test_an_explicit_session_keeps_its_own_name(
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
        response = test_client.post(
            f"/flows/{FLOW_NAME}/execute",
            headers=HEADERS,
            json={"calibration_session_id": session_id, "idempotency_key": "trial-1"},
        )
        assert response.status_code == 200, response.text

        first, second = _run_as_worker(
            coordinator.runs[0], monkeypatch, flow_run_id=response.json()["flow_run_id"]
        )

        [session] = CalibrationSessionDocument.find_all().to_list()
        assert session.objective == "Tune qubit 0"
        assert first.calibration_session_id == second.calibration_session_id == session_id

    def test_a_scheduled_flow_run_names_its_worker_recorded_session(
        self,
        test_client: TestClient,
        coordinator: _RecordingCoordinator,  # noqa: F811
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # A schedule starts the deployment without QDash's launch: no run identity in it.
        run = {"parameters": {"username": USERNAME, "chip_id": CHIP_ID, "qids": ["0"]}}

        first, second = _run_as_worker(run, monkeypatch, flow_run_id="fr-sched", context={})

        [session] = CalibrationSessionDocument.find_all().to_list()
        assert session.calibration_session_id == "cs-flow-fr-sched"
        assert session.objective == SESSION_NAME
        [recorded] = CalibrationPipelineRunDocument.find_all().to_list()
        assert recorded.trigger == "schedule"
        assert first.run_id == second.run_id == recorded.run_id
        assert first.calibration_session_id == "cs-flow-fr-sched"
