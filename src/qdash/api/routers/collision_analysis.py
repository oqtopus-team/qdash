"""Frequency collision analysis router."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from qdash.api.dependencies import get_collision_analysis_service
from qdash.api.lib.project import ProjectContext, get_project_context
from qdash.api.schemas.collision_analysis import (
    CollisionEvaluateRequest,
    CollisionEvaluateResponse,
    ListCollisionChecksResponse,
)
from qdash.api.services.collision_analysis_service import CollisionAnalysisService

router = APIRouter()

ServiceDep = Annotated[CollisionAnalysisService, Depends(get_collision_analysis_service)]


@router.get(
    "/checks",
    summary="List collision checks",
    operation_id="listCollisionChecks",
    response_model=ListCollisionChecksResponse,
)
def list_collision_checks(service: ServiceDep) -> ListCollisionChecksResponse:
    """Return the qubex-compatible collision checks with parameters and legends."""
    return service.list_checks()


@router.post(
    "/chips/{chip_id}/evaluate",
    summary="Evaluate a collision check on a chip",
    operation_id="evaluateCollisionCheck",
    response_model=CollisionEvaluateResponse,
)
def evaluate_collision_check(
    chip_id: str,
    body: CollisionEvaluateRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: ServiceDep,
) -> CollisionEvaluateResponse:
    """Evaluate one check for every qubit or directed pair of the chip's topology."""
    return service.evaluate(project_id=ctx.project_id, chip_id=chip_id, body=body)
