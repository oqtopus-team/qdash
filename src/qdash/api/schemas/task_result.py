"""Schema definitions for task_result router."""

from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator

from qdash.common.utils.datetime import format_elapsed_time, parse_elapsed_time
from qdash.copilot.config import ModelConfig
from qdash.datamodel.note import AiReviewModel
from qdash.datamodel.task import ParameterModel


class TaskResult(BaseModel):
    """TaskResult is a Pydantic model that represents a task result."""

    task_id: str | None = None
    execution_id: str | None = None
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
    ai_review: AiReviewModel | None = None

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


class TaskResultListItem(BaseModel):
    """Compact task result row for investigation lists."""

    task_id: str
    task_name: str
    qid: str
    chip_id: str
    status: str
    execution_id: str
    user_id: str | None = None
    username: str = ""
    message: str = ""
    has_stack_trace: bool = False
    source_task_id: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    elapsed_time: timedelta | None = None
    ai_review_status: str = ""

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


class TaskResultListResponse(BaseModel):
    """Paginated task result list response."""

    items: list[TaskResultListItem]
    total: int
    skip: int
    limit: int
    status_counts: dict[str, int]


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


class BulkAiReviewRequest(BaseModel):
    """Request body for bulk AI review."""

    model_config = ConfigDict(protected_namespaces=())

    chip_id: str
    task: str
    entity_type: str = "qubit"
    date: str | None = None
    task_ids: list[str] | None = None
    model_override: ModelConfig | None = None


class BulkAiReviewResponse(BaseModel):
    """Response after enqueueing bulk AI review."""

    review_run_id: str = ""
    chip_id: str
    task: str
    entity_type: str
    date: str | None = None
    requested_count: int
    task_ids: list[str]
    skipped_reason: str | None = None


class AiReviewListItem(BaseModel):
    """One AI review record extracted from a task result."""

    task_id: str
    review_run_id: str
    task_name: str
    chip_id: str
    qid: str
    target: str
    execution_id: str
    task_status: str
    review_status: str
    decision: str
    human_label: str
    accepted_parameters: str
    needs_review: str
    primary_reason: str
    suggested_labels: str
    recommended_action: str
    model: str
    requested_by: str
    requested_at: datetime | None
    completed_at: datetime | None
    note_updated_at: datetime | None
    start_at: datetime | None
    figure_path: list[str]
    json_figure_path: list[str]
    review_markdown: str
    format_ok: bool


class AiReviewListResponse(BaseModel):
    """Paginated AI review list response."""

    items: list[AiReviewListItem]
    total: int
    skip: int
    limit: int
    decision_counts: dict[str, int]
    status_counts: dict[str, int]


class AiReviewRunSummary(BaseModel):
    """Summary for one bulk AI review run."""

    review_run_id: str
    trigger_type: str
    chip_id: str
    task_name: str
    entity_type: str
    execution_ids: list[str]
    requested_by: str
    requested_at: datetime | None
    completed_at: datetime | None
    model: str
    total: int
    completed_count: int
    failed_count: int
    running_count: int
    requested_count: int
    decision_counts: dict[str, int]
    status_counts: dict[str, int]


class AiReviewRunListResponse(BaseModel):
    """Paginated AI review run list response."""

    items: list[AiReviewRunSummary]
    total: int
    skip: int
    limit: int


class AiReviewRunDetailResponse(BaseModel):
    """Detail response for one AI review run."""

    run: AiReviewRunSummary
    items: list[AiReviewListItem]


class DownloadFiguresAsZipRequest(BaseModel):
    """Request body for downloading task-result artifacts as a ZIP archive."""

    paths: list[str] = []
    filename: str = "figures.zip"
    ai_review_task_ids: list[str] = []
    ai_review_bundle_task_ids: list[str] = []
