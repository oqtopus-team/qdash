import logging
from io import BytesIO

from fastapi import APIRouter
from fastapi.logger import logger
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from qdash.api.schemas.error import (
    Detail,
)
from qdash.dbmodel.execution_lock import ExecutionLockModel

router = APIRouter()
gunicorn_logger = logging.getLogger("gunicorn.error")
logger.handlers = gunicorn_logger.handlers
if __name__ != "main":
    logger.setLevel(gunicorn_logger.level)
else:
    logger.setLevel(logging.DEBUG)


@router.get(
    "/executions/figure",
    responses={404: {"model": Detail}},
    response_class=StreamingResponse,
    summary="Fetches a calibration figure by its path",
    operation_id="fetch_figure_by_path",
)
def fetch_figure_by_path(path: str):
    with open(path, "rb") as file:
        image_data = file.read()
    return StreamingResponse(BytesIO(image_data), media_type="image/png")


class ExecutionLockStatusResponse(BaseModel):
    lock: bool


@router.get(
    "/executions/lock_status",
    summary="Fetches the status of a calibration.",
    operation_id="fetch_execution_lock_status",
    response_model=ExecutionLockStatusResponse,
)
def fetch_execution_lock_status():
    status = ExecutionLockModel.find_one().run()
    if status is None:
        return ExecutionLockStatusResponse(lock=False)
    return ExecutionLockStatusResponse(lock=status.lock)
