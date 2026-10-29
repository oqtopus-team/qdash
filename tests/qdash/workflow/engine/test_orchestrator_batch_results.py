"""Tests for CalibOrchestrator batch result extraction."""

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest

from qdash.datamodel.task import CalibDataModel, ParameterModel, TaskStatusModel
from qdash.workflow.engine.orchestrator import CalibOrchestrator
from qdash.workflow.engine.task.state_manager import TaskStateManager

if TYPE_CHECKING:
    from qdash.workflow.engine.task.context import TaskContext


def test_merge_and_extract_batch_results_includes_failed_task_status() -> None:
    orchestrator = object.__new__(CalibOrchestrator)
    orchestrator._last_executed_task_id_by_qid = {}
    orchestrator._published_names_by_task = {}
    orchestrator._published_name_owner = {}
    orchestrator._execution_service = None
    orchestrator._task_context = cast(
        "TaskContext",
        SimpleNamespace(state=SimpleNamespace(calib_data=CalibDataModel(qubit={}, coupling={}))),
    )

    tasks = {
        "0": SimpleNamespace(
            task_id="task-0",
            status=TaskStatusModel.FAILED,
            message="Qubit frequency too low for qid=0",
        ),
        "4": SimpleNamespace(
            task_id="task-4",
            status=TaskStatusModel.COMPLETED,
            message="Completed",
        ),
    }

    def get_task(*, task_name: str, task_type: str, qid: str) -> Any:
        assert task_name == "CheckSimultaneousQubitSpectroscopy"
        assert task_type == "qubit"
        return tasks[qid]

    def get_output_parameter_by_task_name(
        task_name: str, *, task_type: str, qid: str
    ) -> dict[str, Any]:
        assert task_name == "CheckSimultaneousQubitSpectroscopy"
        assert task_type == "qubit"
        return {"coarse_qubit_frequency": 5.0} if qid == "4" else {}

    executed_context = SimpleNamespace(
        calib_data=CalibDataModel(qubit={}, coupling={}),
        get_task=get_task,
        state=SimpleNamespace(
            get_output_parameter_by_task_name=get_output_parameter_by_task_name,
            get_published_parameter_names=lambda *_args: set(),
        ),
    )

    results = orchestrator._merge_and_extract_batch_results(
        cast("TaskContext", executed_context),
        "CheckSimultaneousQubitSpectroscopy",
        "qubit",
        ["0", "4"],
    )

    assert results["0"] == {
        "task_id": "task-0",
        "status": "failed",
        "error": "Qubit frequency too low for qid=0",
    }
    assert results["4"] == {
        "coarse_qubit_frequency": 5.0,
        "task_id": "task-4",
        "status": "success",
    }


def test_measurement_only_batch_does_not_update_workflow_calibration_state() -> None:
    orchestrator = object.__new__(CalibOrchestrator)
    orchestrator._last_executed_task_id_by_qid = {}
    orchestrator._published_names_by_task = {}
    orchestrator._published_name_owner = {}
    orchestrator._execution_service = None
    original = {"qubit_frequency": ParameterModel(value=5.0)}
    orchestrator._task_context = cast(
        "TaskContext",
        SimpleNamespace(
            state=SimpleNamespace(
                calib_data=CalibDataModel(qubit={"0": original.copy()}, coupling={})
            )
        ),
    )
    task = SimpleNamespace(
        task_id="task-0",
        status=TaskStatusModel.COMPLETED,
        message="Completed",
    )
    measured = {"qubit_frequency": ParameterModel(value=5.1)}
    measured_output = {"qubit_frequency": {"value": 5.1}}
    executed_context = SimpleNamespace(
        calib_data=CalibDataModel(qubit={"0": measured}, coupling={}),
        get_task=lambda **_kwargs: task,
        state=SimpleNamespace(
            get_output_parameter_by_task_name=lambda *_args, **_kwargs: measured_output.copy()
        ),
    )

    results = orchestrator._merge_and_extract_batch_results(
        cast("TaskContext", executed_context),
        "CheckChevron",
        "qubit",
        ["0"],
        update_calibration_parameters=False,
    )

    assert orchestrator.task_context.state.calib_data.qubit["0"]["qubit_frequency"].value == 5.0
    assert results["0"]["qubit_frequency"] == {"value": 5.1}


@pytest.mark.parametrize("batch", [False, True])
def test_successful_rerun_removes_only_aliases_still_owned_by_task(batch: bool) -> None:
    """A replacement output drops old aliases without deleting another task's value."""
    orchestrator = object.__new__(CalibOrchestrator)
    orchestrator._last_executed_task_id_by_qid = {}
    orchestrator._published_names_by_task = {}
    orchestrator._published_name_owner = {}
    parent_state = TaskStateManager(qids=["0"])
    orchestrator._task_context = cast("TaskContext", SimpleNamespace(state=parent_state))
    execution_data = CalibDataModel(qubit={"0": {}}, coupling={})
    orchestrator._execution_service = cast("Any", SimpleNamespace(calib_data=execution_data))

    def run(task_name: str, value: float, targets: tuple[str, ...]) -> None:
        child_state = TaskStateManager(qids=["0"])
        child_state.calib_data = parent_state.calib_data.model_copy(deep=True)
        child_state.put_output_parameters(
            task_name,
            {"measured": ParameterModel(value=value)},
            "qubit",
            "0",
            publish_targets={"measured": targets},
        )
        child_state.update_task_status_to_completed(task_name, "Completed", "qubit", "0")
        execution_data.qubit["0"].update(child_state.calib_data.qubit["0"])
        child_context = cast(
            "TaskContext",
            SimpleNamespace(
                state=child_state,
                calib_data=child_state.calib_data,
                get_task=lambda **_kwargs: child_state.get_task(task_name, "qubit", "0"),
            ),
        )
        if batch:
            orchestrator._merge_and_extract_batch_results(child_context, task_name, "qubit", ["0"])
        else:
            orchestrator._merge_and_extract_results(child_context, task_name, "qubit", "0")

    run("TaskA", 4.2, ("old_alias", "shared_alias"))
    run("TaskB", 5.0, ("shared_alias", "other_alias"))
    run("TaskA", 4.3, ("new_alias",))
    run("TaskA", 4.4, ("new_alias",))

    calib = parent_state.calib_data.qubit["0"]
    assert set(calib) == {"shared_alias", "other_alias", "new_alias"}
    assert calib["shared_alias"].value == 5.0
    assert calib["new_alias"].value == 4.4
    assert set(execution_data.qubit["0"]) == set(calib)
