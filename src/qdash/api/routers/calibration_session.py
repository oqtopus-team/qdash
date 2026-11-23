"""HTTP endpoints for calibration sessions: one objective and the runs started for it."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from qdash.api.dependencies import get_calibration_session_service
from qdash.api.lib.project import (
    ProjectContext,
    get_project_context,
    get_project_context_editor,
)
from qdash.api.schemas.calibration_session import (
    CalibrationSessionDetailResponse,
    CalibrationSessionResponse,
    CloseCalibrationSessionRequest,
    CreateCalibrationSessionRequest,
    ListCalibrationSessionsResponse,
)
from qdash.api.services.calibration_session_service import CalibrationSessionService
from qdash.datamodel.calibration_session import CalibrationSessionStatus

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

    Pipeline runs and agent sessions started with its ID are grouped under it. It grants no
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
