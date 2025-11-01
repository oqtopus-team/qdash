from datetime import datetime
from logging import getLogger
from typing import Annotated

import dateutil.tz
import pendulum
from fastapi import APIRouter, Depends
from prefect.client.orchestration import PrefectClient
from pydantic import BaseModel
from qdash.api.lib.auth import get_current_active_user
from qdash.api.schemas.auth import User
from qdash.api.schemas.calibration import (
    ExecuteCalibRequest,
    ExecuteCalibResponse,
)
from qdash.api.schemas.exception import InternalSeverError
from qdash.config import Settings, get_settings
from qdash.dbmodel.calibration_note import CalibrationNoteDocument
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.execution_counter import ExecutionCounterDocument

from qdash.dbmodel.tag import TagDocument

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








@router.post(
    "/calibration",
    response_model=ExecuteCalibResponse,
    summary="Executes a calibration by creating a flow run from a deployment.",
    operation_id="execute_calib",
)
async def execute_calib(
    request: ExecuteCalibRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ExecuteCalibResponse:
    """Create a flow run from a deployment."""
    client = PrefectClient(api=settings.prefect_api_url)
    logger.info(f"current user: {current_user.username}")
    env = settings.env
    target_deployment = await client.read_deployment_by_name(f"main/{env}-main")
    try:
        execution_id = generate_execution_id(current_user.username, request.chip_id)
        TagDocument.insert_tags(request.tags, current_user.username)
        resp = await client.create_flow_run_from_deployment(
            deployment_id=target_deployment.id,
            parameters={"menu": request.model_dump(), "execution_id": execution_id},
        )
    except Exception as e:
        logger.warning(e)
        raise InternalSeverError(detail=f"Failed to execute calibration {e!s}")
    logger.warning(resp)
    chip_id = ChipDocument.get_current_chip(current_user.username).chip_id
    return ExecuteCalibResponse(
        flow_run_url=f"http://127.0.0.1:{settings.prefect_port}/flow-runs/flow-run/{resp.id}",
        qdash_ui_url=f"http://127.0.0.1:{settings.ui_port}/execution/{chip_id}/{execution_id}",
    )


ja = dateutil.tz.gettz("Asia/Tokyo")
local_date = datetime.now(tz=ja)









