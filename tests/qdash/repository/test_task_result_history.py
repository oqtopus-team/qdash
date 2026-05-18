"""Tests for task result history repository persistence side effects."""

from unittest.mock import MagicMock, patch

from qdash.datamodel.execution import ExecutionModel, ExecutionStatusModel
from qdash.datamodel.system_info import SystemInfoModel
from qdash.datamodel.task import QubitTaskModel, TaskStatusModel
from qdash.repository.task_result_history import MongoTaskResultHistoryRepository


def _sample_task() -> QubitTaskModel:
    return QubitTaskModel(
        name="CheckQubitSpectroscopy",
        qid="0",
        status=TaskStatusModel.COMPLETED,
    )


def _sample_execution_model() -> ExecutionModel:
    return ExecutionModel(
        username="test",
        name="test-execution",
        execution_id="test-exec-001",
        chip_id="test-chip",
        calib_data_path="/tmp/calib",
        tags=[],
        note={},
        status=ExecutionStatusModel.RUNNING,
        start_at=None,
        end_at=None,
        elapsed_time=None,
        message="",
        system_info=SystemInfoModel(),
    )


@patch("qdash.workflow.engine.task.ai_review.enqueue_ai_review_note")
@patch("qdash.repository.task_result_history.TaskResultHistoryDocument")
def test_save_attaches_ai_review_after_upsert(
    mock_document: MagicMock,
    mock_ai_review: MagicMock,
) -> None:
    """Repository save triggers AI review after task result persistence."""
    task = _sample_task()
    execution_model = _sample_execution_model()

    MongoTaskResultHistoryRepository().save(task, execution_model)

    mock_document.upsert_document.assert_called_once_with(
        task=task,
        execution_model=execution_model,
    )
    mock_ai_review.assert_called_once_with(task, execution_model)


@patch("qdash.workflow.engine.task.ai_review.enqueue_ai_review_note")
@patch("qdash.repository.task_result_history.TaskResultHistoryDocument")
def test_save_continues_when_ai_review_fails(
    mock_document: MagicMock,
    mock_ai_review: MagicMock,
) -> None:
    """AI review failures do not fail task result persistence."""
    task = _sample_task()
    execution_model = _sample_execution_model()
    mock_ai_review.side_effect = Exception("AI review error")

    MongoTaskResultHistoryRepository().save(task, execution_model)

    mock_document.upsert_document.assert_called_once_with(
        task=task,
        execution_model=execution_model,
    )
