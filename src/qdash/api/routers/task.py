from __future__ import annotations

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from qdash.api.lib.auth import get_current_active_user
from qdash.api.schemas.auth import User
from qdash.dbmodel.task import TaskDocument

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
                input_parameters={
                    name: InputParameterModel(**param)
                    for name, param in task.input_parameters.items()
                },
                output_parameters={
                    name: InputParameterModel(**param)
                    for name, param in task.output_parameters.items()
                },
            )
            for task in tasks
        ]
    )
