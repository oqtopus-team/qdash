"""Task router for QDash API."""

from __future__ import annotations

import logging
import math
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from qdash.api.dependencies import get_flow_service, get_task_file_service, get_task_service
from qdash.api.lib.project import (
    ProjectContext,
    get_project_context,
    get_project_context_editor,
)
from qdash.api.schemas.flow import ExecuteFlowResponse
from qdash.api.schemas.task import (
    ListTaskKnowledgeResponse,
    ListTaskResponse,
    QuickRunTaskRequest,
    TaskKnowledgeResponse,
    TaskResultResponse,
)
from qdash.api.schemas.task_file import TaskInfo
from qdash.api.services.flow_service import FlowService
from qdash.api.services.task_file_service import TaskFileService
from qdash.api.services.task_service import TaskService
from qdash.common.config.backend import (
    get_available_backends,
    get_default_backend,
    is_task_available,
)

router = APIRouter()

logger = logging.getLogger(__name__)


def _matches_parameter_type(value: object, value_type: object) -> bool:
    """Return whether a JSON value matches a known task parameter type."""
    if value_type == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if value_type == "float":
        return (
            isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        )
    if value_type == "bool":
        return isinstance(value, bool)
    if value_type == "list":
        return isinstance(value, list)
    if value_type in {"np.linspace", "np.logspace", "np.arange", "range"}:
        return isinstance(value, list) and len(value) == 3
    if value_type in {"str", "string"}:
        return isinstance(value, str)
    return True


def _validate_quick_run_overrides(task: TaskInfo, body: QuickRunTaskRequest) -> None:
    """Reject overrides that the selected task cannot apply."""
    unknown_inputs = set(body.input_parameter_overrides) - set(task.input_parameters)
    unknown_run_parameters = set(body.run_parameter_overrides) - set(task.run_parameters)
    forbidden_inputs = {
        name
        for name in body.input_parameter_overrides
        if task.input_parameters.get(name, {}).get("user_override") == "forbidden"
    }
    invalid_types = []
    for kind, overrides, parameters in (
        ("input", body.input_parameter_overrides, task.input_parameters),
        ("run", body.run_parameter_overrides, task.run_parameters),
    ):
        for name, value in overrides.items():
            metadata = parameters.get(name)
            if metadata is not None and not _matches_parameter_type(
                value, metadata.get("value_type")
            ):
                invalid_types.append(f"{kind}.{name} must be {metadata.get('value_type')}")

    errors = []
    if unknown_inputs:
        errors.append(f"unknown input parameters: {', '.join(sorted(unknown_inputs))}")
    if unknown_run_parameters:
        errors.append(f"unknown run parameters: {', '.join(sorted(unknown_run_parameters))}")
    if forbidden_inputs:
        errors.append(
            f"input parameters do not allow overrides: {', '.join(sorted(forbidden_inputs))}"
        )
    if invalid_types:
        errors.append("invalid parameter types: " + ", ".join(sorted(invalid_types)))
    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid parameter overrides: " + "; ".join(errors),
        )


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
) -> ExecuteFlowResponse:
    """Execute one task without requiring a previous execution snapshot."""
    backend_name = body.backend_name or get_default_backend()
    if backend_name not in get_available_backends():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown backend: {backend_name}",
        )
    if not is_task_available(task_name, backend_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task '{task_name}' is not enabled for backend '{backend_name}'",
        )

    task = next(
        (
            task
            for task in task_file_service.list_task_info(backend_name, enabled_only=True).tasks
            if task.name == task_name
        ),
        None,
    )
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task metadata for '{task_name}' is not available in backend '{backend_name}'",
        )
    _validate_quick_run_overrides(task, body)

    return await flow_service.execute_single_task_from_snapshot(
        task_name=task_name,
        qid=body.qid,
        chip_id=body.chip_id,
        source_execution_id=None,
        username=ctx.user.username,
        project_id=ctx.project_id,
        backend_name=backend_name,
        parameter_overrides={"input": body.input_parameter_overrides},
        default_run_parameters={
            task_name: {
                name: {"value": value} for name, value in body.run_parameter_overrides.items()
            }
        },
        persist_output_parameters=body.persist_output_parameters,
        update_params=body.update_params,
        reconfigure=body.reconfigure,
        execution_name=f"quick-run:{task_name}",
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
