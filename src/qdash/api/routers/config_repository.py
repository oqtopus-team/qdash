"""Configuration repository status and synchronization."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from qdash.api.dependencies import get_config_repository_service
from qdash.api.lib.auth import get_current_active_user
from qdash.api.schemas.auth import User
from qdash.api.schemas.config_repository import (
    ConfigRepositoryStatus,
    ConfigRepositorySyncRequest,
    ConfigRepositorySyncResult,
)
from qdash.api.services.config_repository_service import ConfigRepositoryService

router = APIRouter()


@router.get(
    "/config/repository/status",
    response_model=ConfigRepositoryStatus,
    summary="Mode, layout and git state of the Qubex configuration root",
    operation_id="getConfigRepositoryStatus",
)
def get_config_repository_status(
    service: Annotated[ConfigRepositoryService, Depends(get_config_repository_service)],
) -> ConfigRepositoryStatus:
    return service.status()


@router.post(
    "/config/repository/sync",
    response_model=ConfigRepositorySyncResult,
    summary="Publish unpublished calibration files, then pull the repository",
    operation_id="syncConfigRepository",
)
def sync_config_repository(
    request: ConfigRepositorySyncRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[ConfigRepositoryService, Depends(get_config_repository_service)],
) -> ConfigRepositorySyncResult:
    """Refuses with 409 while shared files hold local edits, unless ``force``."""
    return service.sync(actor=current_user.username, force=request.force)
