"""Calibration router for QDash API."""

from datetime import datetime
from logging import getLogger
from typing import Annotated

import dateutil.tz
import pendulum
from fastapi import APIRouter, Depends
from qdash.api.lib.auth import get_current_active_user
from qdash.api.schemas.auth import User
from qdash.api.schemas.calibration import CalibrationNoteResponse
from qdash.dbmodel.calibration_note import CalibrationNoteDocument
from qdash.dbmodel.execution_counter import ExecutionCounterDocument

router = APIRouter()
logger = getLogger("uvicorn.app")


def generate_execution_id(username: str, chip_id: str) -> str:
    """Generate a unique execution ID based on the current date and an execution index. e.g. 20220101-001.

    Args:
    ----
        username: The username to generate the execution ID for
        chip_id: The chip ID to generate the execution ID for

    Returns:
    -------
        str: The generated execution ID.

    """
    date_str = pendulum.now(tz="Asia/Tokyo").date().strftime("%Y%m%d")
    execution_index = ExecutionCounterDocument.get_next_index(date_str, username, chip_id)
    return f"{date_str}-{execution_index:03d}"


@router.get(
    "/calibrations/note",
    response_model=CalibrationNoteResponse,
    summary="Get the calibration note",
    operation_id="getCalibrationNote",
)
def get_calibration_note(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> CalibrationNoteResponse:
    """Get the latest calibration note for the master task.

    Retrieves the most recent calibration note from the database, sorted by timestamp
    in descending order. The note contains metadata about calibration parameters
    and configuration.

    Parameters
    ----------
    current_user : User
        Current authenticated user

    Returns
    -------
    CalibrationNoteResponse
        The latest calibration note containing username, execution_id, task_id,
        note content, and timestamp

    """
    logger.info(f"current user: {current_user.username}")
    latest = (
        CalibrationNoteDocument.find({"task_id": "master"})
        .sort([("timestamp", -1)])  # 更新時刻で降順ソート
        .limit(1)
        .run()
    )[0]
    return CalibrationNoteResponse(
        username=latest.username,
        execution_id=latest.execution_id,
        task_id=latest.task_id,
        note=latest.note,
        timestamp=latest.timestamp,
    )


ja = dateutil.tz.gettz("Asia/Tokyo")
local_date = datetime.now(tz=ja)
