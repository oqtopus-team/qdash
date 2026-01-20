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
    PolicyViolationsResponse,
    ProvenanceStatsResponse,
    RecalibrationRecommendationResponse,
    RecentChangesResponse,
    RecentExecutionsResponse,
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


@router.get(
    "/executions",
    response_model=RecentExecutionsResponse,
    summary="Get recent execution IDs",
    operation_id="getRecentExecutions",
)
def get_recent_executions(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[ProvenanceService, Depends(get_provenance_service)],
    limit: Annotated[
        int,
        Query(description="Maximum number of execution IDs to return", ge=1, le=50),
    ] = 20,
) -> RecentExecutionsResponse:
    """Get recent unique execution IDs.

    Returns unique execution IDs sorted by most recent first.
    Uses MongoDB aggregation for efficient retrieval.

    Parameters
    ----------
    ctx : ProjectContext
        Project context with user and project information
    service : ProvenanceService
        Provenance service instance
    limit : int
        Maximum number of execution IDs to return (1-50)

    Returns
    -------
    RecentExecutionsResponse
        List of recent execution IDs

    """
    return service.get_recent_executions(
        project_id=ctx.project_id,
        limit=limit,
    )


@router.get(
    "/changes",
    response_model=RecentChangesResponse,
    summary="Get recent parameter changes with delta",
    operation_id="getRecentChanges",
)
def get_recent_changes(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[ProvenanceService, Depends(get_provenance_service)],
    limit: Annotated[
        int,
        Query(description="Maximum number of changes to return", ge=1, le=50),
    ] = 20,
    within_hours: Annotated[
        int,
        Query(description="Time window in hours", ge=1, le=168),
    ] = 24,
    parameter_names: Annotated[
        list[str] | None,
        Query(description="Filter by parameter names (from metrics config)"),
    ] = None,
) -> RecentChangesResponse:
    """Get recent parameter changes with delta from previous versions.

    Returns parameter changes that have a previous version, showing
    the delta (difference) from the previous value.

    Parameters
    ----------
    ctx : ProjectContext
        Project context with user and project information
    service : ProvenanceService
        Provenance service instance
    limit : int
        Maximum number of changes to return (1-50)
    within_hours : int
        Time window in hours (1-168, default: 24)
    parameter_names : list[str] | None
        Filter by parameter names (e.g., from metrics.yaml config)

    Returns
    -------
    RecentChangesResponse
        List of recent parameter changes with delta information

    """
    return service.get_recent_changes(
        project_id=ctx.project_id,
        limit=limit,
        within_hours=within_hours,
        parameter_names=parameter_names,
    )


@router.get(
    "/recommendations/{entity_id}",
    response_model=RecalibrationRecommendationResponse,
    summary="Get recalibration task recommendations",
    operation_id="getRecalibrationRecommendations",
)
def get_recalibration_recommendations(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[ProvenanceService, Depends(get_provenance_service)],
    entity_id: Annotated[str, Path(description="Entity identifier of changed parameter")],
    max_depth: Annotated[
        int,
        Query(description="Maximum impact traversal depth", ge=1, le=20),
    ] = 10,
) -> RecalibrationRecommendationResponse:
    """Get recommended recalibration tasks based on parameter change impact.

    When a calibration parameter changes (either through recalibration or
    manual adjustment), this endpoint analyzes the provenance graph to
    identify which downstream parameters are affected and recommends
    which calibration tasks should be re-run.

    The recommendations are prioritized based on dependency proximity:
    tasks producing directly dependent parameters are ranked higher than
    those producing transitively dependent parameters.

    Parameters
    ----------
    ctx : ProjectContext
        Project context with user and project information
    service : ProvenanceService
        Provenance service instance
    entity_id : str
        Entity identifier of the changed parameter
    max_depth : int
        Maximum traversal depth for impact analysis (1-20)

    Returns
    -------
    RecalibrationRecommendationResponse
        Prioritized list of recommended recalibration tasks

    Example
    -------
    If qubit_frequency for Q0 changes:
    - Priority 1: CheckRabiOscillation (direct dependency)
    - Priority 2: CheckT1, CheckT2 (use frequency-dependent pulses)
    - Priority 3: CheckCrossResonance (uses derived gate parameters)

    """
    return service.get_recalibration_recommendations(
        project_id=ctx.project_id,
        entity_id=entity_id,
        max_depth=max_depth,
    )


@router.get(
    "/policy/violations",
    response_model=PolicyViolationsResponse,
    summary="Get policy violations for current parameter versions",
    operation_id="getProvenancePolicyViolations",
)
def get_policy_violations(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[ProvenanceService, Depends(get_provenance_service)],
    severity: Annotated[
        str | None,
        Query(description="Filter by severity (warn)"),
    ] = None,
    limit: Annotated[
        int,
        Query(description="Maximum number of violations to return", ge=1, le=500),
    ] = 200,
    parameter_names: Annotated[
        list[str] | None,
        Query(description="Filter by parameter names"),
    ] = None,
) -> PolicyViolationsResponse:
    """Get policy violations evaluated on current (latest valid) parameter versions."""
    return service.get_policy_violations(
        project_id=ctx.project_id,
        severity=severity,
        limit=limit,
        parameter_names=parameter_names,
    )


@router.get(
    "/policy/impact/{entity_id}",
    response_model=PolicyViolationsResponse,
    summary="Get policy violations for current versions in impact set",
    operation_id="getProvenancePolicyImpactViolations",
)
def get_policy_impact_violations(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[ProvenanceService, Depends(get_provenance_service)],
    entity_id: Annotated[str, Path(description="Entity identifier")],
    max_depth: Annotated[
        int,
        Query(description="Maximum traversal depth", ge=1, le=20),
    ] = 10,
    severity: Annotated[
        str | None,
        Query(description="Filter by severity (warn)"),
    ] = None,
    limit: Annotated[
        int,
        Query(description="Maximum number of violations to return", ge=1, le=500),
    ] = 200,
) -> PolicyViolationsResponse:
    """Get policy violations for current versions within the impact graph of an entity."""
    return service.get_policy_impact_violations(
        project_id=ctx.project_id,
        entity_id=entity_id,
        max_depth=max_depth,
        severity=severity,
        limit=limit,
    )
