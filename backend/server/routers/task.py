from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from neodbmodel.initialize import initialize
from neodbmodel.task import TaskDocument
from pydantic import BaseModel
from server.lib.auth import get_current_active_user
from server.schemas.auth import User

router = APIRouter()

# ロガーの設定
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class TaskResponse(BaseModel):
    """Response model for a task."""

    name: str
    description: str
    task_type: str


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
) -> ListTaskResponse:
    """Fetch all tasks.

    Args:
    ----
        current_user (User): The current user.

    Returns:
    -------
        list[TaskResponse]: The list of tasks.

    """
    initialize()
    tasks = TaskDocument.find({"username": current_user.username}).run()
    return ListTaskResponse(
        tasks=[
            TaskResponse(
                name=task.name,
                description=task.description,
                task_type=task.task_type,
            )
            for task in tasks
        ]
    )
