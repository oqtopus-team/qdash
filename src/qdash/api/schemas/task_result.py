"""Schema definitions for task_result router."""

from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator
from qdash.api.lib.copilot_config import ModelConfig
from qdash.common.datetime_utils import format_elapsed_time, parse_elapsed_time
from qdash.datamodel.note import AiTriageReviewModel
from qdash.datamodel.task import ParameterModel


class TaskResult(BaseModel):
    """TaskResult is a Pydantic model that represents a task result."""

    task_id: str | None = None
    qid: str | None = None
    name: str = ""  # Default empty string for name
    upstream_id: str | None = None
    status: str = "pending"  # Default status
    message: str | None = None
    input_parameters: dict[str, Any] | None = None
    output_parameters: dict[str, Any] | None = None
    output_parameter_names: list[str] | None = None
    run_parameters: dict[str, Any] | None = None
    note: dict[str, Any] | None = None
    figure_path: list[str] | None = None
    json_figure_path: list[str] | None = None
    raw_data_path: list[str] | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    elapsed_time: timedelta | None = None
    task_type: str | None = None
    default_view: bool = True
    ai_triage: AiTriageReviewModel | None = None

    @field_validator("elapsed_time", mode="before")
    @classmethod
    def _parse_elapsed_time(cls, v: Any) -> timedelta | None:
        """Parse elapsed_time from various formats."""
        return parse_elapsed_time(v)

    @field_serializer("elapsed_time")
    @classmethod
    def _serialize_elapsed_time(cls, v: timedelta | None) -> str | None:
        """Serialize elapsed_time to H:MM:SS format."""
        return format_elapsed_time(v) if v else None


class LatestTaskResultResponse(BaseModel):
    """Response model for fetching the latest tasks grouped by qid/coupling_id."""

    task_name: str
    result: dict[str, TaskResult]


class TaskHistoryResponse(BaseModel):
    """Response model for fetching task history."""

    name: str
    data: dict[str, TaskResult]


class TimeSeriesProjection(BaseModel):
    """Projection model for time series data query."""

    qid: str
    output_parameters: dict[str, Any]
    start_at: datetime


class TimeSeriesData(BaseModel):
    """Response model for time series data."""

    data: dict[str, list[ParameterModel]] = {}

    model_config = ConfigDict(arbitrary_types_allowed=True)


class TaskResultExcludeRequest(BaseModel):
    """Request body for toggling exclusion on a task result."""

    excluded: bool
    reason: str = ""


class TaskResultExcludeResponse(BaseModel):
    """Response after toggling exclusion on a task result."""

    task_id: str
    excluded: bool
    excluded_reason: str
    excluded_by_user_id: str | None = None
    excluded_by: str | None
    excluded_at: datetime | None


class BulkAiTriageRequest(BaseModel):
    """Request body for bulk AI triage review."""

    model_config = ConfigDict(protected_namespaces=())

    chip_id: str
    task: str
    entity_type: str = "qubit"
    date: str | None = None
    task_ids: list[str] | None = None
    model_override: ModelConfig | None = None


class BulkAiTriageResponse(BaseModel):
    """Response after enqueueing bulk AI triage review."""

    chip_id: str
    task: str
    entity_type: str
    date: str | None = None
    requested_count: int
    task_ids: list[str]
    skipped_reason: str | None = None


class DownloadFiguresAsZipRequest(BaseModel):
    """Request body for downloading task-result artifacts as a ZIP archive."""

    paths: list[str] = []
    filename: str = "figures.zip"
    ai_triage_task_ids: list[str] = []
