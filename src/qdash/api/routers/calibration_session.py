"""HTTP endpoints for calibration sessions: one objective and the runs started for it."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from qdash.api.dependencies import get_calibration_session_service
from qdash.api.lib.project import (
    ProjectContext,
    get_project_context,
    get_project_context_editor,
)
from qdash.api.schemas.calibration_session import (
    CalibrationDecisionResponse,
    CalibrationSessionAuditResponse,
    CalibrationSessionDetailResponse,
    CalibrationSessionResponse,
    CloseCalibrationSessionRequest,
    CreateCalibrationSessionRequest,
    ListCalibrationDecisionsResponse,
    ListCalibrationSessionsResponse,
    RecordCalibrationDecisionRequest,
)
from qdash.api.services.audit_timeline import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from qdash.api.services.calibration_session_audit import CalibrationSessionAuditService
from qdash.api.services.calibration_session_service import CalibrationSessionService
from qdash.datamodel.calibration_session import CalibrationSessionOrigin, CalibrationSessionStatus

router = APIRouter(prefix="/calibration-sessions")


@router.post(
    "",
    response_model=CalibrationSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a calibration session",
    operation_id="createCalibrationSession",
)
def create_calibration_session(
    body: CreateCalibrationSessionRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[CalibrationSessionService, Depends(get_calibration_session_service)],
) -> CalibrationSessionResponse:
    """Record one calibration objective on a chip.

    Runs (saved workflows, pipelines, tasks) and agent sessions started with its ID are grouped
    under it. A run started without one gets an automatic session instead. It grants no
    operation: each run is still approved, gated, and locked on its own.
    """
    return service.create(project_id=ctx.project_id, username=ctx.user.username, body=body)


@router.get(
    "",
    response_model=ListCalibrationSessionsResponse,
    summary="List calibration sessions",
    operation_id="listCalibrationSessions",
)
def list_calibration_sessions(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[CalibrationSessionService, Depends(get_calibration_session_service)],
    chip_id: Annotated[str | None, Query(max_length=200)] = None,
    status_filter: Annotated[
        list[CalibrationSessionStatus] | None,
        Query(alias="status", description="Only sessions in these statuses"),
    ] = None,
    origin: Annotated[
        list[CalibrationSessionOrigin] | None,
        Query(
            description=(
                "Only sessions of these origins: manual (created for an objective) or "
                "automatic (created by QDash for a run started without a session ID)"
            )
        ),
    ] = None,
    mine: Annotated[bool, Query(description="Only sessions the signed-in user created")] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    skip: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> ListCalibrationSessionsResponse:
    """List the project's calibration sessions, newest first."""
    return service.list_sessions(
        project_id=ctx.project_id,
        chip_id=chip_id,
        created_by=ctx.user.username if mine else None,
        statuses=status_filter,
        origins=origin,
        limit=limit,
        skip=skip,
    )


@router.get(
    "/{calibration_session_id}",
    response_model=CalibrationSessionDetailResponse,
    summary="Get a calibration session with its runs",
    operation_id="getCalibrationSession",
)
def get_calibration_session(
    calibration_session_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[CalibrationSessionService, Depends(get_calibration_session_service)],
) -> CalibrationSessionDetailResponse:
    """The session, its pipeline runs with every step execution, and its agent sessions with
    the executions their actions dispatched."""
    return service.get(project_id=ctx.project_id, calibration_session_id=calibration_session_id)


@router.post(
    "/{calibration_session_id}/close",
    response_model=CalibrationSessionDetailResponse,
    summary="Close a calibration session",
    operation_id="closeCalibrationSession",
)
def close_calibration_session(
    calibration_session_id: str,
    body: CloseCalibrationSessionRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[CalibrationSessionService, Depends(get_calibration_session_service)],
) -> CalibrationSessionDetailResponse:
    """End work on the objective; no new run can start in it.

    Refused (409) while a pipeline run or agent session in it still runs or waits. Closing
    stops nothing and records no verdict on the objective.
    """
    return service.close(
        project_id=ctx.project_id,
        calibration_session_id=calibration_session_id,
        username=ctx.user.username,
        body=body,
    )


@router.post(
    "/{calibration_session_id}/decisions",
    response_model=CalibrationDecisionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a decision in a calibration session's audit",
    operation_id="recordCalibrationDecision",
)
def record_calibration_decision(
    calibration_session_id: str,
    body: RecordCalibrationDecisionRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
) -> CalibrationDecisionResponse:
    """Append a decision, as an agent session decision is appended to its audit.

    Only the session's creator records, in any status. Every cited pipeline run and decision
    must belong to the session and every cited task result must be on its chip (409 otherwise);
    QDash freezes what its records say about them. ``experiment`` proposes a run, which is then
    started with this decision's ID; ``conclusion`` states a recommendation that must rest on
    the cited evidence of its candidate (422 otherwise). A decision changes no calibration and
    starts nothing. A retry with the same key and request returns the same record.
    """
    return CalibrationSessionAuditService().record_decision(
        project_id=ctx.project_id,
        calibration_session_id=calibration_session_id,
        username=ctx.user.username,
        body=body,
    )


@router.get(
    "/{calibration_session_id}/decisions",
    response_model=ListCalibrationDecisionsResponse,
    summary="List a calibration session's decisions",
    operation_id="listCalibrationDecisions",
)
def list_calibration_decisions(
    calibration_session_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> ListCalibrationDecisionsResponse:
    """The session's decisions, oldest first, with the runs that carried each out."""
    return CalibrationSessionAuditService().list_decisions(
        project_id=ctx.project_id, calibration_session_id=calibration_session_id
    )


@router.get(
    "/{calibration_session_id}/audit",
    response_model=CalibrationSessionAuditResponse,
    summary="Read a calibration session's audit timeline",
    operation_id="getCalibrationSessionAudit",
)
def get_calibration_session_audit(
    calibration_session_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    cursor: Annotated[str | None, Query(max_length=1000)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> CalibrationSessionAuditResponse:
    """The session's chronological audit, a page at a time, with the agent session audit's
    event schema; an admitted agent session's events are included."""
    return CalibrationSessionAuditService().read_audit(
        project_id=ctx.project_id,
        calibration_session_id=calibration_session_id,
        cursor=cursor,
        limit=limit,
    )


@router.get(
    "/{calibration_session_id}/audit/export",
    response_model=CalibrationSessionAuditResponse,
    summary="Export a calibration session's audit timeline",
    operation_id="exportCalibrationSessionAudit",
)
def export_calibration_session_audit(
    calibration_session_id: str,
    response: Response,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> CalibrationSessionAuditResponse:
    """The whole audit as versioned JSON; refused rather than cut short when too long."""
    audit = CalibrationSessionAuditService().export_audit(
        project_id=ctx.project_id, calibration_session_id=calibration_session_id
    )
    response.headers["Content-Disposition"] = (
        f'attachment; filename="calibration-session-{calibration_session_id}-audit.json"'
    )
    return audit
