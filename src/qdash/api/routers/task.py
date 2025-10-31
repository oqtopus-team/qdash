from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from qdash.api.lib.auth import get_current_active_user
from qdash.api.schemas.auth import User
from qdash.dbmodel.task import TaskDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

router = APIRouter()

# ロガーの設定
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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


@router.get(
    "/tasks",
    response_model=ListTaskResponse,
    summary="Fetch all tasks",
    operation_id="fetch_all_tasks",
)
def fetch_all_tasks(
    current_user: Annotated[User, Depends(get_current_active_user)],
    backend: str | None = Query(None, description="Optional backend name to filter tasks by"),
) -> ListTaskResponse:
    """Fetch all tasks.

    Args:
    ----
        current_user (User): The current user.
        backend (Optional[str]): Optional backend name to filter tasks by.

    Returns:
    -------
        list[TaskResponse]: The list of tasks.

    """
    # Build query with required username filter
    query = {"username": current_user.username}

    # Add backend filter if specified
    if backend:
        query["backend"] = backend

    tasks = TaskDocument.find(query).run()
    return ListTaskResponse(
        tasks=[
            TaskResponse(
                name=task.name,
                description=task.description,
                task_type=task.task_type,
                backend=task.backend,
                input_parameters={name: InputParameterModel(**param) for name, param in task.input_parameters.items()},
                output_parameters={
                    name: InputParameterModel(**param) for name, param in task.output_parameters.items()
                },
            )
            for task in tasks
        ]
    )


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


@router.get(
    "/task/{task_id}",
    response_model=TaskResultResponse,
    summary="Get task result by task ID",
    operation_id="get_task_result_by_task_id",
)
def get_task_result_by_task_id(
    task_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> TaskResultResponse:
    """Get task result by task_id.

    Args:
    ----
        task_id: The task ID to search for.
        current_user: The current authenticated user.

    Returns:
    -------
        TaskResultResponse: The task result information including figure paths.

    """
    # Find task result by task_id
    task_result = TaskResultHistoryDocument.find_one({"task_id": task_id}).run()

    if not task_result:
        raise HTTPException(status_code=404, detail=f"Task result with task_id {task_id} not found")

    return TaskResultResponse(
        task_id=task_result.task_id,
        task_name=task_result.name,
        qid=task_result.qid,
        status=task_result.status,
        execution_id=task_result.execution_id,
        figure_path=task_result.figure_path,
        json_figure_path=task_result.json_figure_path,
        input_parameters=task_result.input_parameters,
        output_parameters=task_result.output_parameters,
        start_at=task_result.start_at,
        end_at=task_result.end_at,
        elapsed_time=task_result.elapsed_time,
    )
