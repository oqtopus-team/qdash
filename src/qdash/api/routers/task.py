"""Task router for QDash API."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from qdash.api.dependencies import get_task_service  # noqa: TCH002
from qdash.api.lib.project import (  # noqa: TCH002
    ProjectContext,
    get_project_context,
)
from qdash.api.schemas.task import (
    ListTaskKnowledgeResponse,
    ListTaskResponse,
    TaskKnowledgeResponse,
    TaskResultResponse,
)
from qdash.api.services.task_service import TaskService  # noqa: TCH002

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get(
    "/tasks",
    response_model=ListTaskResponse,
    summary="List all tasks",
    operation_id="listTasks",
)
def list_tasks(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[TaskService, Depends(get_task_service)],
    backend: str | None = Query(None, description="Optional backend name to filter tasks by"),
) -> ListTaskResponse:
    """List all tasks.

    Parameters
    ----------
    ctx : ProjectContext
        The project context with user and project information.
    service : TaskService
        The task service instance.
    backend : str | None
        Optional backend name to filter tasks by.

    Returns
    -------
    ListTaskResponse
        The list of tasks.

    """
    return service.list_tasks(ctx.project_id, backend=backend)


@router.get(
    "/tasks/{task_id}/result",
    response_model=TaskResultResponse,
    summary="Get task result by task ID",
    operation_id="getTaskResult",
)
def get_task_result(
    task_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[TaskService, Depends(get_task_service)],
) -> TaskResultResponse:
    """Get task result by task_id.

    Parameters
    ----------
    task_id : str
        The task ID to search for.
    ctx : ProjectContext
        The project context with user and project information.
    service : TaskService
        The task service instance.

    Returns
    -------
    TaskResultResponse
        The task result information including figure paths.

    """
    return service.get_task_result(ctx.project_id, task_id)


@router.get(
    "/task-knowledge",
    response_model=ListTaskKnowledgeResponse,
    summary="List all task knowledge entries",
    operation_id="listTaskKnowledge",
)
def list_task_knowledge(
    service: Annotated[TaskService, Depends(get_task_service)],
) -> ListTaskKnowledgeResponse:
    """List all available task knowledge entries with summary info."""
    return service.list_task_knowledge()


@router.get(
    "/tasks/{task_name}/knowledge/markdown",
    summary="Get raw markdown for a task knowledge entry",
    operation_id="getTaskKnowledgeMarkdown",
    response_class=Response,
)
def get_task_knowledge_markdown(
    task_name: str,
    service: Annotated[TaskService, Depends(get_task_service)],
) -> Response:
    """Get raw markdown content for a task knowledge entry.

    Returns the index.md content with image references replaced
    by inline base64 data URIs for self-contained rendering.
    """
    content = service.get_task_knowledge_markdown(task_name)
    return Response(content=content, media_type="text/markdown; charset=utf-8")


@router.get(
    "/tasks/{task_name}/knowledge",
    response_model=TaskKnowledgeResponse,
    summary="Get task knowledge for LLM analysis",
    operation_id="getTaskKnowledge",
)
def get_task_knowledge(
    task_name: str,
    service: Annotated[TaskService, Depends(get_task_service)],
    backend: str = Query("qubex", description="Backend name"),
) -> TaskKnowledgeResponse:
    """Get structured domain knowledge for a calibration task.

    Returns LLM-oriented knowledge including physical principles,
    expected behavior, evaluation criteria, and failure modes.

    Parameters
    ----------
    task_name : str
        The task name (e.g. "CheckT1", "CheckRabi").
    service : TaskService
        The task service instance.
    backend : str
        The backend name (default "qubex").

    Returns
    -------
    TaskKnowledgeResponse
        Structured task knowledge.

    """
    return service.get_task_knowledge(task_name)
