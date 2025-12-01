"""Schema definitions for task router."""

from pydantic import BaseModel, ConfigDict


class InputParameterModel(BaseModel):
    """Input parameter class."""

    unit: str = ""
    value_type: str = "float"
    value: tuple | int | float | None = None
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
        start_at (str): Start time.
        end_at (str): End time.
        elapsed_time (str): Elapsed time.

    """

    task_id: str
    task_name: str
    qid: str
    status: str
    execution_id: str
    figure_path: list[str]
    json_figure_path: list[str]
    input_parameters: dict
    output_parameters: dict
    start_at: str
    end_at: str
    elapsed_time: str

    model_config = ConfigDict(from_attributes=True)
