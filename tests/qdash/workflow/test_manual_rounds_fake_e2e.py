"""A saved Python flow with manual rounds: preview, execute and run on the fake chip.

The flow is saved through the API, previewed through ``GET /flows/{name}/execution-plan``
and executed through ``POST /flows/{name}/execute`` exactly as the workflow editor does.
The dispatched entrypoint then runs in-process with the recorded parameters and run
context: CalibService, the pipeline preflight, the hardware reservation, the manual
round checks against the fake chip's wiring and coupling documents, and the steps run
for real on the in-memory MongoDB of ``tests/conftest.py``.

What is stubbed: Prefect dispatch (recorded), deployment registration, and the two
functions that would start worker processes; they record each round instead. Both
schedulers are replaced with failing stubs to prove manual rounds never reach them.
No hardware is involved.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from qdash.common.manual_rounds import ManualRoundsError
from tests.qdash.workflow.test_fake_chip_preset import (  # noqa: F401 - pytest fixtures
    CHIP_ID,
    HEADERS,
    USERNAME,
    _create_fake_chip,
    fake_deployment,
    project,
)
from tests.qdash.workflow.test_two_qubit_scheduled_fake_e2e import (  # noqa: F401 - fixture
    _run_dispatched_flow,
    coordinator,
)

if TYPE_CHECKING:
    from pathlib import Path

    from fastapi.testclient import TestClient

    from tests.qdash.workflow.test_two_qubit_scheduled_fake_e2e import _RecordingCoordinator

FLOW_NAME = "manual_rounds"

SOURCE = """
from prefect import flow

from qdash.workflow import TaskCall
from qdash.workflow.service import CalibService
from qdash.workflow.service.steps import CustomOneQubit, CustomTwoQubit
from qdash.workflow.service.targets import QubitTargets

ONE_QUBIT_ROUNDS = QUBITS


@flow
def manual_rounds(username, chip_id, project_id=None, flow_name=None):
    cal = CalibService(username, chip_id, project_id=project_id, flow_name=flow_name)
    steps = [
        CustomOneQubit(
            step_name="rabi_rounds",
            execution_mode="manual",
            rounds=ONE_QUBIT_ROUNDS,
            tasks=[TaskCall(name="CheckRabi")],
        ),
        CustomTwoQubit(
            step_name="cr_rounds",
            execution_mode="manual",
            rounds=PAIRS,
            tasks=[TaskCall(name="CheckCrossResonance")],
        ),
    ]
    return cal.run(QubitTargets(["0", "8", "1", "9", "4", "5"]), steps=steps)
"""
PAIRS = '[[("0", "1"), ("4", "5")], [("8", "9")]]'
QUBITS = '[["0", "8"], ["1", "9"]]'


class _Workers:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    def qubits(self, qids: list[str], plan: Any, worker: Any) -> dict[str, Any]:
        assert worker.settings.backend_name == "fake"
        self.calls.append((plan.step_id, list(qids)))
        return {qid: {"status": "success"} for qid in qids}

    def pairs(self, coupling_qids: list[str], plan: Any, worker: Any) -> dict[str, Any]:
        self.calls.append((plan.step_id, list(coupling_qids)))
        return {pair: {"status": "success"} for pair in coupling_qids}


@pytest.fixture
def workers(monkeypatch: pytest.MonkeyPatch) -> _Workers:
    from qdash.workflow.service._internal import scheduling_tasks

    record = _Workers()
    monkeypatch.setattr(scheduling_tasks, "run_qubit_calibrations_parallel", record.qubits)
    monkeypatch.setattr(scheduling_tasks, "run_coupling_calibrations_parallel", record.pairs)

    def forbidden(*_: Any, **__: Any) -> Any:
        raise AssertionError("manual rounds must not be scheduled automatically")

    monkeypatch.setattr("qdash.workflow.engine.CRScheduler", forbidden)
    monkeypatch.setattr("qdash.workflow.service.strategy.get_one_qubit_strategy", forbidden)
    return record


def _save(client: TestClient, pairs: str = PAIRS, qubits: str = QUBITS) -> dict[str, Any]:
    response = client.post(
        "/flows",
        headers=HEADERS,
        json={
            "name": FLOW_NAME,
            "description": "",
            "code": SOURCE.replace("rounds=PAIRS", f"rounds={pairs}").replace(
                "= QUBITS", f"= {qubits}"
            ),
            "flow_function_name": FLOW_NAME,
            "chip_id": CHIP_ID,
            "tags": [],
            "default_parameters": {"username": USERNAME, "chip_id": CHIP_ID},
        },
    )
    assert response.status_code == 200, response.text
    details = client.get(f"/flows/{FLOW_NAME}", headers=HEADERS)
    assert details.status_code == 200, details.text
    body: dict[str, Any] = details.json()
    return body


def _plan(client: TestClient) -> dict[str, Any]:
    response = client.get(
        f"/flows/{FLOW_NAME}/execution-plan", headers=HEADERS, params={"chip_id": CHIP_ID}
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _execute(
    client: TestClient,
    coordinator: _RecordingCoordinator,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> Any:
    from qdash.dbmodel.flow import FlowDocument

    response = client.post(f"/flows/{FLOW_NAME}/execute", headers=HEADERS, json={})
    assert response.status_code == 200, response.text
    flow = FlowDocument.find_one({"name": FLOW_NAME}).run()
    assert flow is not None
    return _run_dispatched_flow(
        flow.file_path, flow.flow_function_name, coordinator.runs[-1], monkeypatch
    )


@pytest.fixture
def chip(
    project: None,  # noqa: F811
    fake_deployment: Path,  # noqa: F811
    test_client: TestClient,
    coordinator: _RecordingCoordinator,  # noqa: F811
) -> None:
    _create_fake_chip(test_client)


def test_the_saved_flow_previews_and_runs_its_exact_rounds(
    chip: None,
    test_client: TestClient,
    coordinator: _RecordingCoordinator,  # noqa: F811
    workers: _Workers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    details = _save(test_client)
    assert details["target_modes"] == []

    plan = _plan(test_client)
    # Every step was read, and the 1Q rounds do not cover the targets.
    assert plan["status"] == "invalid", plan
    assert plan["reason"] is None
    assert plan["has_manual_rounds"] and not plan["target_override_allowed"]
    [run] = plan["runs"]
    assert run["targets"]["qids"] == ["0", "8", "1", "9", "4", "5"]
    one_qubit, two_qubit = run["steps"]
    assert one_qubit["schedule"] == "manual" and one_qubit["tasks"] == ["CheckRabi"]
    assert [r["targets"] for r in one_qubit["rounds"]] == [["0", "8"], ["1", "9"]]
    assert [r["targets"] for r in two_qubit["rounds"]] == [["0-1", "4-5"], ["8-9"]]
    # The 1Q rounds name 4 of the 6 targets: the preview reports what the run rejects.
    assert [issue["message"] for issue in one_qubit["issues"]] == [
        "current qubits 4, 5 are in no round; add them to a round or remove them from the targets"
    ]
    assert two_qubit["issues"] == []

    # The worker rejects the same rounds before any worker starts.
    with pytest.raises(ManualRoundsError, match="current qubits 4, 5 are in no round"):
        _execute(test_client, coordinator, monkeypatch)
    assert workers.calls == []


def test_matching_targets_run_rounds_in_order_without_scheduling(
    chip: None,
    test_client: TestClient,
    coordinator: _RecordingCoordinator,  # noqa: F811
    workers: _Workers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _save(test_client, qubits='[["0", "8"], ["1", "9"], ["4"], ["5"]]')
    plan = _plan(test_client)
    assert plan["status"] == "resolved", plan
    assert all(not step["issues"] for step in plan["runs"][0]["steps"])

    result = _execute(test_client, coordinator, monkeypatch)

    assert workers.calls == [
        ("rabi_rounds", ["0", "8"]),
        ("rabi_rounds", ["1", "9"]),
        ("rabi_rounds", ["4"]),
        ("rabi_rounds", ["5"]),
        ("cr_rounds", ["0-1", "4-5"]),
        ("cr_rounds", ["8-9"]),
    ]
    assert sorted(result["steps"]["cr_rounds"].couplings) == ["0-1", "4-5", "8-9"]
    assert sorted(result["steps"]["rabi_rounds"].qubits) == ["0", "1", "4", "5", "8", "9"]


def test_invalid_pairs_are_reported_by_the_preview_and_stop_the_run(
    chip: None,
    test_client: TestClient,
    coordinator: _RecordingCoordinator,  # noqa: F811
    workers: _Workers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 1-2 shares MUX 0 with 0-1; 9-8 is a coupling of the fake chip only as 8-9.
    _save(test_client, pairs='[[("0", "1"), ("1", "2")], [("9", "8")]]')
    plan = _plan(test_client)
    assert plan["status"] == "invalid"
    messages = [i["message"] for s in plan["runs"][0]["steps"] for i in s["issues"]]
    assert any("share qubit 1" in message for message in messages)

    with pytest.raises(ManualRoundsError, match="share qubit 1"):
        _execute(test_client, coordinator, monkeypatch)
    assert workers.calls == []


def test_target_overrides_are_rejected_by_the_api_and_the_runtime(
    chip: None,
    test_client: TestClient,
    coordinator: _RecordingCoordinator,  # noqa: F811
    workers: _Workers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from qdash.dbmodel.flow import FlowDocument

    _save(test_client)
    response = test_client.post(
        f"/flows/{FLOW_NAME}/execute",
        headers=HEADERS,
        json={"target_override": {"qids": ["0", "1"]}},
    )
    assert response.status_code == 400
    assert "Target overrides are not accepted" in response.json()["detail"]
    assert coordinator.runs == []

    # A client that bypasses the API still cannot replace the rounds.
    flow = FlowDocument.find_one({"name": FLOW_NAME}).run()
    assert flow is not None
    run = {
        "parameters": {"username": USERNAME, "chip_id": CHIP_ID, "flow_name": FLOW_NAME},
        "context": {"qdash_target_override": {"qids": ["0", "1"]}},
    }
    with pytest.raises(ValueError, match="Target overrides are not accepted"):
        _run_dispatched_flow(flow.file_path, flow.flow_function_name, run, monkeypatch)
    assert workers.calls == []
