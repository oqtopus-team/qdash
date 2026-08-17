"""Execution router for QDash API.

This module provides HTTP endpoints for execution-related operations.
Business logic is delegated to ExecutionService for better testability.
"""

from __future__ import annotations

import logging
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from starlette.exceptions import HTTPException

from qdash.api.dependencies import get_execution_service, get_flow_service
from qdash.api.lib.project import (
    ProjectContext,
    get_project_context,
    get_project_context_editor,
)
from qdash.api.schemas.error import Detail
from qdash.api.schemas.execution import (
    ArtifactPreviewResponse,
    CancelExecutionResponse,
    ExecutionLockStatusResponse,
    ExecutionResponseDetail,
    ListExecutionsResponse,
    ReExecuteRequest,
)
from qdash.api.schemas.flow import ExecuteFlowResponse
from qdash.api.services.artifact_preview_service import preview_netcdf
from qdash.api.services.execution_service import ExecutionService
from qdash.api.services.flow_service import FlowService
from qdash.common.config.path_resolver import resolve_calib_data_path

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
    resolved_path = resolve_calib_data_path(path)
    if not resolved_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"File not found: {path}",
        )
    # FileResponse sets Content-Length, avoiding chunked encoding
    return FileResponse(resolved_path, media_type="image/png")


@router.get(
    "/executions/artifact",
    responses={404: {"model": Detail}},
    response_class=FileResponse,
    summary="Download a calibration artifact by its path",
    operation_id="downloadArtifactByPath",
)
def download_artifact_by_path(path: str) -> FileResponse:
    """Download a calibration artifact such as figure JSON or raw NetCDF data."""
    resolved_path = resolve_calib_data_path(path)
    if not resolved_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    return FileResponse(resolved_path, filename=resolved_path.name)


def _unique_archive_name(path: Path, used_names: set[str]) -> str:
    """Return a stable, unique basename for a ZIP member."""
    candidate = path.name
    counter = 2
    while candidate in used_names:
        candidate = f"{path.stem}_{counter}{path.suffix}"
        counter += 1
    used_names.add(candidate)
    return candidate


@router.get(
    "/executions/artifacts/archive",
    responses={
        200: {"content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}}},
        404: {"model": Detail},
    },
    response_class=FileResponse,
    summary="Download calibration artifacts as a ZIP archive",
    operation_id="downloadArtifactsAsArchive",
)
def download_artifacts_as_archive(
    paths: Annotated[list[str], Query(min_length=1, max_length=100)],
) -> FileResponse:
    """Download multiple figure JSON and raw NetCDF artifacts as one ZIP file."""
    resolved_paths: list[Path] = []
    for path in paths:
        resolved_path = resolve_calib_data_path(path)
        if not resolved_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {path}")
        resolved_paths.append(resolved_path)

    with NamedTemporaryFile(delete=False, suffix=".zip") as temporary_file:
        archive_path = Path(temporary_file.name)

    try:
        used_names: set[str] = set()
        with ZipFile(archive_path, mode="w", compression=ZIP_DEFLATED) as zip_file:
            for resolved_path in resolved_paths:
                zip_file.write(
                    resolved_path,
                    arcname=_unique_archive_name(resolved_path, used_names),
                )
    except Exception:
        archive_path.unlink(missing_ok=True)
        raise

    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename="artifacts.zip",
        background=BackgroundTask(archive_path.unlink, missing_ok=True),
    )


@router.get(
    "/executions/artifact/preview",
    responses={400: {"model": Detail}, 404: {"model": Detail}},
    response_model=ArtifactPreviewResponse,
    summary="Preview a NetCDF calibration artifact",
    operation_id="previewArtifactByPath",
)
def preview_artifact_by_path(path: str) -> ArtifactPreviewResponse:
    """Return a size-limited table preview of a NetCDF calibration artifact."""
    resolved_path = resolve_calib_data_path(path)
    if not resolved_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    if resolved_path.suffix.lower() != ".nc":
        raise HTTPException(status_code=400, detail="Only NetCDF (.nc) artifacts can be previewed")
    try:
        return preview_netcdf(resolved_path)
    except (OSError, RuntimeError, ValueError) as error:
        raise HTTPException(
            status_code=400,
            detail=f"Unable to preview NetCDF artifact: {error}",
        ) from error


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
    total = execution_service.count_executions(
        project_id=ctx.project_id,
        chip_id=chip_id,
    )
    return ListExecutionsResponse(
        executions=executions,
        total=total,
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
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
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
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
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
