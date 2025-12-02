"""Schema definitions for execution router."""

from typing import Any

from pydantic import BaseModel


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


class ExecutionResponseSummary(BaseModel):
    """ExecutionResponseSummary is a Pydantic model that represents the summary of an execution response.

    Attributes
    ----------
        name (str): The name of the execution.
        execution_id (str): The ID of the execution.
        status (str): The current status of the execution.
        start_at (str): The start time of the execution.
        end_at (str): The end time of the execution.
        elapsed_time (str): The total elapsed time of the execution.
        tags (list[str]): Tags associated with the execution.
        note (dict): Notes for the execution.

    """

    name: str
    execution_id: str
    status: str
    start_at: str
    end_at: str
    elapsed_time: str
    tags: list[str]
    note: dict


class ExecutionResponseDetail(BaseModel):
    """ExecutionResponseDetail is a Pydantic model that represents the detail of an execution response.

    Attributes
    ----------
        name (str): The name of the execution.
        status (str): The current status of the execution.
        start_at (str): The start time of the execution.
        end_at (str): The end time of the execution.
        elapsed_time (str): The total elapsed time of the execution.
        task (list[Task]): List of tasks in the execution.
        note (dict): Notes for the execution.

    """

    name: str
    status: str
    start_at: str
    end_at: str
    elapsed_time: str
    task: list[Task]
    note: dict


class ListExecutionsResponse(BaseModel):
    """Response model for listing executions.

    Wraps list of executions for API consistency and future extensibility (e.g., pagination).
    """

    executions: list[ExecutionResponseSummary]
    total: int | None = None
    skip: int | None = None
    limit: int | None = None
