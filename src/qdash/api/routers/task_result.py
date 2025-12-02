"""Task result router for QDash API."""

from __future__ import annotations

import logging
from typing import Annotated

import pendulum
from fastapi import APIRouter, Depends, Query
from pymongo import ASCENDING, DESCENDING
from qdash.api.lib.auth import get_current_active_user, get_optional_current_user
from qdash.api.schemas.auth import User
from qdash.api.schemas.task_result import (
    LatestTaskResultResponse,
    TaskHistoryResponse,
    TaskResult,
    TimeSeriesData,
    TimeSeriesProjection,
)
from qdash.api.services.response_processor import response_processor
from qdash.datamodel.task import OutputParameterModel
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.chip_history import ChipHistoryDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

router = APIRouter()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

QUBIT_FIDELITY_THRESHOLD = 0.99
COUPLING_FIDELITY_THRESHOLD = 0.75


# =============================================================================
# Qubit Task Results
# =============================================================================


@router.get(
    "/task-results/qubits/latest",
    summary="Get latest qubit task results",
    operation_id="getLatestQubitTaskResults",
    response_model=LatestTaskResultResponse,
    response_model_exclude_none=True,
)
def fetch_latest_qubit_task_results(
    chip_id: Annotated[str, Query(description="Chip ID")],
    task: Annotated[str, Query(description="Task name")],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> LatestTaskResultResponse:
    """Fetch latest qubit task results with optional defensive outlier filtering."""
    logger.debug(f"Fetching qubit tasks for chip {chip_id}, task {task}, user: {current_user.username}")

    # Get chip info
    chip = ChipDocument.find_one({"chip_id": chip_id, "username": current_user.username}).run()
    if chip is None:
        raise ValueError(f"Chip {chip_id} not found for user {current_user.username}")

    # Get qids
    qids = list(chip.qubits.keys())
    fidelity_map = {
        k: v.data.get("x90_gate_fidelity", {}).get("value", 0.0) > QUBIT_FIDELITY_THRESHOLD
        for k, v in chip.qubits.items()
    }
    # Fetch all task results in one query
    all_results = (
        TaskResultHistoryDocument.find(
            {
                "username": current_user.username,
                "chip_id": chip_id,
                "name": task,
                "qid": {"$in": qids},
            }
        )
        .sort([("end_at", DESCENDING)])
        .run()
    )

    # Organize results by qid
    task_results: dict[str, TaskResultHistoryDocument] = {}
    for result in all_results:
        if result.qid not in task_results:
            task_results[result.qid] = result

    # Build response
    results = {}
    for qid in qids:
        result = task_results.get(qid)
        if result is not None:
            task_result = TaskResult(
                task_id=result.task_id,
                name=result.name,
                status=result.status,
                message=result.message,
                input_parameters=result.input_parameters,
                output_parameters=result.output_parameters,
                output_parameter_names=result.output_parameter_names,
                note=result.note,
                figure_path=result.figure_path,
                json_figure_path=result.json_figure_path,
                raw_data_path=result.raw_data_path,
                start_at=result.start_at,
                end_at=result.end_at,
                elapsed_time=result.elapsed_time,
                task_type=result.task_type,
                over_threshold=fidelity_map.get(qid, False),
            )
        else:
            task_result = TaskResult(name=task)
        results[qid] = task_result

    response = LatestTaskResultResponse(task_name=task, result=results)
    return response_processor.process_task_response(response, task)


@router.get(
    "/task-results/qubits/history",
    summary="Get historical qubit task results",
    operation_id="getHistoricalQubitTaskResults",
    response_model=LatestTaskResultResponse,
    response_model_exclude_none=True,
)
def fetch_historical_qubit_task_results(
    chip_id: Annotated[str, Query(description="Chip ID")],
    task: Annotated[str, Query(description="Task name")],
    date: Annotated[str, Query(description="Date in YYYYMMDD format")],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> LatestTaskResultResponse:
    """Fetch historical qubit task results for a specific date."""
    logger.debug(f"Fetching historical task results for chip {chip_id}, task {task}, date {date}")

    # Get chip info
    chip = ChipHistoryDocument.find_one(
        {"chip_id": chip_id, "username": current_user.username, "recorded_date": date}
    ).run()
    if chip is None:
        raise ValueError(f"Chip {chip_id} not found for user {current_user.username}")

    # Get qids
    qids = list(chip.qubits.keys())
    parsed_date = pendulum.from_format(date, "YYYYMMDD", tz="Asia/Tokyo")

    start_time = parsed_date.start_of("day")
    end_time = parsed_date.end_of("day")
    all_results = (
        TaskResultHistoryDocument.find(
            {
                "username": current_user.username,
                "chip_id": chip_id,
                "name": task,
                "qid": {"$in": qids},
                # Filter tasks executed on the same date in JST
                "start_at": {
                    "$gte": start_time.to_iso8601_string(),
                    "$lt": end_time.to_iso8601_string(),
                },
            }
        )
        .sort([("end_at", DESCENDING)])
        .run()
    )
    fidelity_map = {}
    for k, v in chip.qubits.items():
        fidelity_data = v.data.get("x90_gate_fidelity", {})
        value = fidelity_data.get("value", 0.0)
        calibrated_at_str = fidelity_data.get("calibrated_at")

        try:
            calibrated_at = pendulum.parse(calibrated_at_str)
        except Exception:
            calibrated_at = None

        fidelity_map[k] = (
            value > QUBIT_FIDELITY_THRESHOLD and calibrated_at is not None and start_time <= calibrated_at <= end_time
        )
    # Organize results by qid
    task_results: dict[str, TaskResultHistoryDocument] = {}
    for result in all_results:
        if result.qid not in task_results:
            task_results[result.qid] = result

    # Build response
    results = {}
    for qid in qids:
        result = task_results.get(qid)
        if result is not None:
            task_result = TaskResult(
                task_id=result.task_id,
                name=result.name,
                status=result.status,
                message=result.message,
                input_parameters=result.input_parameters,
                output_parameters=result.output_parameters,
                output_parameter_names=result.output_parameter_names,
                note=result.note,
                figure_path=result.figure_path,
                json_figure_path=result.json_figure_path,
                raw_data_path=result.raw_data_path,
                start_at=result.start_at,
                end_at=result.end_at,
                elapsed_time=result.elapsed_time,
                task_type=result.task_type,
                over_threshold=fidelity_map.get(qid, False),
            )
        else:
            task_result = TaskResult(name=task)
        results[qid] = task_result

    response = LatestTaskResultResponse(task_name=task, result=results)
    return response_processor.process_task_response(response, task)


@router.get(
    "/task-results/qubits/{qid}/history",
    summary="Get qubit task history",
    operation_id="getQubitTaskHistory",
    response_model=TaskHistoryResponse,
    response_model_exclude_none=True,
)
def fetch_qubit_task_history(
    qid: str,
    chip_id: Annotated[str, Query(description="Chip ID")],
    task: Annotated[str, Query(description="Task name")],
    current_user: Annotated[User, Depends(get_optional_current_user)],
) -> TaskHistoryResponse:
    """Fetch task history for a specific qubit."""
    logger.debug(f"Fetching qubit task history for chip {chip_id}, qid {qid}, task {task}")

    # Get chip info
    chip = ChipDocument.find_one({"chip_id": chip_id, "username": current_user.username}).run()
    if chip is None:
        raise ValueError(f"Chip {chip_id} not found for user {current_user.username}")
    # Fetch all task results in one query
    all_results = (
        TaskResultHistoryDocument.find(
            {
                "username": current_user.username,
                "chip_id": chip_id,
                "name": task,
                "qid": qid,
            }
        )
        .sort([("end_at", DESCENDING)])
        .run()
    )

    # Organize results by task_id
    data = {}
    for result in all_results:
        data[result.task_id] = TaskResult(
            task_id=result.task_id,
            name=result.name,
            status=result.status,
            message=result.message,
            input_parameters=result.input_parameters,
            output_parameters=result.output_parameters,
            output_parameter_names=result.output_parameter_names,
            note=result.note,
            figure_path=result.figure_path,
            json_figure_path=result.json_figure_path,
            raw_data_path=result.raw_data_path,
            start_at=result.start_at,
            end_at=result.end_at,
            elapsed_time=result.elapsed_time,
            task_type=result.task_type,
            over_threshold=False,
        )

    return TaskHistoryResponse(name=task, data=data)


# =============================================================================
# Coupling Task Results
# =============================================================================


@router.get(
    "/task-results/couplings/latest",
    summary="Get latest coupling task results",
    operation_id="getLatestCouplingTaskResults",
    response_model=LatestTaskResultResponse,
    response_model_exclude_none=True,
)
def fetch_latest_coupling_task_results(
    chip_id: Annotated[str, Query(description="Chip ID")],
    task: Annotated[str, Query(description="Task name")],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> LatestTaskResultResponse:
    """Fetch latest coupling task results."""
    logger.debug(f"Fetching coupling tasks for chip {chip_id}, task {task}, user: {current_user.username}")

    # Get chip info
    chip = ChipDocument.find_one({"chip_id": chip_id, "username": current_user.username}).run()
    if chip is None:
        raise ValueError(f"Chip {chip_id} not found for user {current_user.username}")

    # Get coupling ids
    qids = list(chip.couplings.keys())
    fidelity_map = {
        k: v.data.get("bell_state_fidelity", {}).get("value", 0.0) > COUPLING_FIDELITY_THRESHOLD
        for k, v in chip.couplings.items()
    }

    # Fetch all task results in one query
    all_results = (
        TaskResultHistoryDocument.find(
            {
                "username": current_user.username,
                "chip_id": chip_id,
                "name": task,
                "qid": {"$in": qids},
            }
        )
        .sort([("end_at", DESCENDING)])
        .run()
    )

    # Organize results by qid
    task_results: dict[str, TaskResultHistoryDocument] = {}
    for result in all_results:
        if result.qid not in task_results:
            task_results[result.qid] = result

    # Build response
    results = {}
    for qid in qids:
        result = task_results.get(qid)
        if result is not None:
            task_result = TaskResult(
                task_id=result.task_id,
                name=result.name,
                status=result.status,
                message=result.message,
                input_parameters=result.input_parameters,
                output_parameters=result.output_parameters,
                output_parameter_names=result.output_parameter_names,
                note=result.note,
                figure_path=result.figure_path,
                json_figure_path=result.json_figure_path,
                raw_data_path=result.raw_data_path,
                start_at=result.start_at,
                end_at=result.end_at,
                elapsed_time=result.elapsed_time,
                task_type=result.task_type,
                over_threshold=fidelity_map.get(qid, False),
            )
        else:
            task_result = TaskResult(name=task, default_view=False)
        results[qid] = task_result

    response = LatestTaskResultResponse(task_name=task, result=results)
    return response_processor.process_task_response(response, task)


@router.get(
    "/task-results/couplings/history",
    summary="Get historical coupling task results",
    operation_id="getHistoricalCouplingTaskResults",
    response_model=LatestTaskResultResponse,
    response_model_exclude_none=True,
)
def fetch_historical_coupling_task_results(
    chip_id: Annotated[str, Query(description="Chip ID")],
    task: Annotated[str, Query(description="Task name")],
    date: Annotated[str, Query(description="Date in YYYYMMDD format")],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> LatestTaskResultResponse:
    """Fetch historical coupling task results for a specific date."""
    logger.debug(f"Fetching historical coupling task results for chip {chip_id}, task {task}, date {date}")

    # Get chip info
    chip = ChipHistoryDocument.find_one(
        {"chip_id": chip_id, "username": current_user.username, "recorded_date": date}
    ).run()
    if chip is None:
        raise ValueError(f"Chip {chip_id} not found for user {current_user.username}")

    # Get coupling ids
    qids = list(chip.couplings.keys())

    parsed_date = pendulum.from_format(date, "YYYYMMDD", tz="Asia/Tokyo")

    start_time = parsed_date.start_of("day")
    end_time = parsed_date.end_of("day")

    all_results = (
        TaskResultHistoryDocument.find(
            {
                "username": current_user.username,
                "chip_id": chip_id,
                "name": task,
                "qid": {"$in": qids},
                "start_at": {
                    "$gte": start_time.to_iso8601_string(),
                    "$lt": end_time.to_iso8601_string(),
                },
            }
        )
        .sort([("end_at", DESCENDING)])
        .run()
    )

    fidelity_map = {}
    for k, v in chip.couplings.items():
        fidelity_data = v.data.get("bell_state_fidelity", {})
        value = fidelity_data.get("value", 0.0)
        calibrated_at_str = fidelity_data.get("calibrated_at")

        try:
            calibrated_at = pendulum.parse(calibrated_at_str)
        except Exception:
            calibrated_at = None

        fidelity_map[k] = (
            value > COUPLING_FIDELITY_THRESHOLD
            and calibrated_at is not None
            and start_time <= calibrated_at <= end_time
        )
    # Organize results by qid
    task_results: dict[str, TaskResultHistoryDocument] = {}
    for result in all_results:
        if result.qid not in task_results:
            task_results[result.qid] = result

    # Build response
    results = {}
    for qid in qids:
        result = task_results.get(qid)
        if result is not None:
            task_result = TaskResult(
                task_id=result.task_id,
                name=result.name,
                status=result.status,
                message=result.message,
                input_parameters=result.input_parameters,
                output_parameters=result.output_parameters,
                output_parameter_names=result.output_parameter_names,
                note=result.note,
                figure_path=result.figure_path,
                json_figure_path=result.json_figure_path,
                raw_data_path=result.raw_data_path,
                start_at=result.start_at,
                end_at=result.end_at,
                elapsed_time=result.elapsed_time,
                task_type=result.task_type,
                over_threshold=fidelity_map.get(qid, False),
            )
        else:
            task_result = TaskResult(name=task, default_view=False)
        results[qid] = task_result

    response = LatestTaskResultResponse(task_name=task, result=results)
    return response_processor.process_task_response(response, task)


@router.get(
    "/task-results/couplings/{coupling_id}/history",
    summary="Get coupling task history",
    operation_id="getCouplingTaskHistory",
    response_model=TaskHistoryResponse,
    response_model_exclude_none=True,
)
def fetch_coupling_task_history(
    coupling_id: str,
    chip_id: Annotated[str, Query(description="Chip ID")],
    task: Annotated[str, Query(description="Task name")],
    current_user: Annotated[User, Depends(get_optional_current_user)],
) -> TaskHistoryResponse:
    """Fetch task history for a specific coupling."""
    logger.debug(f"Fetching coupling task history for chip {chip_id}, coupling {coupling_id}, task {task}")

    # Get chip info
    chip = ChipDocument.find_one({"chip_id": chip_id, "username": current_user.username}).run()
    if chip is None:
        raise ValueError(f"Chip {chip_id} not found for user {current_user.username}")

    # Fetch all task results in one query
    all_results = (
        TaskResultHistoryDocument.find(
            {
                "username": current_user.username,
                "chip_id": chip_id,
                "name": task,
                "qid": coupling_id,
            }
        )
        .sort([("end_at", DESCENDING)])
        .run()
    )

    # Organize results by task_id
    data = {}
    for result in all_results:
        data[result.task_id] = TaskResult(
            task_id=result.task_id,
            name=result.name,
            status=result.status,
            message=result.message,
            input_parameters=result.input_parameters,
            output_parameters=result.output_parameters,
            output_parameter_names=result.output_parameter_names,
            note=result.note,
            figure_path=result.figure_path,
            json_figure_path=result.json_figure_path,
            raw_data_path=result.raw_data_path,
            start_at=result.start_at,
            end_at=result.end_at,
            elapsed_time=result.elapsed_time,
            task_type=result.task_type,
            over_threshold=False,
        )

    return TaskHistoryResponse(name=task, data=data)


# =============================================================================
# Time Series
# =============================================================================


def _fetch_timeseries_data(
    chip_id: str,
    tag: str,
    parameter: str,
    current_user: User,
    target_qid: str | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
) -> TimeSeriesData:
    """Fetch timeseries data for all qids or a specific qid.

    Parameters
    ----------
    chip_id : str
        The ID of the chip to fetch data for
    tag : str
        The tag to filter by
    parameter : str
        The parameter to fetch
    current_user : User
        The current user
    target_qid : str | None
        If provided, only return data for this specific qid
    start_at : str | None
        The start time in ISO format (optional, defaults to 7 days ago)
    end_at : str | None
        The end time in ISO format (optional, defaults to now)

    Returns
    -------
    TimeSeriesData
        The timeseries data

    """
    if start_at is None or end_at is None:
        end_at = pendulum.now(tz="Asia/Tokyo").to_iso8601_string()
        start_at = pendulum.now(tz="Asia/Tokyo").subtract(days=7).to_iso8601_string()
    # Find all task results for the given tag and parameter
    task_results = (
        TaskResultHistoryDocument.find(
            {
                "username": current_user.username,
                "chip_id": chip_id,
                "tags": tag,
                "output_parameter_names": parameter,
                "start_at": {"$gte": start_at, "$lte": end_at},
            }
        )
        .sort([("start_at", ASCENDING)])
        .project(TimeSeriesProjection)
        .run()
    )

    # Create a dictionary to store time series data for each qid
    timeseries_by_qid: dict[str, list[OutputParameterModel]] = {}

    # Process task results
    for task_result in task_results:
        qid = task_result.qid
        # Skip if we're looking for a specific qid and this isn't it
        if target_qid is not None and qid != target_qid:
            continue

        if qid not in timeseries_by_qid:
            timeseries_by_qid[qid] = []

        param_data = task_result.output_parameters[parameter]
        if isinstance(param_data, dict):
            timeseries_by_qid[qid].append(OutputParameterModel(**param_data))
        else:
            timeseries_by_qid[qid].append(param_data)

    return TimeSeriesData(data=timeseries_by_qid)


@router.get(
    "/task-results/timeseries",
    summary="Get timeseries task results by tag and parameter",
    response_model=TimeSeriesData,
    operation_id="getTimeseriesTaskResults",
)
def fetch_timeseries_task_results(
    chip_id: Annotated[str, Query(description="Chip ID")],
    tag: Annotated[str, Query(description="Tag to filter by")],
    parameter: Annotated[str, Query(description="Parameter name")],
    start_at: Annotated[str, Query(description="Start time in ISO format")],
    end_at: Annotated[str, Query(description="End time in ISO format")],
    current_user: Annotated[User, Depends(get_current_active_user)],
    qid: Annotated[str | None, Query(description="Optional qubit ID to filter by")] = None,
) -> TimeSeriesData:
    """Fetch timeseries task results by tag and parameter.

    If qid is provided, returns data only for that specific qubit.
    Otherwise, returns data for all qubits.

    Returns
    -------
        TimeSeriesData: Time series data for the specified parameters.

    """
    logger.debug(f"Fetching timeseries task result for chip {chip_id}, tag {tag}, parameter {parameter}, qid {qid}")
    return _fetch_timeseries_data(chip_id, tag, parameter, current_user, qid, start_at, end_at)
