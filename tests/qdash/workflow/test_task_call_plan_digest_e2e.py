"""The API's spec digest and the worker's plan digest link every task result of a run.

Two digests describe a pipeline run, and they are deliberately different values:

* ``plan_digest`` from ``POST /calibration-pipelines/validate`` is the digest of the
  normalized spec. The worker re-validates the dispatched spec and stores the same
  value as ``note.pipeline.spec_digest`` on every step Execution.
* ``note.calibration_plan.digest`` is the digest of the plan the worker resolved from
  that spec (step ids, normalized calls, per-task defaults, shared run defaults). Every
  task result's ``invocation.plan_digest`` is this value, including results recorded by
  isolated worker sessions.

This test runs the API-normalized spec through the real ``calibration_pipeline`` flow
on the fake backend with the in-memory MongoDB of ``tests/conftest.py``. The scheduled
1Q mode fans out to isolated worker sessions; here the fan-out runs in-process, with
the step plan and session configuration pickled on the way as Dask would.
"""

from __future__ import annotations

import json
import pickle
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from tests.qdash.workflow.test_fake_chip_preset import (  # noqa: F401 - pytest fixtures
    CHIP_ID,
    HEADERS,
    PROJECT_ID,
    USERNAME,
    _create_fake_chip,
    fake_deployment,
    project,
)

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

# ``fake_deployment`` changes the working directory, so name the task catalog explicitly.
CALIBTASKS = Path(__file__).resolve().parents[3] / "src" / "qdash" / "workflow" / "calibtasks"

SPEC: dict[str, Any] = {
    "spec_version": 2,
    "name": "digest-link",
    "targets": {"qids": ["0", "1"]},
    "task_parameters": {"CheckRabi": {"run": {"shots": 256}}},
    "steps": [
        {
            "type": "CustomOneQubit",
            "step_name": "prepare",
            "mode": "serial",
            "tasks": [{"name": "FakeBringUp"}],
        },
        {
            "type": "CustomOneQubit",
            "step_name": "rabi_twice",
            "mode": "scheduled",
            "tasks": [
                {"name": "CheckRabi", "call_id": "rabi_first"},
                {"name": "CheckRabi", "call_id": "rabi_again", "run": {"shots": 512}},
            ],
        },
    ],
}


@pytest.fixture
def isolated_workers(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Run the scheduled fan-out in-process; record each plan a worker received."""
    from qdash.workflow.service import strategy
    from qdash.workflow.service._internal import scheduling_tasks

    received: list[Any] = []

    def _across_process(plan: Any, worker: Any) -> tuple[Any, Any]:
        plan = pickle.loads(pickle.dumps(plan))  # noqa: S301 - our own object, as Dask does
        received.append(plan)
        return plan, pickle.loads(pickle.dumps(worker))  # noqa: S301

    def mux_parallel(*, mux_groups: list[list[str]], plan: Any, worker: Any) -> Any:
        results: dict[str, Any] = {}
        for group in mux_groups:
            worker_plan, config = _across_process(plan, worker)
            results.update(scheduling_tasks.calibrate_mux_qubits(group, worker_plan, config))
        return results

    def qubit_parallel(*, qids: list[str], plan: Any, worker: Any) -> Any:
        results: dict[str, Any] = {}
        for qid in qids:
            worker_plan, config = _across_process(plan, worker)
            target, result = scheduling_tasks.calibrate_single_qubit(qid, worker_plan, config)
            results[target] = result
        return results

    monkeypatch.setattr(strategy, "run_mux_calibrations_parallel", mux_parallel)
    monkeypatch.setattr(strategy, "run_qubit_calibrations_parallel", qubit_parallel)
    return received


def test_spec_digest_and_plan_digest_are_linked_on_every_execution_and_result(
    project: None,  # noqa: F811
    fake_deployment: Path,  # noqa: F811
    test_client: TestClient,
    isolated_workers: list[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from qdash.workflow.service.pipeline_flow import calibration_pipeline

    monkeypatch.setenv("CALIB_TASKS_PATH", str(CALIBTASKS))
    _create_fake_chip(test_client)
    response = test_client.post(
        "/calibration-pipelines/validate",
        headers=HEADERS,
        json={"chip_id": CHIP_ID, "spec": SPEC, "backend_name": "fake"},
    )
    assert response.status_code == 200
    validation = response.json()
    assert validation["valid"], validation["problems"]
    api_digest = validation["plan_digest"]

    # The execute endpoint dispatches the normalized spec as a JSON flow parameter.
    dispatched = json.loads(json.dumps(validation["spec"]))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        calibration_pipeline(
            USERNAME,
            CHIP_ID,
            spec=dispatched,
            project_id=PROJECT_ID,
            backend_name="fake",
        )
    # The spec's deprecated task_parameters is reported by validation, not
    # re-warned by the worker, the parent session or isolated worker sessions.
    assert not [w for w in caught if "task_parameters is deprecated" in str(w.message)]

    executions = list(
        ExecutionHistoryDocument.find({"project_id": PROJECT_ID, "chip_id": CHIP_ID}).run()
    )
    step_executions = {doc.note["step_id"]: doc for doc in executions if "step_id" in doc.note}
    assert set(step_executions) == {"prepare", "rabi_twice"}

    # Every step Execution names the API's spec digest and the worker's plan digest.
    spec_digests = {doc.note["pipeline"]["spec_digest"] for doc in step_executions.values()}
    plan_digests = {doc.note["calibration_plan"]["digest"] for doc in step_executions.values()}
    assert spec_digests == {api_digest}
    assert len(plan_digests) == 1
    [plan_digest] = plan_digests
    # Distinct versions: the plan adds resolved call ids and the per-task defaults.
    assert plan_digest != api_digest
    plan = step_executions["rabi_twice"].note["calibration_plan"]
    assert [call["call_id"] for call in plan["steps"][1]["calls"]] == ["rabi_first", "rabi_again"]
    assert plan["task_parameters"]["CheckRabi"]["run"]["shots"] == {"value": 256}

    # The scheduled step really went through isolated workers, which kept the digest.
    assert isolated_workers
    assert {worker_plan.plan_digest for worker_plan in isolated_workers} == {plan_digest}
    assert {worker_plan.step_id for worker_plan in isolated_workers} == {"rabi_twice"}

    results = list(
        TaskResultHistoryDocument.find({"project_id": PROJECT_ID, "chip_id": CHIP_ID}).run()
    )
    rabi = [doc for doc in results if doc.name == "CheckRabi"]
    assert len(rabi) == 4
    assert all(doc.invocation is not None for doc in results)
    assert {doc.invocation.plan_digest for doc in results if doc.invocation} == {plan_digest}
    assert {
        (doc.qid, doc.invocation.step_id, doc.invocation.call_id) for doc in rabi if doc.invocation
    } == {
        (qid, "rabi_twice", call_id)
        for qid in ("0", "1")
        for call_id in ("rabi_first", "rabi_again")
    }
    # Each result is recorded under the step Execution whose note holds that plan.
    assert {doc.execution_id for doc in rabi} == {step_executions["rabi_twice"].execution_id}
    shots = {
        doc.invocation.call_id: doc.run_parameters["shots"]["value"]
        for doc in rabi
        if doc.invocation
    }
    assert shots == {"rabi_first": 256, "rabi_again": 512}
