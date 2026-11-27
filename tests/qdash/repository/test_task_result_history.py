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


def test_task_result_document_preserves_quality_metrics(init_db) -> None:
    """Normalized quality metrics remain attached to authoritative task provenance."""
    task = _sample_task()
    task.quality_metrics = {"r2": 0.95}

    document = TaskResultHistoryDocument.from_datamodel(task, _sample_execution_model())

    assert document.quality_metrics == {"r2": 0.95}


@patch("qdash.repository.task_result_history.TaskResultHistoryDocument")
def test_save_upserts_document(mock_document: MagicMock) -> None:
    """Repository save persists the task result through the document upsert."""
    task = _sample_task()
    execution_model = _sample_execution_model()

    MongoTaskResultHistoryRepository().save(task, execution_model)

    mock_document.upsert_document.assert_called_once_with(
        task=task,
        execution_model=execution_model,
    )


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


def test_find_accepts_a_query_time_limit_inside_a_pymongo_timeout(init_db) -> None:
    """``max_time_ms`` and a ``pymongo.timeout`` block leave the results unchanged.

    mongomock ignores both; this only checks that the metric broker's bounded query runs.
    """
    import pymongo
    from bunnet import SortDirection

    _insert_task_result_row(_seq=1, start_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
    _insert_task_result_row(_seq=2, start_at=datetime(2026, 1, 1, tzinfo=timezone.utc))

    repo = MongoTaskResultHistoryRepository()
    with pymongo.timeout(1.0):
        results = repo.find(
            {"project_id": "proj-1", "chip_id": "chip-1"},
            sort=[("start_at", SortDirection.ASCENDING)],
            limit=10,
            max_time_ms=1000,
        )

    assert [r.task_id for r in results] == ["task-2", "task-1"]


def test_metric_aggregations_share_the_completed_result_match_stage() -> None:
    cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 2, tzinfo=timezone.utc)
    pipelines: list[list[dict[str, Any]]] = []

    def record(pipeline: list[dict[str, Any]]) -> MagicMock:
        pipelines.append(pipeline)
        query = MagicMock()
        query.run.return_value = []
        return query

    repo = MongoTaskResultHistoryRepository()
    common = {
        "chip_id": "chip-1",
        "project_id": "project-1",
        "entity_type": "qubit",
        "cutoff_time": cutoff,
        "end_time": end,
    }
    with patch.object(TaskResultHistoryDocument, "aggregate", side_effect=record):
        repo.aggregate_latest_metrics(metric_keys={"t1"}, **common)  # type: ignore[arg-type]
        repo.aggregate_average_metrics(metric_keys={"t1"}, **common)  # type: ignore[arg-type]
        repo.aggregate_best_metrics(metric_modes={"t1": "maximize"}, **common)  # type: ignore[arg-type]

    expected = {
        "chip_id": "chip-1",
        "project_id": "project-1",
        "task_type": "qubit",
        "status": "completed",
        "excluded": {"$ne": True},
        "$or": [{"output_parameters.t1": {"$exists": True}}],
        "start_at": {"$gte": cutoff, "$lte": end},
    }
    assert [pipeline[0] for pipeline in pipelines] == [{"$match": expected}] * 3


def test_latest_fh_and_harmonic_metrics_keep_their_own_measurement_and_uncertainty(init_db) -> None:
    _insert_task_result_row(
        _seq=1,
        start_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        output_parameters={
            "fh_frequency": {"value": 4.5},
            "josephson_energy_second_harmonic": {"value": -0.15, "error": 0},
        },
    )
    _insert_task_result_row(
        _seq=2,
        start_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        output_parameters={"fh_frequency": {"value": 4.51, "error": 0.001}},
    )

    metrics = MongoTaskResultHistoryRepository().aggregate_latest_metrics(
        chip_id="chip-1",
        project_id="proj-1",
        entity_type="qubit",
        metric_keys={"fh_frequency", "josephson_energy_second_harmonic"},
    )

    fh = metrics["fh_frequency"]["0"]
    assert (fh["value"], fh["task_id"], fh["stddev"]) == (4.51, "task-2", 0.001)
    ej2 = metrics["josephson_energy_second_harmonic"]["0"]
    assert (ej2["value"], ej2["task_id"], ej2["stddev"]) == (-0.15, "task-1", 0.0)
