"""Task router for QDash API."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from qdash.api.lib.project import (  # noqa: TCH002
    ProjectContext,
    get_project_context,
)
from qdash.api.schemas.task import (
    InputParameterModel,
    ListTaskResponse,
    TaskResponse,
    TaskResultResponse,
)
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.repository.task_definition import MongoTaskDefinitionRepository

router = APIRouter()

logger = logging.getLogger(__name__)


def get_task_definition_repository() -> MongoTaskDefinitionRepository:
    """Get task definition repository instance."""
    return MongoTaskDefinitionRepository()


@router.get(
    "/tasks",
    response_model=ListTaskResponse,
    summary="List all tasks",
    operation_id="listTasks",
)
def list_tasks(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    task_repo: Annotated[MongoTaskDefinitionRepository, Depends(get_task_definition_repository)],
    backend: str | None = Query(None, description="Optional backend name to filter tasks by"),
) -> ListTaskResponse:
    """List all tasks.

    Parameters
    ----------
    ctx : ProjectContext
        The project context with user and project information.
    task_repo : MongoTaskDefinitionRepository
        Repository for task definition operations.
    backend : str | None
        Optional backend name to filter tasks by.

    Returns
    -------
    ListTaskResponse
        The list of tasks.

    """
    tasks = task_repo.list_by_project(ctx.project_id, backend=backend)
    return ListTaskResponse(
        tasks=[
            TaskResponse(
                name=task["name"],
                description=task["description"],
                task_type=task["task_type"],
                backend=task["backend"],
                input_parameters={
                    name: InputParameterModel(**param)
                    for name, param in task["input_parameters"].items()
                },
                output_parameters={
                    name: InputParameterModel(**param)
                    for name, param in task["output_parameters"].items()
                },
            )
            for task in tasks
        ]
    )


@router.get(
    "/tasks/{task_id}/result",
    response_model=TaskResultResponse,
    summary="Get task result by task ID",
    operation_id="getTaskResult",
)
def get_task_result(
    task_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> TaskResultResponse:
    """Get task result by task_id.

    Parameters
    ----------
    task_id : str
        The task ID to search for.
    ctx : ProjectContext
        The project context with user and project information.

    Returns
    -------
    TaskResultResponse
        The task result information including figure paths.

    """
    # Find task result by task_id (scoped to project)
    # Note: This still uses TaskResultHistoryDocument directly as
    # the find_one operation is specific to this use case
    task_result = TaskResultHistoryDocument.find_one(
        {"project_id": ctx.project_id, "task_id": task_id}
    ).run()

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
        run_parameters=task_result.run_parameters,
        start_at=task_result.start_at,
        end_at=task_result.end_at,
        elapsed_time=task_result.elapsed_time,
    )
