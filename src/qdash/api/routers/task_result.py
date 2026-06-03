"""Task result router for QDash API."""

from __future__ import annotations

import logging
from datetime import datetime  # noqa: TC003
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import StreamingResponse

from qdash.api.dependencies import get_flow_service, get_task_result_service
from qdash.api.lib.project import (
    ProjectContext,
    get_project_context,
    get_project_context_editor,
)
from qdash.api.schemas.flow import ExecuteFlowResponse
from qdash.api.schemas.task_result import (
    AiReviewListResponse,
    AiReviewRunDetailResponse,
    AiReviewRunListResponse,
    BulkAiReviewRequest,
    BulkAiReviewResponse,
    DownloadFiguresAsZipRequest,
    LatestTaskResultResponse,
    TaskHistoryResponse,
    TaskResultExcludeRequest,
    TaskResultExcludeResponse,
    TaskResultListResponse,
    TimeSeriesData,
)
from qdash.api.services.flow_service import FlowService
from qdash.api.services.task_result_service import TaskResultService

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get(
    "/task-results",
    summary="List task results",
    operation_id="listTaskResults",
    response_model=TaskResultListResponse,
    response_model_exclude_none=True,
)
def list_task_results(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[TaskResultService, Depends(get_task_result_service)],
    status: Annotated[str | None, Query(description="Task status filter")] = None,
    chip_id: Annotated[str | None, Query(description="Chip ID filter")] = None,
    task_name: Annotated[str | None, Query(description="Task name filter")] = None,
    qid: Annotated[str | None, Query(description="Qubit or coupling ID filter")] = None,
    execution_id: Annotated[str | None, Query(description="Execution ID filter")] = None,
    username: Annotated[str | None, Query(description="Username filter")] = None,
    start_from: Annotated[
        datetime | None, Query(description="Inclusive start time lower bound")
    ] = None,
    start_to: Annotated[
        datetime | None, Query(description="Inclusive start time upper bound")
    ] = None,
    message_contains: Annotated[
        str | None, Query(description="Case-insensitive message search")
    ] = None,
    skip: Annotated[int, Query(ge=0, description="Number of rows to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum rows to return")] = 50,
) -> TaskResultListResponse:
    """List task results for cross-task investigation."""
    return service.list_task_results(
        project_id=ctx.project_id,
        status=status,
        chip_id=chip_id,
        task_name=task_name,
        qid=qid,
        execution_id=execution_id,
        username=username,
        start_from=start_from,
        start_to=start_to,
        message_contains=message_contains,
        skip=skip,
        limit=limit,
    )


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
    parameter: Annotated[str, Query(description="Parameter name")],
    start_at: Annotated[str, Query(description="Start time in ISO format")],
    end_at: Annotated[str, Query(description="End time in ISO format")],
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[TaskResultService, Depends(get_task_result_service)],
    tag: Annotated[str | None, Query(description="Tag to filter by")] = None,
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
# AI Review
# =============================================================================


@router.get(
    "/task-results/ai-review/runs",
    response_model=AiReviewRunListResponse,
    summary="List bulk AI review runs",
    operation_id="listTaskResultAiReviewRuns",
)
def list_task_result_ai_review_runs(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[TaskResultService, Depends(get_task_result_service)],
    chip_id: Annotated[str | None, Query(description="Optional chip ID filter")] = None,
    task_name: Annotated[str | None, Query(description="Optional task name filter")] = None,
    skip: Annotated[int, Query(ge=0, description="Number of rows to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=200, description="Maximum rows to return")] = 50,
) -> AiReviewRunListResponse:
    """Return bulk AI review runs for run-oriented browsing."""
    return service.list_ai_review_runs(
        project_id=ctx.project_id,
        chip_id=chip_id,
        task_name=task_name,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/task-results/ai-review/runs/{review_run_id}",
    response_model=AiReviewRunDetailResponse,
    summary="Get one bulk AI review run",
    operation_id="getTaskResultAiReviewRun",
)
def get_task_result_ai_review_run(
    review_run_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[TaskResultService, Depends(get_task_result_service)],
) -> AiReviewRunDetailResponse:
    """Return one bulk AI review run and its task-result review rows."""
    return service.get_ai_review_run(
        project_id=ctx.project_id,
        review_run_id=review_run_id,
    )


@router.get(
    "/task-results/ai-review",
    response_model=AiReviewListResponse,
    summary="List task-result AI reviews",
    operation_id="listTaskResultAiReviews",
)
def list_task_result_ai_reviews(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[TaskResultService, Depends(get_task_result_service)],
    chip_id: Annotated[str | None, Query(description="Optional chip ID filter")] = None,
    task_name: Annotated[str | None, Query(description="Optional task name filter")] = None,
    status: Annotated[str | None, Query(description="Optional AI review status filter")] = None,
    decision: Annotated[str | None, Query(description="Optional AI review decision filter")] = None,
    latest_only: Annotated[
        bool,
        Query(description="If true, keep only the latest review per chip, task, and target"),
    ] = False,
    skip: Annotated[int, Query(ge=0, description="Number of rows to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=200, description="Maximum rows to return")] = 50,
) -> AiReviewListResponse:
    """Return task-result AI reviews for review queue style browsing."""
    return service.list_ai_reviews(
        project_id=ctx.project_id,
        chip_id=chip_id,
        task_name=task_name,
        status=status,
        decision=decision,
        latest_only=latest_only,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/task-results/ai-review/bulk",
    response_model=BulkAiReviewResponse,
    summary="Request bulk AI review for latest task results",
    operation_id="requestBulkAiReview",
)
def request_bulk_ai_review(
    body: BulkAiReviewRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[TaskResultService, Depends(get_task_result_service)],
) -> BulkAiReviewResponse:
    """Enqueue AI review for the current latest task result per entity."""
    return service.request_bulk_ai_review(
        project_id=ctx.project_id,
        chip_id=body.chip_id,
        task=body.task,
        entity_type=body.entity_type,
        date=body.date,
        task_ids=body.task_ids,
        model_override=body.model_override,
        requested_by=ctx.user.username,
    )


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
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[TaskResultService, Depends(get_task_result_service)],
    flow_service: Annotated[FlowService, Depends(get_flow_service)],
    parameter_overrides: Annotated[
        dict[str, dict[str, Any]] | None,
        Body(
            description="Optional parameter overrides: {run: {...}, input: {...}}",
            embed=True,
        ),
    ] = None,
    update_params: Annotated[
        bool,
        Body(
            description="Update backend parameters (e.g. qubex YAML) after execution",
            embed=True,
        ),
    ] = True,
    reconfigure: Annotated[
        bool,
        Body(
            description="Run Configure (system_manager load + push) before executing the task",
            embed=True,
        ),
    ] = False,
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
    from starlette.exceptions import HTTPException

    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

    doc = TaskResultHistoryDocument.find_one(
        {"project_id": ctx.project_id, "task_id": task_id}
    ).run()

    if doc is None:
        raise HTTPException(
            status_code=404,
            detail=f"Task result '{task_id}' not found",
        )

    # Verify the requesting user owns the source task result.
    if doc.username != ctx.user.username:
        raise HTTPException(
            status_code=403,
            detail="You can only re-execute your own task results",
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
        update_params=update_params,
        reconfigure=reconfigure,
    )


# =============================================================================
# Exclusion
# =============================================================================


@router.post(
    "/task-results/{task_id}/exclude",
    response_model=TaskResultExcludeResponse,
    summary="Toggle exclusion of a task result from metrics aggregations",
    operation_id="setTaskResultExcluded",
)
def set_task_result_excluded(
    task_id: str,
    body: TaskResultExcludeRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
) -> TaskResultExcludeResponse:
    """Toggle the excluded flag on a task result.

    Excluded measurements are skipped when aggregating metrics for the
    dashboard / metrics screens. Raw data is preserved.
    """
    from starlette.exceptions import HTTPException

    from qdash.common.utils.datetime import now
    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

    doc = TaskResultHistoryDocument.find_one(
        {"project_id": ctx.project_id, "task_id": task_id}
    ).run()

    if doc is None:
        raise HTTPException(
            status_code=404,
            detail=f"Task result '{task_id}' not found",
        )

    doc.excluded = body.excluded
    doc.excluded_reason = body.reason if body.excluded else ""
    doc.excluded_by_user_id = ctx.user.user_id
    doc.excluded_by = ctx.user.username
    doc.excluded_at = now()
    doc.save()

    return TaskResultExcludeResponse(
        task_id=doc.task_id,
        excluded=doc.excluded,
        excluded_reason=doc.excluded_reason,
        excluded_by_user_id=doc.excluded_by_user_id,
        excluded_by=doc.excluded_by,
        excluded_at=doc.excluded_at,
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
    body: DownloadFiguresAsZipRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> StreamingResponse:
    """Download multiple calibration figures as a ZIP file.

    Creates a ZIP archive containing all requested figure files and returns it
    as a streaming response.

    Parameters
    ----------
    body.paths : list[str]
        List of absolute file paths to the calibration figures
    body.filename : str
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
    zip_buffer, safe_filename = TaskResultService.create_figures_zip(
        body.paths,
        body.filename,
        project_id=ctx.project_id,
        ai_review_task_ids=body.ai_review_task_ids,
        ai_review_bundle_task_ids=body.ai_review_bundle_task_ids,
    )

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={safe_filename}"},
    )
