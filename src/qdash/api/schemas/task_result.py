"""Schema definitions for task_result router."""

from typing import Any

from pydantic import BaseModel, ConfigDict
from qdash.datamodel.task import OutputParameterModel


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
    note: dict[str, Any] | None = None
    figure_path: list[str] | None = None
    json_figure_path: list[str] | None = None
    raw_data_path: list[str] | None = None
    start_at: str | None = None
    end_at: str | None = None
    elapsed_time: str | None = None
    task_type: str | None = None
    default_view: bool = True
    over_threshold: bool = False


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
    start_at: str


class TimeSeriesData(BaseModel):
    """Response model for time series data."""

    data: dict[str, list[OutputParameterModel]] = {}

    model_config = ConfigDict(arbitrary_types_allowed=True)
