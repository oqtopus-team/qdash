import logging
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter
from fastapi.logger import logger
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from qdash.api.schemas.error import (
    Detail,
)
from qdash.neodbmodel.execution_lock import ExecutionLockDocument
from starlette.exceptions import HTTPException

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
    operation_id="fetchFigureByPath",
)
def fetch_figure_by_path(path: str):
    """Fetch a calibration figure by its path."""
    if not Path(path).exists():
        raise HTTPException(
            status_code=404,
            detail=f"File not found: {path}",
        )
    with Path(path).open("rb") as file:
        image_data = file.read()
    return StreamingResponse(BytesIO(image_data), media_type="image/png")


class ExecutionLockStatusResponse(BaseModel):
    """Response model for the fetch_execution_lock_status endpoint."""

    lock: bool


@router.get(
    "/executions/lock_status",
    summary="Fetches the status of a calibration.",
    operation_id="fetchExecutionLockStatus",
    response_model=ExecutionLockStatusResponse,
)
def fetch_execution_lock_status() -> ExecutionLockStatusResponse:
    """Fetch the status of the execution lock."""
    status = ExecutionLockDocument.get_lock_status()
    if status is None:
        return ExecutionLockStatusResponse(lock=False)
    return ExecutionLockStatusResponse(lock=status.lock)
