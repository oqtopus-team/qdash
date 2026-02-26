"""Task file router for QDash API."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from qdash.api.dependencies import get_task_file_service  # noqa: TCH002
from qdash.api.lib.auth import get_current_active_user  # noqa: TCH002
from qdash.api.schemas.auth import User  # noqa: TCH002
from qdash.api.schemas.task_file import (
    BackendConfigResponse,
    ListTaskFileBackendsResponse,
    ListTaskInfoResponse,
    SaveTaskFileRequest,
    TaskFileSettings,
    TaskFileTreeNode,
)
from qdash.api.services.task_file_service import TaskFileService  # noqa: TCH002

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/task-files/settings",
    response_model=TaskFileSettings,
    summary="Get task file settings",
    operation_id="getTaskFileSettings",
)
def get_task_file_settings(
    service: Annotated[TaskFileService, Depends(get_task_file_service)],
) -> TaskFileSettings:
    """Get task file settings from config/settings.yaml.

    Returns
    -------
        Task file settings including default backend

    """
    return service.get_settings()


@router.get(
    "/task-files/backends",
    response_model=ListTaskFileBackendsResponse,
    summary="List available task file backends",
    operation_id="listTaskFileBackends",
)
def list_task_file_backends(
    service: Annotated[TaskFileService, Depends(get_task_file_service)],
) -> ListTaskFileBackendsResponse:
    """List all available backend directories in calibtasks.

    Returns
    -------
        List of backend names and paths

    """
    return service.list_backends()


@router.get(
    "/task-files/tree",
    summary="Get file tree for a specific backend",
    operation_id="getTaskFileTree",
    response_model=list[TaskFileTreeNode],
)
def get_task_file_tree(
    backend: str,
    service: Annotated[TaskFileService, Depends(get_task_file_service)],
) -> list[TaskFileTreeNode]:
    """Get file tree structure for a specific backend directory.

    Args:
    ----
        backend: Backend name (e.g., "qubex", "fake")

    Returns:
    -------
        File tree structure for the backend

    """
    return service.get_file_tree(backend)


@router.get(
    "/task-files/content",
    summary="Get task file content for viewing/editing",
    operation_id="getTaskFileContent",
)
def get_task_file_content(
    path: str,
    service: Annotated[TaskFileService, Depends(get_task_file_service)],
) -> dict[str, Any]:
    """Get task file content for viewing/editing.

    Args:
    ----
        path: Relative path from CALIBTASKS_BASE_PATH

    Returns:
    -------
        File content and metadata

    """
    return service.get_file_content(path)


@router.put(
    "/task-files/content",
    summary="Save task file content",
    operation_id="saveTaskFileContent",
)
def save_task_file_content(
    request: SaveTaskFileRequest,
    _current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[TaskFileService, Depends(get_task_file_service)],
) -> dict[str, str]:
    """Save task file content.

    Args:
    ----
        request: Save file request with path and content

    Returns:
    -------
        Success message

    """
    return service.save_file_content(request)


@router.get(
    "/task-files/backend-config",
    response_model=BackendConfigResponse,
    summary="Get backend configuration",
    operation_id="getBackendConfig",
)
def get_backend_config(
    service: Annotated[TaskFileService, Depends(get_task_file_service)],
) -> BackendConfigResponse:
    """Get backend configuration from backend.yaml.

    Returns
    -------
        Backend configuration

    """
    return service.get_backend_config()


@router.get(
    "/task-files/tasks",
    response_model=ListTaskInfoResponse,
    summary="List all tasks in a backend",
    operation_id="listTaskInfo",
)
def list_task_info(
    backend: str,
    service: Annotated[TaskFileService, Depends(get_task_file_service)],
    sort_order: str | None = None,
    enabled_only: bool = False,
) -> ListTaskInfoResponse:
    """List all task definitions found in a backend directory.

    Args:
    ----
        backend: Backend name (e.g., "qubex", "fake")
        sort_order: Sort order for tasks
        enabled_only: If True, only return tasks that are enabled

    Returns:
    -------
        List of task information

    """
    return service.list_task_info(backend, sort_order=sort_order, enabled_only=enabled_only)
