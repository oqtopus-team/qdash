import logging

from fastapi import APIRouter
from fastapi.logger import logger
from neodbmodel.execution_history import ExecutionHistoryDocument
from pydantic import BaseModel
from pymongo import DESCENDING

router = APIRouter()
gunicorn_logger = logging.getLogger("gunicorn.error")
logger.handlers = gunicorn_logger.handlers
if __name__ != "main":
    logger.setLevel(gunicorn_logger.level)
else:
    logger.setLevel(logging.DEBUG)


class ExecutionResponseSummaryV2(BaseModel):
    """ExecutionResponseSummaryV2 is a Pydantic model that represents the summary of an execution response.

    Attributes
    ----------
        name (str): The name of the execution.
        status (str): The current status of the execution.
        start_at (str): The start time of the execution.
        end_at (str): The end time of the execution.
        elapsed_time (str): The total elapsed time of the execution.

    """

    name: str
    status: str
    start_at: str
    end_at: str
    elapsed_time: str


@router.get(
    "/v2/executions",
    response_model=list[ExecutionResponseSummaryV2],
    summary="Fetch all executions",
    operation_id="fetch_all_executions",
)
def fetch_all_executions_v2() -> list[ExecutionResponseSummaryV2]:
    """Fetch all executions."""
    executions = ExecutionHistoryDocument.find(sort=[("end_at", DESCENDING)]).limit(50).run()
    return [
        ExecutionResponseSummaryV2(
            name=execution.name,
            status=execution.status,
            start_at=execution.start_at,
            end_at=execution.end_at,
            elapsed_time=execution.elapsed_time,
        )
        for execution in executions
    ]
