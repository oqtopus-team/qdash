"""Schema definitions for execution router."""

from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, field_serializer, field_validator
from qdash.common.datetime_utils import format_elapsed_time, parse_elapsed_time


class ExecutionLockStatusResponse(BaseModel):
    """Response model for the fetch_execution_lock_status endpoint."""

    lock: bool


class Task(BaseModel):
    """Task is a Pydantic model that represents a task."""

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


class ExecutionResponseSummary(BaseModel):
    """ExecutionResponseSummary is a Pydantic model that represents the summary of an execution response.

    Attributes
    ----------
        name (str): The name of the execution.
        execution_id (str): The ID of the execution.
        status (str): The current status of the execution.
        start_at (datetime | None): The start time of the execution.
        end_at (datetime | None): The end time of the execution.
        elapsed_time (timedelta | None): The total elapsed time of the execution.
        tags (list[str]): Tags associated with the execution.
        note (dict): Notes for the execution.

    """

    name: str
    execution_id: str
    status: str
    start_at: datetime | None = None
    end_at: datetime | None = None
    elapsed_time: timedelta | None = None
    tags: list[str]
    note: dict[str, Any]

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


class ExecutionResponseDetail(BaseModel):
    """ExecutionResponseDetail is a Pydantic model that represents the detail of an execution response.

    Attributes
    ----------
        name (str): The name of the execution.
        status (str): The current status of the execution.
        start_at (datetime | None): The start time of the execution.
        end_at (datetime | None): The end time of the execution.
        elapsed_time (timedelta | None): The total elapsed time of the execution.
        task (list[Task]): List of tasks in the execution.
        note (dict): Notes for the execution.

    """

    name: str
    status: str
    start_at: datetime | None = None
    end_at: datetime | None = None
    elapsed_time: timedelta | None = None
    task: list[Task]
    note: dict[str, Any]

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


class ListExecutionsResponse(BaseModel):
    """Response model for listing executions.

    Wraps list of executions for API consistency and future extensibility (e.g., pagination).
    """

    executions: list[ExecutionResponseSummary]
    total: int | None = None
    skip: int | None = None
    limit: int | None = None
