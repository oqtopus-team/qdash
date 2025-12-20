"""Task result router for QDash API."""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path
from typing import Annotated

import pendulum
from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import StreamingResponse
from starlette.exceptions import HTTPException
from bunnet import SortDirection
from qdash.api.lib.project import ProjectContext, get_project_context
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
def get_latest_qubit_task_results(
    chip_id: Annotated[str, Query(description="Chip ID")],
    task: Annotated[str, Query(description="Task name")],
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> LatestTaskResultResponse:
    """Get the latest qubit task results for all qubits on a chip.

    Retrieves the most recent task result for each qubit on the specified chip.
    Results include fidelity threshold status based on x90 gate fidelity.

    Parameters
    ----------
    chip_id : str
        ID of the chip to fetch results for
    task : str
        Name of the task to fetch results for
    ctx : ProjectContext
        Project context with user and project information

    Returns
    -------
    LatestTaskResultResponse
        Task results for all qubits, keyed by qubit ID

    Raises
    ------
    ValueError
        If the chip is not found for the current project

    """
    logger.debug(
        f"Getting latest qubit task results for chip {chip_id}, task {task}, project: {ctx.project_id}"
    )

    # Get chip info (scoped by project)
    chip = ChipDocument.find_one({"project_id": ctx.project_id, "chip_id": chip_id}).run()
    if chip is None:
        raise ValueError(f"Chip {chip_id} not found in project {ctx.project_id}")

    # Get qids
    qids = list(chip.qubits.keys())
    fidelity_map = {
        k: v.data.get("x90_gate_fidelity", {}).get("value", 0.0) > QUBIT_FIDELITY_THRESHOLD
        for k, v in chip.qubits.items()
    }
    # Fetch all task results in one query (scoped by project)
    all_results = (
        TaskResultHistoryDocument.find(
            {
                "project_id": ctx.project_id,
                "chip_id": chip_id,
                "name": task,
                "qid": {"$in": qids},
            }
        )
        .sort([("end_at", SortDirection.DESCENDING)])
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
def get_historical_qubit_task_results(
    chip_id: Annotated[str, Query(description="Chip ID")],
    task: Annotated[str, Query(description="Task name")],
    date: Annotated[str, Query(description="Date in YYYYMMDD format")],
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> LatestTaskResultResponse:
    """Get historical qubit task results for a specific date.

    Retrieves task results from a specific historical date using chip history
    snapshots. Results are filtered to tasks executed within the specified
    day in JST timezone.

    Parameters
    ----------
    chip_id : str
        ID of the chip to fetch results for
    task : str
        Name of the task to fetch results for
    date : str
        Date in YYYYMMDD format (JST timezone)
    ctx : ProjectContext
        Project context with user and project information

    Returns
    -------
    LatestTaskResultResponse
        Historical task results for all qubits, keyed by qubit ID

    Raises
    ------
    ValueError
        If the chip history is not found for the specified date

    """
    logger.debug(
        f"Getting historical qubit task results for chip {chip_id}, task {task}, date {date}"
    )

    # Get chip info (scoped by project)
    chip = ChipHistoryDocument.find_one(
        {"project_id": ctx.project_id, "chip_id": chip_id, "recorded_date": date}
    ).run()
    if chip is None:
        raise ValueError(f"Chip {chip_id} not found in project {ctx.project_id}")

    # Get qids
    qids = list(chip.qubits.keys())
    parsed_date = pendulum.from_format(date, "YYYYMMDD", tz="Asia/Tokyo")

    start_time = parsed_date.start_of("day")
    end_time = parsed_date.end_of("day")
    all_results = (
        TaskResultHistoryDocument.find(
            {
                "project_id": ctx.project_id,
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
        .sort([("end_at", SortDirection.DESCENDING)])
        .run()
    )
    fidelity_map = {}
    for k, v in chip.qubits.items():
        fidelity_data = v.data.get("x90_gate_fidelity", {})
        value = fidelity_data.get("value", 0.0)
        calibrated_at_str = fidelity_data.get("calibrated_at")

        try:
            parsed = pendulum.parse(calibrated_at_str)
            calibrated_at = parsed if isinstance(parsed, pendulum.DateTime) else None
        except Exception:
            calibrated_at = None

        fidelity_map[k] = (
            value > QUBIT_FIDELITY_THRESHOLD
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
def get_qubit_task_history(
    qid: str,
    chip_id: Annotated[str, Query(description="Chip ID")],
    task: Annotated[str, Query(description="Task name")],
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> TaskHistoryResponse:
    """Get complete task history for a specific qubit.

    Retrieves all historical task results for a specific qubit, sorted by
    end time in descending order. Useful for tracking calibration trends
    over time.

    Parameters
    ----------
    qid : str
        Qubit ID to fetch history for
    chip_id : str
        ID of the chip containing the qubit
    task : str
        Name of the task to fetch history for
    ctx : ProjectContext
        Project context with user and project information

    Returns
    -------
    TaskHistoryResponse
        All historical task results, keyed by task_id

    Raises
    ------
    ValueError
        If the chip is not found for the current project

    """
    logger.debug(f"Getting qubit task history for chip {chip_id}, qid {qid}, task {task}")

    # Get chip info (scoped by project)
    chip = ChipDocument.find_one({"project_id": ctx.project_id, "chip_id": chip_id}).run()
    if chip is None:
        raise ValueError(f"Chip {chip_id} not found in project {ctx.project_id}")
    # Fetch all task results in one query (scoped by project)
    all_results = (
        TaskResultHistoryDocument.find(
            {
                "project_id": ctx.project_id,
                "chip_id": chip_id,
                "name": task,
                "qid": qid,
            }
        )
        .sort([("end_at", SortDirection.DESCENDING)])
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
def get_latest_coupling_task_results(
    chip_id: Annotated[str, Query(description="Chip ID")],
    task: Annotated[str, Query(description="Task name")],
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> LatestTaskResultResponse:
    """Get the latest coupling task results for all couplings on a chip.

    Retrieves the most recent task result for each coupling (qubit pair) on
    the specified chip. Results include fidelity threshold status based on
    Bell state fidelity.

    Parameters
    ----------
    chip_id : str
        ID of the chip to fetch results for
    task : str
        Name of the task to fetch results for
    ctx : ProjectContext
        Project context with user and project information

    Returns
    -------
    LatestTaskResultResponse
        Task results for all couplings, keyed by coupling ID (e.g., "0-1")

    Raises
    ------
    ValueError
        If the chip is not found for the current project

    """
    logger.debug(
        f"Getting latest coupling task results for chip {chip_id}, task {task}, project: {ctx.project_id}"
    )

    # Get chip info (scoped by project)
    chip = ChipDocument.find_one({"project_id": ctx.project_id, "chip_id": chip_id}).run()
    if chip is None:
        raise ValueError(f"Chip {chip_id} not found in project {ctx.project_id}")

    # Get coupling ids
    qids = list(chip.couplings.keys())
    fidelity_map = {
        k: v.data.get("bell_state_fidelity", {}).get("value", 0.0) > COUPLING_FIDELITY_THRESHOLD
        for k, v in chip.couplings.items()
    }

    # Fetch all task results in one query (scoped by project)
    all_results = (
        TaskResultHistoryDocument.find(
            {
                "project_id": ctx.project_id,
                "chip_id": chip_id,
                "name": task,
                "qid": {"$in": qids},
            }
        )
        .sort([("end_at", SortDirection.DESCENDING)])
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
def get_historical_coupling_task_results(
    chip_id: Annotated[str, Query(description="Chip ID")],
    task: Annotated[str, Query(description="Task name")],
    date: Annotated[str, Query(description="Date in YYYYMMDD format")],
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> LatestTaskResultResponse:
    """Get historical coupling task results for a specific date.

    Retrieves task results from a specific historical date using chip history
    snapshots. Results are filtered to tasks executed within the specified
    day in JST timezone.

    Parameters
    ----------
    chip_id : str
        ID of the chip to fetch results for
    task : str
        Name of the task to fetch results for
    date : str
        Date in YYYYMMDD format (JST timezone)
    ctx : ProjectContext
        Project context with user and project information

    Returns
    -------
    LatestTaskResultResponse
        Historical task results for all couplings, keyed by coupling ID

    Raises
    ------
    ValueError
        If the chip history is not found for the specified date

    """
    logger.debug(
        f"Getting historical coupling task results for chip {chip_id}, task {task}, date {date}"
    )

    # Get chip info (scoped by project)
    chip = ChipHistoryDocument.find_one(
        {"project_id": ctx.project_id, "chip_id": chip_id, "recorded_date": date}
    ).run()
    if chip is None:
        raise ValueError(f"Chip {chip_id} not found in project {ctx.project_id}")

    # Get coupling ids
    qids = list(chip.couplings.keys())

    parsed_date = pendulum.from_format(date, "YYYYMMDD", tz="Asia/Tokyo")

    start_time = parsed_date.start_of("day")
    end_time = parsed_date.end_of("day")

    all_results = (
        TaskResultHistoryDocument.find(
            {
                "project_id": ctx.project_id,
                "chip_id": chip_id,
                "name": task,
                "qid": {"$in": qids},
                "start_at": {
                    "$gte": start_time.to_iso8601_string(),
                    "$lt": end_time.to_iso8601_string(),
                },
            }
        )
        .sort([("end_at", SortDirection.DESCENDING)])
        .run()
    )

    fidelity_map = {}
    for k, v in chip.couplings.items():
        fidelity_data = v.data.get("bell_state_fidelity", {})
        value = fidelity_data.get("value", 0.0)
        calibrated_at_str = fidelity_data.get("calibrated_at")

        try:
            parsed = pendulum.parse(calibrated_at_str)
            calibrated_at = parsed if isinstance(parsed, pendulum.DateTime) else None
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
def get_coupling_task_history(
    coupling_id: str,
    chip_id: Annotated[str, Query(description="Chip ID")],
    task: Annotated[str, Query(description="Task name")],
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> TaskHistoryResponse:
    """Get complete task history for a specific coupling.

    Retrieves all historical task results for a specific coupling (qubit pair),
    sorted by end time in descending order. Useful for tracking two-qubit
    calibration trends over time.

    Parameters
    ----------
    coupling_id : str
        Coupling ID to fetch history for (e.g., "0-1")
    chip_id : str
        ID of the chip containing the coupling
    task : str
        Name of the task to fetch history for
    ctx : ProjectContext
        Project context with user and project information

    Returns
    -------
    TaskHistoryResponse
        All historical task results, keyed by task_id

    Raises
    ------
    ValueError
        If the chip is not found for the current project

    """
    logger.debug(
        f"Getting coupling task history for chip {chip_id}, coupling {coupling_id}, task {task}"
    )

    # Get chip info (scoped by project)
    chip = ChipDocument.find_one({"project_id": ctx.project_id, "chip_id": chip_id}).run()
    if chip is None:
        raise ValueError(f"Chip {chip_id} not found in project {ctx.project_id}")

    # Fetch all task results in one query (scoped by project)
    all_results = (
        TaskResultHistoryDocument.find(
            {
                "project_id": ctx.project_id,
                "chip_id": chip_id,
                "name": task,
                "qid": coupling_id,
            }
        )
        .sort([("end_at", SortDirection.DESCENDING)])
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
    project_id: str,
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
    project_id : str
        The project ID for scoping the query
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
    # Find all task results for the given tag and parameter (scoped by project)
    task_results = (
        TaskResultHistoryDocument.find(
            {
                "project_id": project_id,
                "chip_id": chip_id,
                "tags": tag,
                "output_parameter_names": parameter,
                "start_at": {"$gte": start_at, "$lte": end_at},
            }
        )
        .sort([("start_at", SortDirection.ASCENDING)])
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

        # Skip if the parameter is not in output_parameters (data inconsistency)
        if parameter not in task_result.output_parameters:
            logger.warning(
                f"Parameter '{parameter}' not found in output_parameters for task_result "
                f"(qid={qid}, start_at={task_result.start_at}), skipping"
            )
            continue

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
def get_timeseries_task_results(
    chip_id: Annotated[str, Query(description="Chip ID")],
    tag: Annotated[str, Query(description="Tag to filter by")],
    parameter: Annotated[str, Query(description="Parameter name")],
    start_at: Annotated[str, Query(description="Start time in ISO format")],
    end_at: Annotated[str, Query(description="End time in ISO format")],
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    qid: Annotated[str | None, Query(description="Optional qubit ID to filter by")] = None,
) -> TimeSeriesData:
    """Get timeseries task results filtered by tag and parameter.

    Retrieves time series data for calibration parameters, optionally filtered
    to a specific qubit. Useful for plotting parameter trends over time.

    Parameters
    ----------
    chip_id : str
        ID of the chip to fetch results for
    tag : str
        Tag to filter tasks by (e.g., calibration category)
    parameter : str
        Name of the output parameter to retrieve
    start_at : str
        Start time in ISO format for the time range
    end_at : str
        End time in ISO format for the time range
    ctx : ProjectContext
        Project context with user and project information
    qid : str | None
        Optional qubit ID to filter results to a specific qubit

    Returns
    -------
    TimeSeriesData
        Time series data keyed by qubit ID, each containing a list of
        parameter values with timestamps

    """
    logger.debug(
        f"Getting timeseries task results for chip {chip_id}, tag {tag}, parameter {parameter}, qid {qid}"
    )
    return _fetch_timeseries_data(chip_id, tag, parameter, ctx.project_id, qid, start_at, end_at)


# =============================================================================
# Figure Download
# =============================================================================


@router.post(
    "/task-results/figures/download",
    summary="Download multiple figures as a ZIP file",
    operation_id="downloadFiguresAsZip",
)
def download_figures_as_zip(
    paths: Annotated[list[str], Body(description="List of file paths to include in the ZIP")],
    filename: Annotated[str, Body(description="Filename for the ZIP archive")] = "figures.zip",
) -> StreamingResponse:
    """Download multiple calibration figures as a ZIP file.

    Creates a ZIP archive containing all requested figure files and returns it
    as a streaming response.

    Parameters
    ----------
    paths : list[str]
        List of absolute file paths to the calibration figures
    filename : str
        Filename for the ZIP archive (default: "figures.zip")

    Returns
    -------
    StreamingResponse
        ZIP archive containing all requested files

    Raises
    ------
    HTTPException
        400 if no paths are provided or if any path does not exist

    """
    if not paths:
        raise HTTPException(
            status_code=400,
            detail="No paths provided",
        )

    # Validate all paths exist
    missing_paths = [p for p in paths if not Path(p).exists()]
    if missing_paths:
        raise HTTPException(
            status_code=400,
            detail=f"Files not found: {', '.join(missing_paths[:5])}{'...' if len(missing_paths) > 5 else ''}",
        )

    # Create ZIP in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for file_path in paths:
            path = Path(file_path)
            # Use the filename as the archive name
            zip_file.write(path, path.name)

    zip_buffer.seek(0)

    # Sanitize filename
    safe_filename = (
        "".join(c for c in filename if c.isalnum() or c in "._-").strip() or "figures.zip"
    )
    if not safe_filename.endswith(".zip"):
        safe_filename += ".zip"

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={safe_filename}"},
    )
