"""Schema definitions for task_result router."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from qdash.datamodel.field_types import ElapsedTime
from qdash.datamodel.task import (
    ParameterModel,
    TaskResultInputParameter,
    TaskResultOutputParameter,
)
from qdash.datamodel.task_invocation import TaskInvocation

_INVOCATION = "Planned step and call this result executed; null for older results."


class TaskResult(BaseModel):
    """TaskResult is a Pydantic model that represents a task result."""

    task_id: str | None = None
    execution_id: str | None = None
    qid: str | None = None
    name: str = ""  # Default empty string for name
    upstream_id: str | None = None
    status: str = "pending"  # Default status
    message: str | None = None
    input_parameters: dict[str, TaskResultInputParameter] | None = None
    output_parameters: dict[str, TaskResultOutputParameter] | None = None
    output_parameter_names: list[str] | None = None
    run_parameters: dict[str, Any] | None = None
    note: dict[str, Any] | None = None
    figure_path: list[str] | None = None
    json_figure_path: list[str] | None = None
    raw_data_path: list[str] | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    elapsed_time: ElapsedTime = None
    task_type: str | None = None
    invocation: TaskInvocation | None = Field(default=None, description=_INVOCATION)
    default_view: bool = True


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
    invocation: TaskInvocation | None = Field(default=None, description=_INVOCATION)
    start_at: datetime | None = None
    end_at: datetime | None = None
    elapsed_time: ElapsedTime = None


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
    output_parameters: dict[str, TaskResultOutputParameter]
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


class DownloadFiguresAsZipRequest(BaseModel):
    """Request body for downloading task-result artifacts as a ZIP archive."""

    paths: list[str] = []
    filename: str = "figures.zip"
