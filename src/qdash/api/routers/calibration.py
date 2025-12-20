"""Calibration router for QDash API."""

from logging import getLogger
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from qdash.api.dependencies import get_calibration_service
from qdash.api.lib.project import ProjectContext, get_project_context
from qdash.api.schemas.calibration import CalibrationNoteResponse
from qdash.api.services.calibration_service import CalibrationService

router = APIRouter()
logger = getLogger("uvicorn.app")


@router.get(
    "/calibrations/note",
    response_model=CalibrationNoteResponse,
    summary="Get the calibration note",
    operation_id="getCalibrationNote",
)
def get_calibration_note(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    calibration_service: Annotated[CalibrationService, Depends(get_calibration_service)],
) -> CalibrationNoteResponse:
    """Get the latest calibration note for the master task.

    Retrieves the most recent calibration note from the database, sorted by timestamp
    in descending order. The note contains metadata about calibration parameters
    and configuration.

    Parameters
    ----------
    ctx : ProjectContext
        Project context with user and project information
    calibration_service : CalibrationService
        Service for calibration operations

    Returns
    -------
    CalibrationNoteResponse
        The latest calibration note containing username, execution_id, task_id,
        note content, and timestamp

    Raises
    ------
    HTTPException
        404 if no calibration note is found

    """
    logger.info(f"project: {ctx.project_id}, user: {ctx.user.username}")
    note = calibration_service.get_latest_note(ctx.project_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Calibration note not found")
    return note
