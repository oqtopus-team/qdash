"""Provenance router for QDash API.

This module provides HTTP endpoints for provenance (data lineage) operations.
Following W3C PROV-DM concepts for tracking calibration parameter origins.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from qdash.api.lib.project import (  # noqa: TCH002
    ProjectContext,
    get_project_context,
)
from qdash.api.schemas.provenance import (
    ExecutionComparisonResponse,
    ImpactResponse,
    LineageResponse,
    ParameterHistoryResponse,
    ParameterVersionResponse,
    ProvenanceStatsResponse,
)
from qdash.api.services.provenance_service import ProvenanceService
from qdash.repository.provenance import (
    MongoActivityRepository,
    MongoParameterVersionRepository,
    MongoProvenanceRelationRepository,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def get_provenance_service() -> ProvenanceService:
    """Get the provenance service instance.

    Returns
    -------
    ProvenanceService
        Provenance service instance

    """
    return ProvenanceService(
        parameter_version_repo=MongoParameterVersionRepository(),
        provenance_relation_repo=MongoProvenanceRelationRepository(),
        activity_repo=MongoActivityRepository(),
    )


@router.get(
    "/entities/{entity_id}",
    response_model=ParameterVersionResponse,
    summary="Get a parameter version by entity ID",
    operation_id="getProvenanceEntity",
)
def get_entity(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[ProvenanceService, Depends(get_provenance_service)],
    entity_id: Annotated[str, Path(description="Entity identifier")],
) -> ParameterVersionResponse:
    """Get a specific parameter version by entity ID.

    Parameters
    ----------
    ctx : ProjectContext
        Project context with user and project information
    service : ProvenanceService
        Provenance service instance
    entity_id : str
        Entity identifier (format: parameter_name:qid:execution_id:task_id)

    Returns
    -------
    ParameterVersionResponse
        Parameter version details

    Raises
    ------
    HTTPException
        404 if entity not found

    """
    entity = service.get_entity(ctx.project_id, entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity {entity_id} not found",
        )
    return entity


@router.get(
    "/lineage/{entity_id}",
    response_model=LineageResponse,
    summary="Get lineage (ancestors) of a parameter version",
    operation_id="getProvenanceLineage",
)
def get_lineage(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[ProvenanceService, Depends(get_provenance_service)],
    entity_id: Annotated[str, Path(description="Entity identifier")],
    max_depth: Annotated[
        int,
        Query(description="Maximum traversal depth", ge=1, le=20),
    ] = 5,
) -> LineageResponse:
    """Get the lineage (ancestors) of a parameter version.

    Traverses wasDerivedFrom and wasGeneratedBy relations backward
    to find all entities and activities that contributed to this entity.

    Parameters
    ----------
    ctx : ProjectContext
        Project context with user and project information
    service : ProvenanceService
        Provenance service instance
    entity_id : str
        Entity identifier to trace lineage from
    max_depth : int
        Maximum traversal depth (1-20)

    Returns
    -------
    LineageResponse
        Lineage graph with nodes and edges

    """
    return service.get_lineage(
        project_id=ctx.project_id,
        entity_id=entity_id,
        max_depth=max_depth,
    )


@router.get(
    "/impact/{entity_id}",
    response_model=ImpactResponse,
    summary="Get impact (descendants) of a parameter version",
    operation_id="getProvenanceImpact",
)
def get_impact(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[ProvenanceService, Depends(get_provenance_service)],
    entity_id: Annotated[str, Path(description="Entity identifier")],
    max_depth: Annotated[
        int,
        Query(description="Maximum traversal depth", ge=1, le=20),
    ] = 5,
) -> ImpactResponse:
    """Get the impact (descendants) of a parameter version.

    Traverses wasDerivedFrom relations forward to find all entities
    that were derived from this entity.

    Parameters
    ----------
    ctx : ProjectContext
        Project context with user and project information
    service : ProvenanceService
        Provenance service instance
    entity_id : str
        Entity identifier to trace impact from
    max_depth : int
        Maximum traversal depth (1-20)

    Returns
    -------
    ImpactResponse
        Impact graph with affected nodes and edges

    """
    return service.get_impact(
        project_id=ctx.project_id,
        entity_id=entity_id,
        max_depth=max_depth,
    )


@router.get(
    "/compare",
    response_model=ExecutionComparisonResponse,
    summary="Compare parameter values between two executions",
    operation_id="compareExecutions",
)
def compare_executions(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[ProvenanceService, Depends(get_provenance_service)],
    execution_id_before: Annotated[
        str,
        Query(description="First execution ID (before)"),
    ],
    execution_id_after: Annotated[
        str,
        Query(description="Second execution ID (after)"),
    ],
) -> ExecutionComparisonResponse:
    """Compare parameter values between two executions.

    Shows which parameters were added, removed, or changed between
    two calibration executions.

    Parameters
    ----------
    ctx : ProjectContext
        Project context with user and project information
    service : ProvenanceService
        Provenance service instance
    execution_id_before : str
        First execution ID (before state)
    execution_id_after : str
        Second execution ID (after state)

    Returns
    -------
    ExecutionComparisonResponse
        Comparison of parameter values

    """
    return service.compare_executions(
        project_id=ctx.project_id,
        execution_id_before=execution_id_before,
        execution_id_after=execution_id_after,
    )


@router.get(
    "/history",
    response_model=ParameterHistoryResponse,
    summary="Get version history for a parameter",
    operation_id="getParameterHistory",
)
def get_parameter_history(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[ProvenanceService, Depends(get_provenance_service)],
    parameter_name: Annotated[
        str,
        Query(description="Name of the parameter"),
    ],
    qid: Annotated[
        str,
        Query(description="Qubit or coupling identifier"),
    ],
    limit: Annotated[
        int,
        Query(description="Maximum number of versions", ge=1, le=100),
    ] = 50,
) -> ParameterHistoryResponse:
    """Get version history for a parameter.

    Returns all versions of a parameter for a specific qubit,
    sorted by version number (newest first).

    Parameters
    ----------
    ctx : ProjectContext
        Project context with user and project information
    service : ProvenanceService
        Provenance service instance
    parameter_name : str
        Name of the parameter (e.g., "qubit_frequency")
    qid : str
        Qubit or coupling identifier (e.g., "Q0", "Q0-Q1")
    limit : int
        Maximum number of versions to return

    Returns
    -------
    ParameterHistoryResponse
        List of parameter versions

    """
    return service.get_parameter_history(
        project_id=ctx.project_id,
        parameter_name=parameter_name,
        qid=qid,
        limit=limit,
    )


@router.get(
    "/stats",
    response_model=ProvenanceStatsResponse,
    summary="Get provenance statistics",
    operation_id="getProvenanceStats",
)
def get_stats(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[ProvenanceService, Depends(get_provenance_service)],
) -> ProvenanceStatsResponse:
    """Get provenance statistics for a project.

    Returns counts and recent entities for provenance tracking.

    Parameters
    ----------
    ctx : ProjectContext
        Project context with user and project information
    service : ProvenanceService
        Provenance service instance

    Returns
    -------
    ProvenanceStatsResponse
        Provenance statistics

    """
    return service.get_stats(ctx.project_id)
