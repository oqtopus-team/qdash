"""Cryostat router."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from qdash.api.dependencies import get_cryostat_service
from qdash.api.lib.project import (
    ProjectContext,
    get_project_context,
    get_project_context_editor,
)
from qdash.api.schemas.cryostat import (
    CryostatCreateRequest,
    CryostatResponse,
    CryostatUpdateRequest,
    ListCryostatsResponse,
)
from qdash.api.schemas.success import SuccessResponse
from qdash.api.services.cryostat_service import CryostatService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    "/cryostats",
    summary="List all cryostats",
    operation_id="listCryostats",
    response_model=ListCryostatsResponse,
)
def list_cryostats(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[CryostatService, Depends(get_cryostat_service)],
) -> ListCryostatsResponse:
    return service.list_all(project_id=ctx.project_id)


@router.get(
    "/cryostats/{cryo_id}",
    summary="Get a cryostat by id",
    operation_id="getCryostat",
    response_model=CryostatResponse,
)
def get_cryostat(
    cryo_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[CryostatService, Depends(get_cryostat_service)],
) -> CryostatResponse:
    return service.get(project_id=ctx.project_id, cryo_id=cryo_id)


@router.post(
    "/cryostats",
    summary="Create a cryostat",
    operation_id="createCryostat",
    response_model=CryostatResponse,
    status_code=201,
)
def create_cryostat(
    body: CryostatCreateRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[CryostatService, Depends(get_cryostat_service)],
) -> CryostatResponse:
    return service.create(project_id=ctx.project_id, body=body)


@router.patch(
    "/cryostats/{cryo_id}",
    summary="Update a cryostat",
    operation_id="updateCryostat",
    response_model=CryostatResponse,
)
def update_cryostat(
    cryo_id: str,
    body: CryostatUpdateRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[CryostatService, Depends(get_cryostat_service)],
) -> CryostatResponse:
    return service.update(project_id=ctx.project_id, cryo_id=cryo_id, body=body)


@router.delete(
    "/cryostats/{cryo_id}",
    summary="Delete a cryostat",
    operation_id="deleteCryostat",
    response_model=SuccessResponse,
)
def delete_cryostat(
    cryo_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[CryostatService, Depends(get_cryostat_service)],
) -> SuccessResponse:
    return service.delete(project_id=ctx.project_id, cryo_id=cryo_id)
