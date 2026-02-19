"""Task result router for QDash API."""

from __future__ import annotations

import io
import logging
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from bunnet import SortDirection
from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import StreamingResponse
from qdash.api.lib.project import (  # noqa: TCH002
    ProjectContext,
    get_project_context,
)
from qdash.api.schemas.success import SuccessResponse
from qdash.api.schemas.task_result import (
    LatestTaskResultResponse,
    TaskHistoryResponse,
    TaskResult,
    TimeSeriesData,
    TimeSeriesProjection,
)
from qdash.api.schemas.task_result_comment import (
    CommentCreate,
    CommentResponse,
    ListCommentsResponse,
)
from qdash.common.datetime_utils import (
    end_of_day,
    now,
    parse_date,
    parse_elapsed_time,
    start_of_day,
)
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.task import ParameterModel
from qdash.dbmodel.task_result_comment import TaskResultCommentDocument
from qdash.repository.chip import MongoChipRepository
from qdash.repository.task_result_history import MongoTaskResultHistoryRepository
from starlette.exceptions import HTTPException

if TYPE_CHECKING:
    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

router = APIRouter()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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

    # Use individual QubitDocument collection for scalability
    chip_repo = MongoChipRepository()

    # Get qubit IDs from QubitDocument collection
    qids = chip_repo.get_qubit_ids(ctx.project_id, chip_id)
    if not qids:
        raise ValueError(f"Chip {chip_id} not found or has no qubits in project {ctx.project_id}")

    # Fetch all task results in one query (scoped by project)
    task_result_repo = MongoTaskResultHistoryRepository()
    all_results = task_result_repo.find(
        {
            "project_id": ctx.project_id,
            "chip_id": chip_id,
            "name": task,
            "qid": {"$in": qids},
        },
        sort=[("end_at", SortDirection.DESCENDING)],
    )

    # Organize results by qid
    task_results: dict[str, TaskResultHistoryDocument] = {}
    for result in all_results:
        if result.qid is not None and result.qid not in task_results:
            task_results[result.qid] = result

    # Build response
    results = {}
    for qid in qids:
        task_result_doc = task_results.get(qid)
        if task_result_doc is not None:
            task_result = TaskResult(
                task_id=task_result_doc.task_id,
                name=task_result_doc.name,
                status=task_result_doc.status,
                message=task_result_doc.message,
                input_parameters=task_result_doc.input_parameters,
                output_parameters=task_result_doc.output_parameters,
                output_parameter_names=task_result_doc.output_parameter_names,
                run_parameters=task_result_doc.run_parameters,
                note=task_result_doc.note,
                figure_path=task_result_doc.figure_path,
                json_figure_path=task_result_doc.json_figure_path,
                raw_data_path=task_result_doc.raw_data_path,
                start_at=task_result_doc.start_at,
                end_at=task_result_doc.end_at,
                elapsed_time=parse_elapsed_time(task_result_doc.elapsed_time),
                task_type=task_result_doc.task_type,
            )
        else:
            task_result = TaskResult(name=task)
        results[qid] = task_result

    return LatestTaskResultResponse(task_name=task, result=results)


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

    # Use QubitHistoryDocument for historical data (scalable approach)
    chip_repo = MongoChipRepository()
    parsed_date = parse_date(date, "YYYYMMDD")
    start_time = start_of_day(parsed_date)
    end_time = end_of_day(parsed_date)

    # Get qubit IDs from QubitHistoryDocument
    qids = chip_repo.get_historical_qubit_ids(ctx.project_id, chip_id, date)
    if not qids:
        raise ValueError(f"Chip {chip_id} not found or has no qubits for date {date}")

    # Fetch task results
    task_result_repo = MongoTaskResultHistoryRepository()
    all_results = task_result_repo.find(
        {
            "project_id": ctx.project_id,
            "chip_id": chip_id,
            "name": task,
            "qid": {"$in": qids},
            "start_at": {"$gte": start_time, "$lt": end_time},
        },
        sort=[("end_at", SortDirection.DESCENDING)],
    )
    # Organize results by qid
    task_results: dict[str, TaskResultHistoryDocument] = {}
    for result in all_results:
        if result.qid is not None and result.qid not in task_results:
            task_results[result.qid] = result

    # Build response
    results = {}
    for qid in qids:
        task_result_doc = task_results.get(qid)
        if task_result_doc is not None:
            task_result = TaskResult(
                task_id=task_result_doc.task_id,
                name=task_result_doc.name,
                status=task_result_doc.status,
                message=task_result_doc.message,
                input_parameters=task_result_doc.input_parameters,
                output_parameters=task_result_doc.output_parameters,
                output_parameter_names=task_result_doc.output_parameter_names,
                run_parameters=task_result_doc.run_parameters,
                note=task_result_doc.note,
                figure_path=task_result_doc.figure_path,
                json_figure_path=task_result_doc.json_figure_path,
                raw_data_path=task_result_doc.raw_data_path,
                start_at=task_result_doc.start_at,
                end_at=task_result_doc.end_at,
                elapsed_time=parse_elapsed_time(task_result_doc.elapsed_time),
                task_type=task_result_doc.task_type,
            )
        else:
            task_result = TaskResult(name=task)
        results[qid] = task_result

    return LatestTaskResultResponse(task_name=task, result=results)


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
    chip_repo = MongoChipRepository()
    chip = chip_repo.find_one_document({"project_id": ctx.project_id, "chip_id": chip_id})
    if chip is None:
        raise ValueError(f"Chip {chip_id} not found in project {ctx.project_id}")
    # Fetch all task results in one query (scoped by project)
    task_result_repo = MongoTaskResultHistoryRepository()
    all_results = task_result_repo.find(
        {
            "project_id": ctx.project_id,
            "chip_id": chip_id,
            "name": task,
            "qid": qid,
        },
        sort=[("end_at", SortDirection.DESCENDING)],
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
            run_parameters=result.run_parameters,
            note=result.note,
            figure_path=result.figure_path,
            json_figure_path=result.json_figure_path,
            raw_data_path=result.raw_data_path,
            start_at=result.start_at,
            end_at=result.end_at,
            elapsed_time=parse_elapsed_time(result.elapsed_time),
            task_type=result.task_type,
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

    # Use individual CouplingDocument collection for scalability
    chip_repo = MongoChipRepository()

    # Get coupling IDs from CouplingDocument collection
    qids = chip_repo.get_coupling_ids(ctx.project_id, chip_id)
    if not qids:
        raise ValueError(
            f"Chip {chip_id} not found or has no couplings in project {ctx.project_id}"
        )

    # Fetch all task results in one query (scoped by project)
    task_result_repo = MongoTaskResultHistoryRepository()
    all_results = task_result_repo.find(
        {
            "project_id": ctx.project_id,
            "chip_id": chip_id,
            "name": task,
            "qid": {"$in": qids},
        },
        sort=[("end_at", SortDirection.DESCENDING)],
    )

    # Organize results by qid
    task_results: dict[str, TaskResultHistoryDocument] = {}
    for result in all_results:
        if result.qid is not None and result.qid not in task_results:
            task_results[result.qid] = result

    # Build response
    results = {}
    for qid in qids:
        task_result_doc = task_results.get(qid)
        if task_result_doc is not None:
            task_result = TaskResult(
                task_id=task_result_doc.task_id,
                name=task_result_doc.name,
                status=task_result_doc.status,
                message=task_result_doc.message,
                input_parameters=task_result_doc.input_parameters,
                output_parameters=task_result_doc.output_parameters,
                output_parameter_names=task_result_doc.output_parameter_names,
                run_parameters=task_result_doc.run_parameters,
                note=task_result_doc.note,
                figure_path=task_result_doc.figure_path,
                json_figure_path=task_result_doc.json_figure_path,
                raw_data_path=task_result_doc.raw_data_path,
                start_at=task_result_doc.start_at,
                end_at=task_result_doc.end_at,
                elapsed_time=parse_elapsed_time(task_result_doc.elapsed_time),
                task_type=task_result_doc.task_type,
            )
        else:
            task_result = TaskResult(name=task, default_view=False)
        results[qid] = task_result

    return LatestTaskResultResponse(task_name=task, result=results)


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

    # Use CouplingHistoryDocument for historical data (scalable approach)
    chip_repo = MongoChipRepository()
    parsed_date = parse_date(date, "YYYYMMDD")
    start_time = start_of_day(parsed_date)
    end_time = end_of_day(parsed_date)

    # Get coupling IDs from CouplingHistoryDocument
    qids = chip_repo.get_historical_coupling_ids(ctx.project_id, chip_id, date)
    if not qids:
        raise ValueError(f"Chip {chip_id} not found or has no couplings for date {date}")

    # Fetch task results
    task_result_repo = MongoTaskResultHistoryRepository()
    all_results = task_result_repo.find(
        {
            "project_id": ctx.project_id,
            "chip_id": chip_id,
            "name": task,
            "qid": {"$in": qids},
            "start_at": {"$gte": start_time, "$lt": end_time},
        },
        sort=[("end_at", SortDirection.DESCENDING)],
    )
    # Organize results by qid
    task_results: dict[str, TaskResultHistoryDocument] = {}
    for result in all_results:
        if result.qid is not None and result.qid not in task_results:
            task_results[result.qid] = result

    # Build response
    results = {}
    for qid in qids:
        task_result_doc = task_results.get(qid)
        if task_result_doc is not None:
            task_result = TaskResult(
                task_id=task_result_doc.task_id,
                name=task_result_doc.name,
                status=task_result_doc.status,
                message=task_result_doc.message,
                input_parameters=task_result_doc.input_parameters,
                output_parameters=task_result_doc.output_parameters,
                output_parameter_names=task_result_doc.output_parameter_names,
                run_parameters=task_result_doc.run_parameters,
                note=task_result_doc.note,
                figure_path=task_result_doc.figure_path,
                json_figure_path=task_result_doc.json_figure_path,
                raw_data_path=task_result_doc.raw_data_path,
                start_at=task_result_doc.start_at,
                end_at=task_result_doc.end_at,
                elapsed_time=parse_elapsed_time(task_result_doc.elapsed_time),
                task_type=task_result_doc.task_type,
            )
        else:
            task_result = TaskResult(name=task, default_view=False)
        results[qid] = task_result

    return LatestTaskResultResponse(task_name=task, result=results)


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
    chip_repo = MongoChipRepository()
    chip = chip_repo.find_one_document({"project_id": ctx.project_id, "chip_id": chip_id})
    if chip is None:
        raise ValueError(f"Chip {chip_id} not found in project {ctx.project_id}")

    # Fetch all task results in one query (scoped by project)
    task_result_repo = MongoTaskResultHistoryRepository()
    all_results = task_result_repo.find(
        {
            "project_id": ctx.project_id,
            "chip_id": chip_id,
            "name": task,
            "qid": coupling_id,
        },
        sort=[("end_at", SortDirection.DESCENDING)],
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
            run_parameters=result.run_parameters,
            note=result.note,
            figure_path=result.figure_path,
            json_figure_path=result.json_figure_path,
            raw_data_path=result.raw_data_path,
            start_at=result.start_at,
            end_at=result.end_at,
            elapsed_time=parse_elapsed_time(result.elapsed_time),
            task_type=result.task_type,
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
        end_at_dt = now()
        start_at_dt = now() - timedelta(days=7)
    else:
        start_at_dt = datetime.fromisoformat(start_at)
        end_at_dt = datetime.fromisoformat(end_at)
    # Find all task results for the given tag and parameter (scoped by project)
    task_result_repo = MongoTaskResultHistoryRepository()
    task_results = task_result_repo.find_with_projection(
        {
            "project_id": project_id,
            "chip_id": chip_id,
            "tags": tag,
            "output_parameter_names": parameter,
            "start_at": {"$gte": start_at_dt, "$lte": end_at_dt},
        },
        projection_model=TimeSeriesProjection,
        sort=[("start_at", SortDirection.ASCENDING)],
    )

    # Create a dictionary to store time series data for each qid
    timeseries_by_qid: dict[str, list[ParameterModel]] = {}

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
            timeseries_by_qid[qid].append(ParameterModel(**param_data))
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


# =============================================================================
# Task Result Comments
# =============================================================================


@router.get(
    "/task-results/comments",
    summary="List all comments across tasks",
    operation_id="listAllComments",
    response_model=ListCommentsResponse,
)
def list_all_comments(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    skip: Annotated[int, Query(ge=0, description="Number of items to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=200, description="Max items to return")] = 50,
    task_id: Annotated[str | None, Query(description="Filter by task ID")] = None,
    is_closed: Annotated[
        bool | None,
        Query(
            description="Filter by closed status. Default false (open only). Set to true for closed, or omit/null for all."
        ),
    ] = False,
) -> ListCommentsResponse:
    """List all root comments across the project, with reply counts."""
    query: dict[str, object] = {
        "project_id": ctx.project_id,
        "parent_id": None,
    }
    if task_id:
        query["task_id"] = task_id
    if is_closed is not None:
        query["is_closed"] = is_closed

    total = TaskResultCommentDocument.find(query).count()

    docs = (
        TaskResultCommentDocument.find(query)
        .sort("-system_info.created_at")
        .skip(skip)
        .limit(limit)
        .to_list()
    )

    # Collect root comment IDs to get reply counts
    root_ids = [str(doc.id) for doc in docs]

    # Aggregate reply counts for these root comments
    reply_counts: dict[str, int] = {}
    if root_ids:
        pipeline = [
            {
                "$match": {
                    "project_id": ctx.project_id,
                    "parent_id": {"$in": root_ids},
                }
            },
            {"$group": {"_id": "$parent_id", "count": {"$sum": 1}}},
        ]
        results = TaskResultCommentDocument.aggregate(pipeline).to_list()
        for item in results:
            reply_counts[item["_id"]] = item["count"]

    comments = [
        CommentResponse(
            id=str(doc.id),
            task_id=doc.task_id,
            username=doc.username,
            content=doc.content,
            created_at=doc.system_info.created_at,
            parent_id=doc.parent_id,
            reply_count=reply_counts.get(str(doc.id), 0),
            is_closed=doc.is_closed,
        )
        for doc in docs
    ]

    return ListCommentsResponse(
        comments=comments,
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/task-results/comments/{comment_id}",
    summary="Get a single comment by ID",
    operation_id="getComment",
    response_model=CommentResponse,
)
def get_comment(
    comment_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> CommentResponse:
    """Get a single root comment by its ID, including reply count."""
    from bson import ObjectId

    doc = TaskResultCommentDocument.find_one(
        {
            "_id": ObjectId(comment_id),
            "project_id": ctx.project_id,
        },
    ).run()

    if doc is None:
        raise HTTPException(status_code=404, detail="Comment not found")

    # Count replies if this is a root comment
    reply_count = 0
    if doc.parent_id is None:
        reply_count = TaskResultCommentDocument.find(
            {
                "project_id": ctx.project_id,
                "parent_id": comment_id,
            },
        ).count()

    return CommentResponse(
        id=str(doc.id),
        task_id=doc.task_id,
        username=doc.username,
        content=doc.content,
        created_at=doc.system_info.created_at,
        parent_id=doc.parent_id,
        reply_count=reply_count,
        is_closed=doc.is_closed,
    )


@router.get(
    "/task-results/comments/{comment_id}/replies",
    summary="List replies for a comment",
    operation_id="getCommentReplies",
    response_model=list[CommentResponse],
)
def get_comment_replies(
    comment_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> list[CommentResponse]:
    """List all replies to a specific comment, sorted by creation time ascending."""
    docs = (
        TaskResultCommentDocument.find(
            {
                "project_id": ctx.project_id,
                "parent_id": comment_id,
            },
        )
        .sort("system_info.created_at")
        .to_list()
    )

    return [
        CommentResponse(
            id=str(doc.id),
            task_id=doc.task_id,
            username=doc.username,
            content=doc.content,
            created_at=doc.system_info.created_at,
            parent_id=doc.parent_id,
            is_closed=doc.is_closed,
        )
        for doc in docs
    ]


@router.get(
    "/task-results/{task_id}/comments",
    summary="List comments for a task result",
    operation_id="getTaskResultComments",
    response_model=list[CommentResponse],
)
def get_task_result_comments(
    task_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> list[CommentResponse]:
    """List all comments for a task result, sorted by creation time ascending."""
    docs = (
        TaskResultCommentDocument.find(
            {
                "project_id": ctx.project_id,
                "task_id": task_id,
            },
        )
        .sort("system_info.created_at")
        .to_list()
    )

    return [
        CommentResponse(
            id=str(doc.id),
            task_id=doc.task_id,
            username=doc.username,
            content=doc.content,
            created_at=doc.system_info.created_at,
            parent_id=doc.parent_id,
            is_closed=doc.is_closed,
        )
        for doc in docs
    ]


@router.post(
    "/task-results/{task_id}/comments",
    summary="Create a comment on a task result",
    operation_id="createTaskResultComment",
    response_model=CommentResponse,
    status_code=201,
)
def create_task_result_comment(
    task_id: str,
    body: CommentCreate,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> CommentResponse:
    """Create a new comment on a task result."""
    doc = TaskResultCommentDocument(
        project_id=ctx.project_id,
        task_id=task_id,
        username=ctx.user.username,
        content=body.content,
        parent_id=body.parent_id,
    )
    doc.insert()

    return CommentResponse(
        id=str(doc.id),
        task_id=doc.task_id,
        username=doc.username,
        content=doc.content,
        created_at=doc.system_info.created_at,
        parent_id=doc.parent_id,
        is_closed=doc.is_closed,
    )


@router.delete(
    "/task-results/{task_id}/comments/{comment_id}",
    summary="Delete a comment on a task result",
    operation_id="deleteTaskResultComment",
    response_model=SuccessResponse,
)
def delete_task_result_comment(
    task_id: str,
    comment_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> SuccessResponse:
    """Delete a comment. Only the author can delete their own comment."""
    from bson import ObjectId

    doc = TaskResultCommentDocument.find_one(
        {
            "_id": ObjectId(comment_id),
            "project_id": ctx.project_id,
            "task_id": task_id,
        },
    ).run()

    if doc is None:
        raise HTTPException(status_code=404, detail="Comment not found")

    if doc.username != ctx.user.username:
        raise HTTPException(status_code=403, detail="You can only delete your own comments")

    doc.delete()

    return SuccessResponse(message="Comment deleted")


@router.patch(
    "/task-results/comments/{comment_id}/close",
    summary="Close a comment thread",
    operation_id="closeCommentThread",
    response_model=SuccessResponse,
)
def close_comment_thread(
    comment_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> SuccessResponse:
    """Close a comment thread. Only the author or project owner can close."""
    from bson import ObjectId

    doc = TaskResultCommentDocument.find_one(
        {
            "_id": ObjectId(comment_id),
            "project_id": ctx.project_id,
            "parent_id": None,
        },
    ).run()

    if doc is None:
        raise HTTPException(status_code=404, detail="Comment thread not found")

    if doc.username != ctx.user.username and ctx.role != ProjectRole.OWNER:
        raise HTTPException(
            status_code=403, detail="Only the author or project owner can close this thread"
        )

    doc.is_closed = True
    doc.save()

    return SuccessResponse(message="Thread closed")


@router.patch(
    "/task-results/comments/{comment_id}/reopen",
    summary="Reopen a comment thread",
    operation_id="reopenCommentThread",
    response_model=SuccessResponse,
)
def reopen_comment_thread(
    comment_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> SuccessResponse:
    """Reopen a closed comment thread. Only the author or project owner can reopen."""
    from bson import ObjectId

    doc = TaskResultCommentDocument.find_one(
        {
            "_id": ObjectId(comment_id),
            "project_id": ctx.project_id,
            "parent_id": None,
        },
    ).run()

    if doc is None:
        raise HTTPException(status_code=404, detail="Comment thread not found")

    if doc.username != ctx.user.username and ctx.role != ProjectRole.OWNER:
        raise HTTPException(
            status_code=403, detail="Only the author or project owner can reopen this thread"
        )

    doc.is_closed = False
    doc.save()

    return SuccessResponse(message="Thread reopened")
