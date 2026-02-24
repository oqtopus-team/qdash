"""Task result router for QDash API."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import StreamingResponse
from qdash.api.dependencies import get_flow_service, get_task_result_service  # noqa: TCH002
from qdash.api.lib.project import (  # noqa: TCH002
    ProjectContext,
    get_project_context,
)
from qdash.api.schemas.flow import ExecuteFlowResponse
from qdash.api.schemas.task_result import (
    LatestTaskResultResponse,
    TaskHistoryResponse,
    TimeSeriesData,
)
from qdash.api.services.flow_service import FlowService  # noqa: TCH002
from qdash.api.services.task_result_service import TaskResultService

router = APIRouter()

logger = logging.getLogger(__name__)


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
    service: Annotated[TaskResultService, Depends(get_task_result_service)],
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
    service : TaskResultService
        Injected task result service

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
        "Getting latest qubit task results for chip %s, task %s, project: %s",
        chip_id,
        task,
        ctx.project_id,
    )
    return service.get_latest_results(ctx.project_id, chip_id, task, "qubit")


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
    service: Annotated[TaskResultService, Depends(get_task_result_service)],
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
    service : TaskResultService
        Injected task result service

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
    return service.get_historical_results(ctx.project_id, chip_id, task, "qubit", date)


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
    service: Annotated[TaskResultService, Depends(get_task_result_service)],
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
    service : TaskResultService
        Injected task result service

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
    return service.get_history(ctx.project_id, chip_id, task, qid)


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
    service: Annotated[TaskResultService, Depends(get_task_result_service)],
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
    service : TaskResultService
        Injected task result service

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
        "Getting latest coupling task results for chip %s, task %s, project: %s",
        chip_id,
        task,
        ctx.project_id,
    )
    return service.get_latest_results(ctx.project_id, chip_id, task, "coupling")


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
    service: Annotated[TaskResultService, Depends(get_task_result_service)],
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
    service : TaskResultService
        Injected task result service

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
    return service.get_historical_results(ctx.project_id, chip_id, task, "coupling", date)


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
    service: Annotated[TaskResultService, Depends(get_task_result_service)],
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
    service : TaskResultService
        Injected task result service

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
    return service.get_history(ctx.project_id, chip_id, task, coupling_id)


# =============================================================================
# Time Series
# =============================================================================


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
    service: Annotated[TaskResultService, Depends(get_task_result_service)],
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
    service : TaskResultService
        Injected task result service
    qid : str | None
        Optional qubit ID to filter results to a specific qubit

    Returns
    -------
    TimeSeriesData
        Time series data keyed by qubit ID, each containing a list of
        parameter values with timestamps

    """
    logger.debug(
        "Getting timeseries task results for chip %s, tag %s, parameter %s, qid %s",
        chip_id,
        tag,
        parameter,
        qid,
    )
    return service.get_timeseries(chip_id, tag, parameter, ctx.project_id, qid, start_at, end_at)


# =============================================================================
# Single-Task Re-execution
# =============================================================================


@router.post(
    "/task-results/{task_id}/re-execute",
    response_model=ExecuteFlowResponse,
    summary="Re-execute a single task from its task result",
    operation_id="reExecuteTaskResult",
)
async def re_execute_task_result(
    task_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[TaskResultService, Depends(get_task_result_service)],
    flow_service: Annotated[FlowService, Depends(get_flow_service)],
    parameter_overrides: Annotated[
        dict[str, dict[str, Any]] | None,
        Body(
            description="Optional parameter overrides: {run: {...}, input: {...}}",
            embed=True,
        ),
    ] = None,
) -> ExecuteFlowResponse:
    """Re-execute a single task using the system single-task-executor deployment.

    Looks up the TaskResultHistoryDocument to extract task_name, qid, chip_id,
    execution_id, and tags, then delegates to FlowService to create a Prefect
    flow run via the system deployment.

    Parameters
    ----------
    task_id : str
        The task result ID to re-execute
    ctx : ProjectContext
        Project context with user and project information
    service : TaskResultService
        Injected task result service
    flow_service : FlowService
        Injected flow service

    Returns
    -------
    ExecuteFlowResponse
        Execution result with IDs and URLs

    """
    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
    from starlette.exceptions import HTTPException

    doc = TaskResultHistoryDocument.find_one(
        {"project_id": ctx.project_id, "task_id": task_id}
    ).run()

    if doc is None:
        raise HTTPException(
            status_code=404,
            detail=f"Task result '{task_id}' not found",
        )

    return await flow_service.execute_single_task_from_snapshot(
        task_name=doc.name,
        qid=doc.qid,
        chip_id=doc.chip_id,
        source_execution_id=doc.execution_id,
        username=ctx.user.username,
        project_id=ctx.project_id,
        tags=doc.tags,
        source_task_id=task_id,
        parameter_overrides=parameter_overrides,
    )


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
    zip_buffer, safe_filename = TaskResultService.create_figures_zip(paths, filename)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={safe_filename}"},
    )
