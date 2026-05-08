"""Cool-down router."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from qdash.api.dependencies import get_cooldown_service  # noqa: TCH002
from qdash.api.lib.project import (  # noqa: TCH002
    ProjectContext,
    get_project_context,
    get_project_context_editor,
)
from qdash.api.schemas.cooldown import (
    CooldownCreateRequest,
    CooldownResponse,
    CooldownUpdateRequest,
    ListCooldownsResponse,
)
from qdash.api.schemas.success import SuccessResponse
from qdash.api.services.cooldown_service import CooldownService  # noqa: TCH002

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    "/cooldowns",
    summary="List cool-downs (optionally filter by cryostat or chip)",
    operation_id="listCooldowns",
    response_model=ListCooldownsResponse,
)
def list_cooldowns(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[CooldownService, Depends(get_cooldown_service)],
    cryo_id: Annotated[str | None, Query(description="Filter by cryostat")] = None,
    chip_id: Annotated[str | None, Query(description="Filter by chip membership")] = None,
) -> ListCooldownsResponse:
    return service.list_all(project_id=ctx.project_id, cryo_id=cryo_id, chip_id=chip_id)


@router.get(
    "/cooldowns/{cooldown_id}",
    summary="Get a cool-down by id",
    operation_id="getCooldown",
    response_model=CooldownResponse,
)
def get_cooldown(
    cooldown_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[CooldownService, Depends(get_cooldown_service)],
) -> CooldownResponse:
    return service.get(project_id=ctx.project_id, cooldown_id=cooldown_id)


@router.post(
    "/cooldowns",
    summary="Create a cool-down",
    operation_id="createCooldown",
    response_model=CooldownResponse,
    status_code=201,
)
def create_cooldown(
    body: CooldownCreateRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[CooldownService, Depends(get_cooldown_service)],
) -> CooldownResponse:
    return service.create(project_id=ctx.project_id, body=body)


@router.patch(
    "/cooldowns/{cooldown_id}",
    summary="Update a cool-down",
    operation_id="updateCooldown",
    response_model=CooldownResponse,
)
def update_cooldown(
    cooldown_id: str,
    body: CooldownUpdateRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[CooldownService, Depends(get_cooldown_service)],
) -> CooldownResponse:
    return service.update(project_id=ctx.project_id, cooldown_id=cooldown_id, body=body)


@router.delete(
    "/cooldowns/{cooldown_id}",
    summary="Delete a cool-down",
    operation_id="deleteCooldown",
    response_model=SuccessResponse,
)
def delete_cooldown(
    cooldown_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[CooldownService, Depends(get_cooldown_service)],
) -> SuccessResponse:
    return service.delete(project_id=ctx.project_id, cooldown_id=cooldown_id)


@router.post(
    "/cooldowns/{cooldown_id}/chips/{chip_id}",
    summary="Assign a chip to a cool-down",
    operation_id="assignChipToCooldown",
    response_model=CooldownResponse,
)
def assign_chip(
    cooldown_id: str,
    chip_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[CooldownService, Depends(get_cooldown_service)],
) -> CooldownResponse:
    return service.assign_chip(project_id=ctx.project_id, cooldown_id=cooldown_id, chip_id=chip_id)


@router.delete(
    "/cooldowns/{cooldown_id}/chips/{chip_id}",
    summary="Unassign a chip from a cool-down",
    operation_id="unassignChipFromCooldown",
    response_model=CooldownResponse,
)
def unassign_chip(
    cooldown_id: str,
    chip_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[CooldownService, Depends(get_cooldown_service)],
) -> CooldownResponse:
    return service.unassign_chip(
        project_id=ctx.project_id, cooldown_id=cooldown_id, chip_id=chip_id
    )
