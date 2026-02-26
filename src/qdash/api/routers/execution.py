"""Execution router for QDash API.

This module provides HTTP endpoints for execution-related operations.
Business logic is delegated to ExecutionService for better testability.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from qdash.api.dependencies import get_execution_service, get_flow_service  # noqa: TCH002
from qdash.api.lib.project import (  # noqa: TCH002
    ProjectContext,
    get_project_context,
    get_project_context_owner,
)
from qdash.api.schemas.error import Detail
from qdash.api.schemas.execution import (
    CancelExecutionResponse,
    ExecutionLockStatusResponse,
    ExecutionResponseDetail,
    ListExecutionsResponse,
    ReExecuteRequest,
)
from qdash.api.schemas.flow import ExecuteFlowResponse
from qdash.api.services.execution_service import ExecutionService  # noqa: TCH002
from qdash.api.services.flow_service import FlowService  # noqa: TCH002
from starlette.exceptions import HTTPException

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get(
    "/executions/figure",
    responses={404: {"model": Detail}},
    response_class=FileResponse,
    summary="Get a calibration figure by its path",
    operation_id="getFigureByPath",
)
def get_figure_by_path(path: str) -> FileResponse:
    """Fetch a calibration figure by its file path.

    Retrieves a PNG image file from the server's filesystem and returns it
    as a streaming response.

    Parameters
    ----------
    path : str
        Absolute file path to the calibration figure image

    Returns
    -------
    FileResponse
        PNG image data as a file response with media type "image/png"

    Raises
    ------
    HTTPException
        404 if the file does not exist at the specified path

    """
    if not Path(path).exists():
        raise HTTPException(
            status_code=404,
            detail=f"File not found: {path}",
        )
    # FileResponse sets Content-Length, avoiding chunked encoding
    return FileResponse(path, media_type="image/png")


@router.get(
    "/executions/lock-status",
    summary="Get the execution lock status",
    operation_id="getExecutionLockStatus",
    response_model=ExecutionLockStatusResponse,
)
def get_execution_lock_status(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    execution_service: Annotated[ExecutionService, Depends(get_execution_service)],
) -> ExecutionLockStatusResponse:
    """Fetch the current status of the execution lock.

    The execution lock prevents concurrent calibration workflows from running
    simultaneously. This endpoint checks whether a lock is currently held.

    Parameters
    ----------
    ctx : ProjectContext
        Project context with user and project information
    execution_service : ExecutionService
        Service for execution operations

    Returns
    -------
    ExecutionLockStatusResponse
        Response containing lock status (True if locked, False if available)

    """
    return execution_service.get_lock_status(ctx.project_id)


@router.get(
    "/executions",
    response_model=ListExecutionsResponse,
    summary="List executions",
    operation_id="listExecutions",
)
def list_executions(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    execution_service: Annotated[ExecutionService, Depends(get_execution_service)],
    chip_id: Annotated[str, Query(description="Chip ID to filter executions")],
    skip: Annotated[int, Query(ge=0, description="Number of items to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Number of items to return")] = 20,
) -> ListExecutionsResponse:
    """List executions for a given chip with pagination.

    Parameters
    ----------
    ctx : ProjectContext
        Project context with user and project information
    execution_service : ExecutionService
        Service for execution operations
    chip_id : str
        ID of the chip to fetch executions for
    skip : int
        Number of items to skip (default: 0)
    limit : int
        Number of items to return (default: 20, max: 100)

    Returns
    -------
    ListExecutionsResponse
        Wrapped list of executions for the chip

    """
    logger.debug(
        "Listing executions for chip %s, project: %s, skip: %s, limit: %s",
        chip_id,
        ctx.project_id,
        skip,
        limit,
    )
    executions = execution_service.list_executions(
        project_id=ctx.project_id,
        chip_id=chip_id,
        skip=skip,
        limit=limit,
    )
    return ListExecutionsResponse(
        executions=executions,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/executions/{execution_id}",
    response_model=ExecutionResponseDetail,
    summary="Get an execution by its ID",
    operation_id="getExecution",
)
def get_execution(
    execution_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    execution_service: Annotated[ExecutionService, Depends(get_execution_service)],
) -> ExecutionResponseDetail:
    """Return the execution detail by its ID.

    Parameters
    ----------
    execution_id : str
        ID of the execution to fetch
    ctx : ProjectContext
        Project context with user and project information
    execution_service : ExecutionService
        Service for execution operations

    Returns
    -------
    ExecutionResponseDetail
        Detailed execution information

    """
    logger.debug(f"Fetching execution {execution_id}, project: {ctx.project_id}")
    execution = execution_service.get_execution(ctx.project_id, execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")
    return execution


@router.post(
    "/executions/{flow_run_id}/cancel",
    response_model=CancelExecutionResponse,
    summary="Cancel a running or scheduled execution",
    operation_id="cancelExecution",
)
async def cancel_execution(
    flow_run_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    execution_service: Annotated[ExecutionService, Depends(get_execution_service)],
) -> CancelExecutionResponse:
    """Cancel a running or scheduled execution via Prefect.

    Sends a cancellation request to Prefect for the specified flow run.
    The flow_run_id is the Prefect flow run UUID, which can be obtained from
    the execution detail's note.flow_run_id field.
    Only executions in SCHEDULED, PENDING, RUNNING, or PAUSED state can be cancelled.

    Parameters
    ----------
    flow_run_id : str
        Prefect flow run UUID
    ctx : ProjectContext
        Project context with user and project information
    execution_service : ExecutionService
        Service for execution operations

    Returns
    -------
    CancelExecutionResponse
        Cancellation result with status

    """
    return await execution_service.cancel_execution(
        flow_run_id=flow_run_id,
        project_id=ctx.project_id,
    )


@router.post(
    "/executions/{execution_id}/re-execute",
    response_model=ExecuteFlowResponse,
    summary="Re-execute a flow from snapshot parameters",
    operation_id="reExecuteFromSnapshot",
)
async def re_execute_from_snapshot(
    execution_id: str,
    request: ReExecuteRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_owner)],
    execution_service: Annotated[ExecutionService, Depends(get_execution_service)],
    flow_service: Annotated[FlowService, Depends(get_flow_service)],
) -> ExecuteFlowResponse:
    """Re-execute a flow using snapshot parameters from a previous execution.

    Parameters
    ----------
    execution_id : str
        ID of the source execution to snapshot parameters from
    request : ReExecuteRequest
        Re-execution request with flow_name and optional parameter_overrides
    ctx : ProjectContext
        Project context with user and project information
    execution_service : ExecutionService
        Service for execution operations
    flow_service : FlowService
        Service for flow operations

    Returns
    -------
    ExecuteFlowResponse
        Execution result with IDs and URLs

    """
    # Validate source execution exists
    metadata = execution_service.get_execution_metadata(ctx.project_id, execution_id)
    if metadata is None:
        raise HTTPException(
            status_code=404,
            detail=f"Source execution {execution_id} not found",
        )

    # Verify the requesting user owns the source execution.
    flow_owner = metadata["username"]
    if flow_owner != ctx.user.username:
        raise HTTPException(
            status_code=403,
            detail="You can only re-execute your own executions",
        )

    return await flow_service.re_execute_from_snapshot(
        flow_name=request.flow_name,
        source_execution_id=execution_id,
        parameter_overrides=request.parameter_overrides,
        username=flow_owner,
        project_id=ctx.project_id,
    )
