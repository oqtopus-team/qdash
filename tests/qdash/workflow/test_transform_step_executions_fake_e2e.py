"""Filters in a saved workflow are recorded as Executions, end to end on the fake backend.

A ``@calibration_flow`` saved and launched through the API runs two calibrations in one flow
run: a bring-up step followed by two filters, then a Rabi check. The worker runs the saved
entrypoint in-process (the harness of ``test_calibration_session_fake_e2e``) against the
in-memory MongoDB, so the Executions, task results and API reads are the real ones.
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.repository import MongoExecutionRepository
from tests.qdash.workflow.test_calibration_run_grouping_fake_e2e import _claim_in_memory
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

    from qdash.calibration import CalibrationResult
    from tests.qdash.workflow.test_two_qubit_pairs_fake_e2e import _RecordingCoordinator

FLOW_NAME = "bringup_then_filter"
FLOW_SOURCE = f"""
from qdash.calibration import (
    CustomOneQubit,
    ExecutionStep,
    FilterByStatus,
    QubitTargets,
    TaskCall,
)
from qdash.workflow import CalibrationSession, calibration_flow, resolve_calib_context


@calibration_flow(session_name="Filter check")
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
    steps: list[ExecutionStep] = [
        CustomOneQubit(
            step_name="bringup",
            tasks=[TaskCall(name="FakeBringUp")],
            execution_mode="sequential",
        ),
        FilterByStatus(step="bringup"),
        FilterByStatus(step="bringup"),
    ]
    first = session.run(targets=targets, steps=steps, name=flow_name, tags=tags)
    second = session.run(
        targets=QubitTargets(list(first.candidate_qids)),
        steps=[
            CustomOneQubit(
                step_name="rabi", tasks=[TaskCall(name="CheckRabi")], execution_mode="sequential"
            )
        ],
        name=flow_name,
        tags=tags,
    )
    return first, second
"""


def _run_as_worker(
    run: dict[str, Any], monkeypatch: pytest.MonkeyPatch, *, flow_run_id: str
) -> tuple[CalibrationResult, CalibrationResult]:
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
        id=flow_run_id, name="dancing-fox", context=run.get("context") or {}, auto_scheduled=False
    )
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
    response = test_client.post(
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


@pytest.mark.usefixtures("saved")
def test_filters_are_recorded_executions_of_the_run(
    test_client: TestClient,
    coordinator: _RecordingCoordinator,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = test_client.post(
        f"/flows/{FLOW_NAME}/execute", headers=HEADERS, json={"idempotency_key": "click-1"}
    )
    assert response.status_code == 200, response.text
    launch = response.json()
    flow_run_id = launch["flow_run_id"]

    first, second = _run_as_worker(coordinator.runs[0], monkeypatch, flow_run_id=flow_run_id)

    # The first call recorded its calibration step and both filters, in order.
    assert len(first.execution_ids) == 3
    executions = {
        doc.execution_id: doc
        for doc in ExecutionHistoryDocument.find(
            {"project_id": PROJECT_ID, "note.flow_run_id": flow_run_id}
        ).run()
    }
    bringup, *filters = (executions[execution_id] for execution_id in first.execution_ids)
    assert [doc.note["step_index"] for doc in (bringup, *filters)] == [1, 2, 3]
    assert [doc.note["step_key"] for doc in (bringup, *filters)] == [
        "bringup",
        "filter_by_status_2",
        "filter_by_status_3",
    ]
    assert all(doc.status == "completed" for doc in executions.values())
    assert all(doc.start_at is not None and doc.end_at is not None for doc in filters)
    for doc in filters:
        assert doc.note["step_kind"] == "transform"
        assert doc.note["calibration_run_id"] == launch["calibration_run_id"]
        assert doc.note["transform_result"]["output_qids"] == list(first.candidate_qids)
        # A filter runs no task.
        assert TaskResultHistoryDocument.find({"execution_id": doc.execution_id}).count() == 0
    assert TaskResultHistoryDocument.find({"execution_id": bringup.execution_id}).count() > 0
    assert set(first.steps) == {"bringup"}
    assert list(first["transforms"]) == ["filter_by_status_2", "filter_by_status_3"]
    # The second call of the same flow run is its own step in the same run.
    [rabi_id] = second.execution_ids
    assert executions[rabi_id].note["step_kind"] == "calibration"
    assert second.run_id == first.run_id == launch["calibration_run_id"]

    # The run lists every step execution; a filter's detail carries its decision and no task.
    state = test_client.get(
        f"/calibration-sessions/{launch['calibration_session_id']}/runs/"
        f"{launch['calibration_run_id']}",
        headers=HEADERS,
    )
    assert state.status_code == 200, state.text
    listed = [summary["execution_id"] for summary in state.json()["executions"]]
    assert set(listed) == set(first.execution_ids) | {rabi_id}
    detail = test_client.get(f"/executions/{filters[0].execution_id}", headers=HEADERS)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["task"] == []
    assert body["note"]["transform_result"]["kind"] == "filter"
    assert body["note"]["transform_result"]["source_step"] == "bringup"
