from datetime import datetime
from logging import getLogger
from typing import Annotated

import dateutil.tz
import pendulum
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from qdash.api.lib.auth import get_current_active_user
from qdash.api.schemas.auth import User
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


class CalibrationNoteResponse(BaseModel):
    """CalibrationNote is a subclass of BaseModel."""

    username: str
    execution_id: str
    task_id: str
    note: dict
    timestamp: str


@router.get(
    "/calibration/note",
    response_model=CalibrationNoteResponse,
    summary="Fetches all the cron schedules.",
    operation_id="listCronSchedules",
)
def get_calibration_note(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> CalibrationNoteResponse:
    """Get the calibration note."""
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
