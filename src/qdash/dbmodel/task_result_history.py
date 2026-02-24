from datetime import datetime, timedelta
from typing import Any, ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field, field_validator
from pymongo import ASCENDING, DESCENDING, IndexModel
from qdash.common.datetime_utils import ensure_timezone, parse_elapsed_time
from qdash.datamodel.execution import ExecutionModel
from qdash.datamodel.system_info import SystemInfoModel
from qdash.datamodel.task import BaseTaskResultModel


class TaskResultHistoryDocument(Document):
    """Document for storing execution history.

    Attributes
    ----------
        project_id (str): The owning project identifier.
        execution_id (str): The execution ID. e.g. "0".
        status (str): The status of the execution. e.g. "completed".
        tasks (dict): The tasks of the execution. e.g. {"task1": "completed"}.
        calib_data (dict): The calibration data. e.g. {"qubit": {"0":{"qubit_frequency": 5.0}}, "coupling": {"0-1": {"coupling_strength": 0.1}}}.

        note (str): The note. e.g. "This is a note".
        tags (list[str]): The tags. e.g. ["tag1", "tag2"].
        message (str): The message. e.g. "This is a message".
        start_at (datetime): The time when the execution started.
        end_at (datetime): The time when the execution ended.
        elapsed_time (timedelta): The elapsed time.
        system_info (SystemInfoModel): The system information.

    """

    project_id: str | None = Field(None, description="Owning project identifier")
    username: str = Field(..., description="The username of the user who created the task")
    task_id: str = Field(..., description="The task ID")
    name: str = Field(..., description="The task name")
    upstream_id: str = Field(..., description="The upstream task ID")
    status: str = Field(..., description="The status of the execution")
    message: str = Field(..., description="The message")
    input_parameters: dict[str, Any] = Field(..., description="The input parameters")
    output_parameters: dict[str, Any] = Field(..., description="The output parameters")
    output_parameter_names: list[str] = Field(..., description="The output parameter names")
    run_parameters: dict[str, Any] = Field(default_factory=dict, description="The run parameters")
    note: dict[str, Any] = Field(..., description="The note")
    figure_path: list[str] = Field(..., description="The path to the figure")
    json_figure_path: list[str] = Field([], description="The path to the JSON figure")
    raw_data_path: list[str] = Field([], description="The path to the raw data")
    start_at: datetime | None = Field(..., description="The time when the execution started")
    end_at: datetime | None = Field(..., description="The time when the execution ended")
    elapsed_time: float | None = Field(..., description="The elapsed time in seconds")
    task_type: str = Field(..., description="The task type")
    system_info: SystemInfoModel = Field(..., description="The system information")
    qid: str = Field("", description="The qubit ID")

    execution_id: str = Field(..., description="The execution ID")
    tags: list[str] = Field(..., description="The tags")
    chip_id: str = Field(..., description="The chip ID")

    source_task_id: str | None = Field(
        None,
        description="Task result ID that triggered this re-execution (cross-reference to parent)",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )

    @field_validator("start_at", "end_at", mode="before")
    @classmethod
    def _ensure_timezone(cls, v: Any) -> datetime | Any:
        """Ensure datetime fields are timezone-aware."""
        if v is None:
            return None
        if isinstance(v, datetime):
            return ensure_timezone(v)
        # For other inputs (e.g., strings), let pydantic handle the conversion
        return v

    @field_validator("elapsed_time", mode="before")
    @classmethod
    def _parse_elapsed_time(cls, v: Any) -> float | None:
        """Parse elapsed_time from various formats and return seconds."""
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, timedelta):
            return v.total_seconds()
        td = parse_elapsed_time(v)
        return td.total_seconds() if td else None

    class Settings:
        """Settings for the document."""

        name = "task_result_history"
        indexes: ClassVar = [
            # Primary indexes
            IndexModel([("project_id", ASCENDING), ("task_id", ASCENDING)], unique=True),
            IndexModel([("project_id", ASCENDING), ("execution_id", ASCENDING)]),
            IndexModel(
                [("project_id", ASCENDING), ("chip_id", ASCENDING), ("start_at", DESCENDING)]
            ),
            # Index for latest task result queries (task_result.py: get_latest_*_task_results)
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("chip_id", ASCENDING),
                    ("name", ASCENDING),
                    ("qid", ASCENDING),
                    ("end_at", DESCENDING),
                ]
            ),
            # Index for metrics history queries (metrics.py: get_*_metric_history)
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("chip_id", ASCENDING),
                    ("task_type", ASCENDING),
                    ("qid", ASCENDING),
                    ("start_at", DESCENDING),
                ]
            ),
            # Index for timeseries queries (task_result.py: get_timeseries_task_results)
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("chip_id", ASCENDING),
                    ("tags", ASCENDING),
                    ("start_at", ASCENDING),
                ]
            ),
            # Index for metrics aggregation queries (metrics.py: aggregate_*_metrics)
            IndexModel(
                [
                    ("chip_id", ASCENDING),
                    ("username", ASCENDING),
                    ("task_type", ASCENDING),
                    ("status", ASCENDING),
                    ("start_at", DESCENDING),
                ]
            ),
            # Index for re-execution cross-reference queries
            IndexModel(
                [("project_id", ASCENDING), ("source_task_id", ASCENDING)],
                sparse=True,
            ),
        ]

    @classmethod
    def from_datamodel(
        cls, task: BaseTaskResultModel, execution_model: ExecutionModel
    ) -> "TaskResultHistoryDocument":
        return cls(
            project_id=execution_model.project_id,
            username=execution_model.username,
            task_id=task.task_id,
            name=task.name,
            upstream_id=task.upstream_id,
            status=task.status,
            message=task.message,
            input_parameters=task.input_parameters,
            output_parameters=task.output_parameters,
            output_parameter_names=task.output_parameter_names,
            run_parameters=task.run_parameters,
            note=task.note,
            figure_path=task.figure_path,
            json_figure_path=task.json_figure_path,
            raw_data_path=task.raw_data_path,
            start_at=task.start_at,
            end_at=task.end_at,
            elapsed_time=task.elapsed_time,
            task_type=task.task_type,
            system_info=task.system_info.model_dump(),
            qid=getattr(task, "qid", ""),
            execution_id=execution_model.execution_id,
            tags=execution_model.tags,
            chip_id=execution_model.chip_id,
        )

    @classmethod
    def upsert_document(
        cls, task: BaseTaskResultModel, execution_model: ExecutionModel
    ) -> "TaskResultHistoryDocument":
        doc = cls.find_one(
            {"project_id": execution_model.project_id, "task_id": task.task_id}
        ).run()
        if doc is None:
            doc = cls.from_datamodel(task=task, execution_model=execution_model)
            doc.save()
            return doc
        doc.project_id = execution_model.project_id
        doc.username = execution_model.username
        doc.name = task.name
        doc.upstream_id = task.upstream_id
        doc.status = task.status
        doc.message = task.message
        doc.input_parameters = task.input_parameters
        doc.output_parameters = task.output_parameters
        doc.output_parameter_names = task.output_parameter_names
        doc.run_parameters = task.run_parameters
        doc.note = task.note
        doc.figure_path = task.figure_path
        doc.json_figure_path = task.json_figure_path
        doc.raw_data_path = task.raw_data_path
        doc.start_at = task.start_at
        doc.end_at = task.end_at
        doc.elapsed_time = task.elapsed_time.total_seconds() if task.elapsed_time else None
        doc.task_type = task.task_type
        doc.system_info = task.system_info
        doc.qid = getattr(task, "qid", "")
        doc.execution_id = execution_model.execution_id
        doc.tags = execution_model.tags
        doc.chip_id = execution_model.chip_id
        doc.save()
        return doc
