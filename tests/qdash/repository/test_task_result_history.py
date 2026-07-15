"""Tests for task result history repository persistence side effects."""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

from qdash.datamodel.execution import ExecutionModel, ExecutionStatusModel
from qdash.datamodel.system_info import SystemInfoModel
from qdash.datamodel.task import QubitTaskModel, TaskStatusModel
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
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


def test_task_result_document_preserves_quality_metrics() -> None:
    """Normalized quality metrics remain attached to authoritative task provenance."""
    task = _sample_task()
    task.quality_metrics = {"r2": 0.95}

    document = TaskResultHistoryDocument.from_datamodel(task, _sample_execution_model())

    assert document.quality_metrics == {"r2": 0.95}


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


def _insert_task_result_row(**overrides: Any) -> None:
    """Insert a raw task_result_history row (bypassing validation).

    Uses the raw collection so we can seed dirty/legacy values (e.g. a null
    ``upstream_id``) that would fail model validation on insert but exist in
    real historical data.
    """
    row: dict[str, Any] = {
        "project_id": "proj-1",
        "username": "test",
        "task_id": "task-" + str(overrides.get("_seq", 0)),
        "name": "CheckRabi",
        "upstream_id": "up-1",
        "status": "completed",
        "message": "",
        "input_parameters": {},
        "output_parameters": {},
        "output_parameter_names": [],
        "note": {},
        "figure_path": [],
        "start_at": None,
        "end_at": None,
        "elapsed_time": None,
        "task_type": "qubit",
        "system_info": SystemInfoModel().model_dump(),
        "qid": "0",
        "execution_id": "exec-1",
        "tags": [],
        "chip_id": "chip-1",
    }
    row.update({k: v for k, v in overrides.items() if k != "_seq"})
    TaskResultHistoryDocument.get_motor_collection().insert_one(row)


def test_find_latest_by_chip_and_qids_returns_one_latest_per_group(init_db) -> None:
    """Only the most recent task result per (qid, name) is returned."""
    dt = lambda d: datetime(2026, 1, d, tzinfo=timezone.utc)  # noqa: E731

    # Same (qid=0, name=CheckRabi): three runs -> only the latest (day 3) wins.
    _insert_task_result_row(_seq=1, qid="0", name="CheckRabi", end_at=dt(1))
    _insert_task_result_row(_seq=2, qid="0", name="CheckRabi", end_at=dt(3))  # latest
    _insert_task_result_row(_seq=3, qid="0", name="CheckRabi", end_at=dt(2))
    # A different (qid, name) group is kept independently.
    _insert_task_result_row(_seq=4, qid="1", name="CheckT1", end_at=dt(1))

    repo = MongoTaskResultHistoryRepository()
    results = repo.find_latest_by_chip_and_qids(
        project_id="proj-1",
        chip_id="chip-1",
        qids=["0", "1"],
        task_names=["CheckRabi", "CheckT1"],
    )

    by_group = {(r.qid, r.name): r for r in results}
    assert set(by_group) == {("0", "CheckRabi"), ("1", "CheckT1")}
    assert by_group[("0", "CheckRabi")].task_id == "task-2"  # the day-3 run


def test_find_latest_by_chip_and_qids_coerces_null_upstream_id(init_db) -> None:
    """Legacy rows with a null upstream_id parse instead of raising."""
    _insert_task_result_row(_seq=1, upstream_id=None, end_at=None)

    repo = MongoTaskResultHistoryRepository()
    results = repo.find_latest_by_chip_and_qids(
        project_id="proj-1",
        chip_id="chip-1",
        qids=["0"],
        task_names=["CheckRabi"],
    )

    assert len(results) == 1
    assert results[0].upstream_id == ""


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
