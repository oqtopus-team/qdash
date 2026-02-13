"""Schema definitions for task router."""

from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator
from qdash.common.datetime_utils import format_elapsed_time, parse_elapsed_time


class InputParameterModel(BaseModel):
    """Input parameter class."""

    unit: str = ""
    value_type: str = "float"
    value: tuple[int | float, ...] | int | float | None = None
    description: str = ""


class TaskResponse(BaseModel):
    """Response model for a task."""

    name: str
    description: str
    backend: str | None = None
    task_type: str
    input_parameters: dict[str, InputParameterModel]
    output_parameters: dict[str, InputParameterModel]


class ListTaskResponse(BaseModel):
    """Response model for a list of tasks."""

    tasks: list[TaskResponse]


class TaskResultResponse(BaseModel):
    """Response model for task result by task_id.

    Attributes
    ----------
        task_id (str): The task ID.
        task_name (str): The name of the task.
        qid (str): The qubit or coupling ID.
        status (str): The task status.
        execution_id (str): The execution ID.
        figure_path (list[str]): List of figure paths.
        json_figure_path (list[str]): List of JSON figure paths.
        input_parameters (dict): Input parameters.
        output_parameters (dict): Output parameters.
        start_at (datetime | None): Start time.
        end_at (datetime | None): End time.
        elapsed_time (timedelta | None): Elapsed time.

    """

    task_id: str
    task_name: str
    qid: str
    status: str
    execution_id: str
    figure_path: list[str]
    json_figure_path: list[str]
    input_parameters: dict[str, Any]
    output_parameters: dict[str, Any]
    run_parameters: dict[str, Any] = {}
    start_at: datetime | None = None
    end_at: datetime | None = None
    elapsed_time: timedelta | None = None

    model_config = ConfigDict(from_attributes=True)

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
