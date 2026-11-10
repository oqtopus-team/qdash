"""One step runs the same task twice per qubit, end to end on the fake backend.

The pipeline runs on a fake chip created through the API, with the in-memory
MongoDB of ``tests/conftest.py`` and the suite's Prefect stub, so every task is
the production qubex implementation executed in-process against the simulator.
Serial mode keeps the run in the parent session (no Dask workers).

The ``ramsey`` step calls ``CheckRamsey`` twice on qubits 0 and 1: a coarse call
and a fine call with a different detuning and time range. The fine call is
made to fail its quality check on qubit 1. The test then checks, from the
stored task results and the pipeline result, that each call ran as its own
task with its own settings, that only the accepted call's values reached the
calibration database, that a filter on the fine call drops qubit 1 even though
its coarse call succeeded, and that replaying the step execution restores each
call's own recorded settings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from qdash.datamodel.task_call import TaskCall
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.workflow import sweep
from tests.qdash.workflow.test_fake_chip_preset import (  # noqa: F401 - pytest fixtures
    CHIP_ID,
    PROJECT_ID,
    USERNAME,
    _create_fake_chip,
    fake_deployment,
    project,
)

if TYPE_CHECKING:
    from pathlib import Path

    from fastapi.testclient import TestClient

QIDS = ["0", "1"]
COARSE = {"detuning": 0.001, "time_range": sweep.arange(0, 10_001, 100)}
FINE = {"detuning": 0.0002, "time_range": sweep.arange(0, 50_001, 500)}


def _results(**query: Any) -> list[TaskResultHistoryDocument]:
    return list(
        TaskResultHistoryDocument.find({"project_id": PROJECT_ID, "chip_id": CHIP_ID, **query})
        .sort("start_at")
        .run()
    )


def _qubit_data(qid: str) -> dict[str, Any]:
    qubit = QubitDocument.find_one({"project_id": PROJECT_ID, "chip_id": CHIP_ID, "qid": qid}).run()
    assert qubit is not None
    return dict(qubit.data)


def _fail_fine_ramsey_on(monkeypatch: pytest.MonkeyPatch, failing_qid: str) -> None:
    """Make the fine CheckRamsey call fail its quality check on one qubit."""
    from qdash.workflow.calibtasks.qubex.one_qubit_coarse.check_ramsey import CheckRamsey

    original = CheckRamsey.postprocess

    def postprocess(self: Any, backend: Any, execution_id: str, run_result: Any, qid: str) -> Any:
        result = original(self, backend, execution_id, run_result, qid)
        detuning = self.run_parameters["detuning"].get_value()
        if qid == failing_qid and detuning == FINE["detuning"]:
            result.validation_error = "fine Ramsey fit rejected"
        return result

    monkeypatch.setattr(CheckRamsey, "postprocess", postprocess)


def _service() -> Any:
    from qdash.workflow.service import CalibService, resolve_calib_context

    # The public direct-Python path: a checked context on the fake backend.
    context = resolve_calib_context(USERNAME, CHIP_ID, project_id=PROJECT_ID, backend="fake")
    return CalibService.from_context(
        context, flow_name="ramsey_twice", default_run_parameters={"shots": 256}
    )


def _steps() -> list[Any]:
    from qdash.workflow.service.steps import CustomOneQubit, FilterByMetric

    return [
        CustomOneQubit(
            step_name="prepare",
            mode="serial",
            tasks=[
                TaskCall(name="FakeBringUp"),
                TaskCall(name="CheckRabi"),
                TaskCall(name="CreateHPIPulse"),
                TaskCall(name="CreatePIPulse"),
            ],
        ),
        CustomOneQubit(
            step_name="ramsey",
            mode="serial",
            continue_on_failure=True,
            tasks=[
                TaskCall(name="CheckRamsey", call_id="ramsey_coarse", run=COARSE),
                TaskCall(name="CheckRamsey", call_id="ramsey_fine", run=FINE),
            ],
        ),
        FilterByMetric(step="ramsey", call_id="ramsey_fine", metric="t2_star", threshold=0.0),
        CustomOneQubit(step_name="after_filter", mode="serial", tasks=[TaskCall(name="CheckT1")]),
    ]


def test_repeated_calls_in_one_step_are_traceable_end_to_end(
    project: None,  # noqa: F811
    fake_deployment: Path,  # noqa: F811
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from qdash.workflow.service.targets import QubitTargets

    _create_fake_chip(test_client)
    _fail_fine_ramsey_on(monkeypatch, failing_qid="1")

    service = _service()
    result = service.run(QubitTargets(qids=QIDS), steps=_steps())

    # --- one task result per call and qubit, each with its own runtime task_id
    ramsey = _results(name="CheckRamsey")
    assert len(ramsey) == 4
    assert len({doc.task_id for doc in ramsey}) == 4
    by_call = {(doc.qid, doc.invocation.call_id): doc for doc in ramsey if doc.invocation}
    assert set(by_call) == {
        (qid, call) for qid in QIDS for call in ("ramsey_coarse", "ramsey_fine")
    }
    digests = {doc.invocation.plan_digest for doc in ramsey if doc.invocation}
    assert len(digests) == 1 and None not in digests
    assert {doc.invocation.step_id for doc in ramsey if doc.invocation} == {"ramsey"}

    for qid in QIDS:
        coarse = by_call[(qid, "ramsey_coarse")]
        fine = by_call[(qid, "ramsey_fine")]
        # Each call ran with its own settings over the shared run default.
        assert coarse.run_parameters["detuning"]["value"] == COARSE["detuning"]
        assert fine.run_parameters["detuning"]["value"] == FINE["detuning"]
        assert list(fine.run_parameters["time_range"]["value"]) == [0, 50_001, 500]
        assert coarse.run_parameters["shots"]["value"] == 256
        assert fine.run_parameters["shots"]["value"] == 256
        assert fine.invocation is not None and fine.invocation.settings is not None
        assert fine.invocation.settings["run"]["detuning"] == {"value": FINE["detuning"]}
        # The second call follows the first on the same qubit.
        assert fine.upstream_id == coarse.task_id
        assert coarse.status == "completed"
        # The coarse call's accepted qubit_frequency is the fine call's control frequency.
        assert fine.input_parameters["control_frequency"]["value"] == pytest.approx(
            coarse.output_parameters["qubit_frequency"]["value"]
        )
        assert fine.input_parameters["control_frequency"]["task_id"] == coarse.task_id

    assert by_call[("0", "ramsey_fine")].status == "completed"
    assert by_call[("1", "ramsey_fine")].status == "failed"
    assert "fine Ramsey fit rejected" in by_call[("1", "ramsey_fine")].message

    # --- only accepted writes reach the calibration database
    for qid, accepted_call in (("0", "ramsey_fine"), ("1", "ramsey_coarse")):
        stored = _qubit_data(qid)["t2_star"]
        assert stored["task_id"] == by_call[(qid, accepted_call)].task_id

    # --- the step result keeps both calls of each qubit, in order
    step_result = result["steps"]["ramsey"]
    for qid in QIDS:
        calls = step_result.get_qubit(qid).calls
        assert [call.call_id for call in calls] == ["ramsey_coarse", "ramsey_fine"]
        assert [call.task_id for call in calls] == [
            by_call[(qid, "ramsey_coarse")].task_id,
            by_call[(qid, "ramsey_fine")].task_id,
        ]
    assert [call.status for call in step_result.get_qubit("1").calls] == ["success", "failed"]
    assert step_result.get_qubit("0").status == "success"
    assert step_result.get_qubit("1").status == "failed"

    # --- the same lossless record is in the step Execution's stage results
    ramsey_execution = ExecutionHistoryDocument.find_one(
        {
            "project_id": PROJECT_ID,
            "chip_id": CHIP_ID,
            "execution_id": by_call[("0", "ramsey_coarse")].execution_id,
        }
    ).run()
    assert ramsey_execution is not None
    note = ramsey_execution.note
    assert note["step_id"] == "ramsey"
    plan = note["calibration_plan"]
    assert plan["digest"] in digests
    assert [call["call_id"] for call in plan["steps"][1]["calls"]] == [
        "ramsey_coarse",
        "ramsey_fine",
    ]
    stage = note["stage_results"]["1q_serial"]["result"]
    assert [call["call_id"] for call in stage["1"]["calls"]] == ["ramsey_coarse", "ramsey_fine"]

    # --- the filter on the fine call drops qubit 1 although its coarse call succeeded
    assert result["candidate_qids"] == ["0"]
    [ramsey_filter] = result["filters"]
    assert ramsey_filter.output_qids == ["0"]
    assert "ramsey.ramsey_fine" in ramsey_filter.filter_criteria
    assert [doc.qid for doc in _results(name="CheckT1")] == ["0"]

    # --- replaying the step execution restores each call's own recorded settings
    from qdash.workflow.service.steps import CustomOneQubit
    from qdash.workflow.service.targets import QubitTargets as Targets

    # A flow that declares source_execution_id restores from it, as the flow run
    # parameter would supply it.
    monkeypatch.setattr(
        "qdash.workflow.service._internal.runs.read_source_execution_id_from_context",
        lambda: ramsey_execution.execution_id,
    )
    replay = _service()
    replay.run(
        Targets(qids=["0"]),
        steps=[
            CustomOneQubit(
                step_name="ramsey",
                mode="serial",
                continue_on_failure=True,
                # No run settings: the snapshot of each call supplies them.
                tasks=[
                    TaskCall(name="CheckRamsey", call_id="ramsey_coarse"),
                    TaskCall(name="CheckRamsey", call_id="ramsey_fine"),
                ],
            )
        ],
    )
    replayed = [
        doc
        for doc in _results(name="CheckRamsey", qid="0")
        if doc.execution_id != ramsey_execution.execution_id
    ]
    restored = {doc.invocation.call_id: doc for doc in replayed if doc.invocation}
    assert set(restored) == {"ramsey_coarse", "ramsey_fine"}
    assert restored["ramsey_coarse"].run_parameters["detuning"]["value"] == COARSE["detuning"]
    assert restored["ramsey_fine"].run_parameters["detuning"]["value"] == FINE["detuning"]
