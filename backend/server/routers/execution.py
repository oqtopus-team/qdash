import logging
from io import BytesIO
from typing import Optional

from dbmodel.execution_lock import ExecutionLockModel
from dbmodel.execution_run_history import ExecutionRunHistoryModel
from dbmodel.experiment_history import ExperimentHistoryModel
from fastapi import APIRouter, Query
from fastapi.logger import logger
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from pymongo import DESCENDING
from server.schemas.error import (
    Detail,
)

router = APIRouter()
gunicorn_logger = logging.getLogger("gunicorn.error")
logger.handlers = gunicorn_logger.handlers
if __name__ != "main":
    logger.setLevel(gunicorn_logger.level)
else:
    logger.setLevel(logging.DEBUG)


class ResponseModel(BaseModel):
    message: str


class ExecutionResponse(BaseModel):
    experiment_name: str
    label: str
    status: Optional[str] = Field(None)
    timestamp: str
    input_parameter: Optional[dict] = Field(None)
    output_parameter: Optional[dict] = Field(None)
    fig_path: Optional[str] = Field(None)


class ExecutionRunResponse(BaseModel):
    timestamp: str
    date: str
    status: Optional[str] = Field(None)
    execution_id: str
    menu: dict
    tags: Optional[list[str]] = Field(None)
    qpu_name: Optional[str] = Field(None)
    fridge_temperature: Optional[float] = Field(None)
    flow_url: Optional[str] = Field(None)


@router.get(
    "/executions",
    response_model=list[ExecutionRunResponse],
    summary="Fetch all executions",
    operation_id="fetch_all_executions",
)
def fetch_all_executions():
    execution_runs = ExecutionRunHistoryModel.find(sort=[("timestamp", DESCENDING)])
    return [
        ExecutionRunResponse(
            timestamp=execution_run.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            date=execution_run.date,
            status=execution_run.status,
            execution_id=execution_run.execution_id,
            tags=execution_run.tags,
            menu=execution_run.menu,
            qpu_name=execution_run.qpu_name,
            fridge_temperature=execution_run.fridge_temperature,
            flow_url=execution_run.flow_url,
        )
        for execution_run in execution_runs
    ]


@router.get(
    "/executions/{execution_id}/experiments",
    response_model=list[ExecutionResponse],
    summary="Fetch an execution by its ID",
    operation_id="fetch_experiments_by_id",
)
def fetch_experiments_by_id(execution_id: str):
    executions = ExperimentHistoryModel.find({"execution_id": execution_id})
    return [
        ExecutionResponse(
            experiment_name=execution.experiment_name,
            label=execution.label,
            status=execution.status,
            input_parameter=execution.input_parameter,
            output_parameter=execution.output_parameter,
            timestamp=execution.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            fig_path=execution.fig_path,
        )
        for execution in executions
    ]


@router.post(
    "/executions/{execution_id}/tags",
    summary="Add tags to an execution",
    operation_id="add_execution_tags",
)
def add_execution_tags(execution_id: str, tags: list[str]):
    execution_run_history = ExecutionRunHistoryModel.get_by_execution_id(execution_id)
    execution_run_history.add_tags(tags)


@router.delete(
    "/executions/{execution_id}/tags",
    summary="Remove tags from an execution",
    operation_id="remove_execution_tags",
)
def remove_execution_tags(execution_id: str, tags: list[str]):
    execution_run_history = ExecutionRunHistoryModel.get_by_execution_id(execution_id)
    execution_run_history.remove_tags(tags)


@router.get(
    "/executions/experiments",
    response_model=list[ExecutionResponse],
    summary="Fetch all executions",
    operation_id="fetch_all_executions_experiments",
)
def fetch_all_executions_experiments(
    label: Optional[list[str]] = Query(None, alias="label[]"),
    experiment_name: Optional[list[str]] = Query(None, alias="experiment_name[]"),
    execution_id: Optional[list[str]] = Query(None, alias="execution_id[]"),
):
    query = {"$and": []}
    if label:
        query["$and"].append({"$or": [{"label": la} for la in label]})
    if experiment_name:
        query["$and"].append(
            {"$or": [{"experiment_name": en} for en in experiment_name]}
        )
    if execution_id:
        query["$and"].append({"$or": [{"execution_id": eid} for eid in execution_id]})
    logger.info(f"Query: {query}")
    logger.info(f"label: {label}")
    logger.info(f"experiment_name: {experiment_name}")
    logger.info(f"execution_id: {execution_id}")

    if not query["$and"]:
        query = {}

    executions = ExperimentHistoryModel.find(query, sort=[("timestamp", DESCENDING)])
    return [
        ExecutionResponse(
            experiment_name=execution.experiment_name,
            label=execution.label,
            status=execution.status,
            timestamp=execution.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            input_parameter=execution.input_parameter,
            output_parameter=execution.output_parameter,
            fig_path=execution.fig_path,
        )
        for execution in executions
    ]


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
