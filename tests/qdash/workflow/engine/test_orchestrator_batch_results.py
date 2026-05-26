"""Tests for CalibOrchestrator batch result extraction."""

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

from qdash.datamodel.task import CalibDataModel, TaskStatusModel
from qdash.workflow.engine.orchestrator import CalibOrchestrator

if TYPE_CHECKING:
    from qdash.workflow.engine.task.context import TaskContext


def test_merge_and_extract_batch_results_includes_failed_task_status() -> None:
    orchestrator = object.__new__(CalibOrchestrator)
    orchestrator._last_executed_task_id_by_qid = {}
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
        state=SimpleNamespace(get_output_parameter_by_task_name=get_output_parameter_by_task_name),
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
