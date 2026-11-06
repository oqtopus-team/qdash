"""Task router for QDash API."""

from __future__ import annotations

import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from fastapi.security import (
    HTTPAuthorizationCredentials,  # noqa: TC002 - FastAPI resolves annotations
)

from qdash.api.dependencies import (
    get_flow_service,
    get_knowledge_draft_store,
    get_task_file_service,
    get_task_service,
)
from qdash.api.lib.auth import bearer_scheme
from qdash.api.lib.project import (
    ProjectContext,
    get_project_context,
    get_project_context_editor,
)
from qdash.api.schemas.flow import ExecuteFlowResponse
from qdash.api.schemas.task import (
    EvaluationPromptPreviewResponse,
    ListTaskKnowledgeResponse,
    ListTaskResponse,
    QuickRunTaskRequest,
    TaskKnowledgeResponse,
    TaskResultResponse,
)
from qdash.api.services.catalog_task_run import resolve_catalog_task, run_catalog_task
from qdash.api.services.flow_service import FlowService
from qdash.api.services.knowledge_draft_service import KnowledgeDraftStore, task_archive
from qdash.api.services.pi_chat_service import QDashAuth
from qdash.api.services.pi_evaluation_service import (
    EvaluationRuntimeError,
    preview_evaluation_prompts,
)
from qdash.api.services.task_file_service import TaskFileService
from qdash.api.services.task_service import TaskService
from qdash.datamodel.task_knowledge import get_task_knowledge as lookup_task_knowledge

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


@router.post(
    "/tasks/{task_name}/execute",
    response_model=ExecuteFlowResponse,
    summary="Execute a single task from the task catalog",
    operation_id="quickRunTask",
)
async def quick_run_task(
    task_name: str,
    body: QuickRunTaskRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    flow_service: Annotated[FlowService, Depends(get_flow_service)],
    task_file_service: Annotated[TaskFileService, Depends(get_task_file_service)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
) -> ExecuteFlowResponse:
    """Execute one task without requiring a previous execution snapshot."""
    task, backend_name = resolve_catalog_task(task_file_service, task_name, body.backend_name)

    source = None
    if body.source_task_id:
        source = task_service.get_task_result(ctx.project_id, body.source_task_id)
        if source.username != ctx.user.username:
            raise HTTPException(
                status_code=403, detail="You can only re-execute your own task results"
            )
        if (source.task_name, source.chip_id, source.qid) != (task_name, body.chip_id, body.qid):
            raise HTTPException(
                status_code=400, detail="Source task does not match the task and target"
            )

    return await run_catalog_task(
        flow_service=flow_service,
        task=task,
        backend_name=backend_name,
        chip_id=body.chip_id,
        qid=body.qid,
        username=ctx.user.username,
        project_id=ctx.project_id,
        input_overrides=body.input_parameter_overrides,
        run_overrides=body.run_parameter_overrides,
        persist_output_parameters=body.persist_output_parameters,
        update_params=body.update_params,
        reconfigure=body.reconfigure,
        execution_name=f"quick-run:{task_name}",
        source_task_id=body.source_task_id,
        tags=source.tags if source else None,
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

    Returns the task.md content with image references replaced
    by inline base64 data URIs for self-contained rendering.
    """
    content = service.get_task_knowledge_markdown(task_name)
    return Response(content=content, media_type="text/markdown; charset=utf-8")


@router.get(
    "/tasks/{task_name}/knowledge/archive",
    summary="Download a task's knowledge directory as a zip",
    operation_id="downloadTaskKnowledgeArchive",
    response_class=Response,
    responses={
        200: {"content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}}}
    },
)
def download_task_knowledge_archive(task_name: str) -> Response:
    """The task's ``task.md``, examples and figures, zipped under ``<task_name>/``.

    The zip is the starting point of a knowledge draft: edit it locally and
    upload it from the evaluation dialog. Raises 404 when the task has no
    knowledge directory.
    """
    knowledge = lookup_task_knowledge(task_name)
    task_dir = knowledge.task_dir() if knowledge else None
    if task_dir is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_name}' does not have a knowledge directory",
        )
    return Response(
        content=task_archive(task_dir),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{task_dir.name}.zip"'},
    )


@router.get(
    "/tasks/{task_name}/evaluation-prompts",
    response_model=EvaluationPromptPreviewResponse,
    summary="Preview the prompts an AI evaluation of a task would send",
    operation_id="getTaskEvaluationPrompts",
)
async def get_task_evaluation_prompts(
    task_name: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    drafts: Annotated[KnowledgeDraftStore, Depends(get_knowledge_draft_store)],
    with_examples: bool = Query(
        False, description="Lay out the task's labeled examples, as an in-context evaluation"
    ),
    knowledge_draft_id: str | None = Query(
        None, description="Build the prompts from this uploaded knowledge draft"
    ),
) -> EvaluationPromptPreviewResponse:
    """The prompts the evaluation model would receive for a task.

    The Agent Runtime builds them the way a direct evaluation does, from the
    task's reference in Knowledge, or from an uploaded draft, and its labeled
    examples when asked, as the requesting user, without a figure or a model
    call.
    """
    if knowledge_draft_id:
        draft = drafts.get(ctx.project_id, knowledge_draft_id)
        if draft.task_name != task_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"the knowledge draft describes {draft.task_name}, not {task_name}",
            )
    try:
        payload = await preview_evaluation_prompts(
            task_name,
            auth=QDashAuth(access_token=credentials.credentials, project_id=ctx.project_id),
            with_examples=with_examples,
            knowledge_draft_id=knowledge_draft_id or None,
        )
    except EvaluationRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"agent runtime unavailable: {exc}",
        ) from exc
    return EvaluationPromptPreviewResponse.from_runtime(payload)


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
