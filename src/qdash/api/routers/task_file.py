"""Task file router for QDash API."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from qdash.api.dependencies import get_task_file_service
from qdash.api.schemas.task_file import (
    BackendConfigResponse,
    ListTaskFileBackendsResponse,
    ListTaskInfoResponse,
    TaskFileSettings,
)
from qdash.api.services.task_file_service import TaskFileService

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
    """Get task file settings from config/app/settings.yaml.

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
    "/task-files/backend-config",
    response_model=BackendConfigResponse,
    summary="Get backend configuration",
    operation_id="getBackendConfig",
)
def get_backend_config(
    service: Annotated[TaskFileService, Depends(get_task_file_service)],
) -> BackendConfigResponse:
    """Get backend configuration from config/app/backend.yaml.

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
