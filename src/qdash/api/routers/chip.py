"""Chip router for QDash API.

This module provides HTTP endpoints for chip-related operations.
Business logic is delegated to ChipService for better testability.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from qdash.api.dependencies import get_chip_service  # noqa: TCH002
from qdash.api.lib.config_loader import ConfigLoader
from qdash.api.lib.project import (  # noqa: TCH002
    ProjectContext,
    get_project_context,
    get_project_context_owner,
)
from qdash.api.routers.task_file import (
    CALIBTASKS_BASE_PATH,
    collect_tasks_from_directory,
)
from qdash.api.schemas.chip import (
    ChipDatesResponse,
    ChipResponse,
    ChipSummaryResponse,
    CouplingResponse,
    CreateChipRequest,
    ListChipsResponse,
    ListChipsSummaryResponse,
    ListCouplingsResponse,
    ListMuxResponse,
    ListQubitsResponse,
    MetricHeatmapResponse,
    MetricsSummaryResponse,
    MuxDetailResponse,
    QubitResponse,
)
from qdash.api.services.chip_initializer import ChipInitializer
from qdash.api.services.chip_service import ChipService  # noqa: TCH002

router = APIRouter()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# =============================================================================
# Chip CRUD
# =============================================================================


@router.get(
    "/chips", response_model=ListChipsResponse, summary="List all chips", operation_id="listChips"
)
def list_chips(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    chip_service: Annotated[ChipService, Depends(get_chip_service)],
) -> ListChipsResponse:
    """List all chips in the current project.

    Parameters
    ----------
    ctx : ProjectContext
        Project context with user and project information
    chip_service : ChipService
        Service for chip operations

    Returns
    -------
    ListChipsResponse
        Wrapped list of available chips

    """
    logger.debug(f"Listing chips for project: {ctx.project_id}")
    chips = chip_service.list_chips(ctx.project_id)
    return ListChipsResponse(chips=chips)


@router.get(
    "/chips/summary",
    response_model=ListChipsSummaryResponse,
    summary="List all chips (lightweight)",
    operation_id="listChipsSummary",
)
def list_chips_summary(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    chip_service: Annotated[ChipService, Depends(get_chip_service)],
) -> ListChipsSummaryResponse:
    """List all chips with summary information only (no qubit/coupling data).

    This endpoint returns ~1KB vs ~300KB+ for full chip data.
    Use this for chip selectors and listings where qubit data is not needed.
    """
    logger.debug(f"Listing chip summaries for project: {ctx.project_id}")
    summaries = chip_service.list_chips_summary(ctx.project_id)
    return ListChipsSummaryResponse(chips=summaries, total=len(summaries))


@router.post(
    "/chips", response_model=ChipResponse, summary="Create a new chip", operation_id="createChip"
)
def create_chip(
    request: CreateChipRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_owner)],
) -> ChipResponse:
    """Create a new chip in the current project.

    Parameters
    ----------
    request : CreateChipRequest
        Chip creation request containing chip_id and size
    ctx : ProjectContext
        Project context with owner permission

    Returns
    -------
    ChipResponse
        Created chip information

    Raises
    ------
    HTTPException
        If chip_id already exists or size is invalid

    """
    logger.debug(f"Creating chip {request.chip_id} for project: {ctx.project_id}")

    try:
        # Use ChipInitializer service to create chip with full initialization
        chip = ChipInitializer.create_chip(
            username=ctx.user.username,
            chip_id=request.chip_id,
            size=request.size,
            project_id=ctx.project_id,
            topology_id=request.topology_id,
        )

        return ChipResponse(
            chip_id=chip.chip_id,
            size=chip.size,
            topology_id=chip.topology_id,
            qubits=chip.qubits,
            couplings=chip.couplings,
            installed_at=chip.installed_at,
        )
    except ValueError as e:
        # Handle validation errors (duplicate chip, invalid size, etc.)
        logger.warning(f"Validation error creating chip {request.chip_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Error creating chip {request.chip_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create chip: {e!s}") from e


@router.get(
    "/chips/{chip_id}/dates",
    response_model=ChipDatesResponse,
    summary="Get available dates for a chip",
    operation_id="getChipDates",
)
def get_chip_dates(
    chip_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    chip_service: Annotated[ChipService, Depends(get_chip_service)],
) -> ChipDatesResponse:
    """Fetch available dates for a chip from execution counter.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    ctx : ProjectContext
        Project context with user and project information
    chip_service : ChipService
        Service for chip operations

    Returns
    -------
    ChipDatesResponse
        List of available dates

    """
    logger.debug(f"Fetching dates for chip {chip_id}, project: {ctx.project_id}")
    dates = chip_service.get_chip_dates(ctx.project_id, chip_id)
    return ChipDatesResponse(data=dates)


@router.get(
    "/chips/{chip_id}", response_model=ChipResponse, summary="Get a chip", operation_id="getChip"
)
def get_chip(
    chip_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    chip_service: Annotated[ChipService, Depends(get_chip_service)],
) -> ChipResponse:
    """Get a chip by its ID.

    Parameters
    ----------
    chip_id : str
        ID of the chip to fetch
    ctx : ProjectContext
        Project context with user and project information
    chip_service : ChipService
        Service for chip operations

    Returns
    -------
    ChipResponse
        Chip information

    Raises
    ------
    HTTPException
        If chip is not found

    """
    logger.debug(f"Fetching chip {chip_id} for project: {ctx.project_id}")

    chip = chip_service.get_chip(ctx.project_id, chip_id)
    if chip is None:
        raise HTTPException(status_code=404, detail=f"Chip {chip_id} not found")

    return chip


# =============================================================================
# Mux (Multiplexer) - chip structure information
# =============================================================================


def _get_task_names_from_files() -> list[str]:
    """Get task names from task files instead of database.

    Returns
    -------
        List of task names from task files

    """
    # Get default backend from settings
    default_backend = "qubex"  # fallback default
    try:
        settings = ConfigLoader.load_settings()
        ui_settings = settings.get("ui", {})
        task_files_settings = ui_settings.get("task_files", {})
        default_backend = task_files_settings.get("default_backend", "qubex")
    except Exception as e:
        logger.warning(f"Failed to load settings: {e}")

    # Get tasks from task files
    backend_path = CALIBTASKS_BASE_PATH / default_backend
    if not backend_path.exists() or not backend_path.is_dir():
        logger.warning(f"Backend directory not found: {backend_path}")
        return []

    tasks = collect_tasks_from_directory(backend_path, backend_path)
    return [task.name for task in tasks]


@router.get(
    "/chips/{chip_id}/muxes/{mux_id}",
    response_model=MuxDetailResponse,
    summary="Get multiplexer details",
    operation_id="getChipMux",
)
def get_chip_mux(
    chip_id: str,
    mux_id: int,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    chip_service: Annotated[ChipService, Depends(get_chip_service)],
) -> MuxDetailResponse:
    """Get the multiplexer details.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    mux_id : int
        ID of the multiplexer
    ctx : ProjectContext
        Project context with user and project information
    chip_service : ChipService
        Service for chip operations

    Returns
    -------
    MuxDetailResponse
        Multiplexer details

    """
    logger.debug(f"Fetching mux details for chip {chip_id}, project: {ctx.project_id}")

    # Get task names from task files instead of database
    task_names = _get_task_names_from_files()
    logger.debug("Task names from files: %s", task_names)

    return chip_service.get_mux_detail(
        project_id=ctx.project_id,
        chip_id=chip_id,
        mux_id=mux_id,
        task_names=task_names,
    )


@router.get(
    "/chips/{chip_id}/muxes",
    response_model=ListMuxResponse,
    summary="List all multiplexers for a chip",
    operation_id="listChipMuxes",
    response_model_exclude_none=True,
)
def list_chip_muxes(
    chip_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    chip_service: Annotated[ChipService, Depends(get_chip_service)],
) -> ListMuxResponse:
    """List all multiplexers for a chip.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    ctx : ProjectContext
        Project context with user and project information
    chip_service : ChipService
        Service for chip operations

    Returns
    -------
    ListMuxResponse
        List of multiplexer details

    """
    # Get task names from task files instead of database
    task_names = _get_task_names_from_files()

    # Get chip size
    chip_size = chip_service.get_chip_size(ctx.project_id, chip_id)
    if chip_size is None:
        raise HTTPException(
            status_code=404, detail=f"Chip {chip_id} not found in project {ctx.project_id}"
        )

    muxes = chip_service.get_all_mux_details(
        project_id=ctx.project_id,
        chip_id=chip_id,
        chip_size=chip_size,
        task_names=task_names,
    )

    return ListMuxResponse(muxes=muxes)


# =============================================================================
# Optimized endpoints for scalability (256+ qubits)
# =============================================================================


@router.get(
    "/chips/{chip_id}/summary",
    response_model=ChipSummaryResponse,
    summary="Get chip summary (lightweight)",
    operation_id="getChipSummary",
)
def get_chip_summary(
    chip_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    chip_service: Annotated[ChipService, Depends(get_chip_service)],
) -> ChipSummaryResponse:
    """Get chip summary without embedded qubit/coupling data.

    This endpoint returns ~0.3KB vs ~300KB+ for full chip data.
    Use this when you only need chip metadata (size, topology, dates).

    Parameters
    ----------
    chip_id : str
        ID of the chip
    ctx : ProjectContext
        Project context with user and project information
    chip_service : ChipService
        Service for chip operations

    Returns
    -------
    ChipSummaryResponse
        Chip summary information

    """
    logger.debug(f"Fetching chip summary for {chip_id}, project: {ctx.project_id}")
    summary = chip_service.get_chip_summary(ctx.project_id, chip_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Chip {chip_id} not found")
    return summary


@router.get(
    "/chips/{chip_id}/qubits",
    response_model=ListQubitsResponse,
    summary="List qubits for a chip",
    operation_id="listChipQubits",
)
def list_chip_qubits(
    chip_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    chip_service: Annotated[ChipService, Depends(get_chip_service)],
    limit: Annotated[int, Query(le=256, ge=1)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    qids: Annotated[list[str] | None, Query()] = None,
) -> ListQubitsResponse:
    """List qubits for a chip with pagination.

    Retrieves qubit data from the separate QubitDocument collection.
    Supports filtering by specific qubit IDs.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    ctx : ProjectContext
        Project context with user and project information
    chip_service : ChipService
        Service for chip operations
    limit : int
        Maximum number of qubits to return (default 50, max 256)
    offset : int
        Number of qubits to skip for pagination
    qids : list[str] | None
        Optional list of specific qubit IDs to fetch

    Returns
    -------
    ListQubitsResponse
        List of qubits with pagination info

    """
    logger.debug(f"Listing qubits for chip {chip_id}, project: {ctx.project_id}")
    qubits, total = chip_service.list_qubits(
        project_id=ctx.project_id,
        chip_id=chip_id,
        limit=limit,
        offset=offset,
        qids=qids,
    )
    return ListQubitsResponse(qubits=qubits, total=total, limit=limit, offset=offset)


@router.get(
    "/chips/{chip_id}/qubits/{qid}",
    response_model=QubitResponse,
    summary="Get a single qubit",
    operation_id="getChipQubit",
)
def get_chip_qubit(
    chip_id: str,
    qid: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    chip_service: Annotated[ChipService, Depends(get_chip_service)],
) -> QubitResponse:
    """Get a single qubit by ID.

    This is 10-18x faster than fetching the full chip and extracting one qubit.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    qid : str
        ID of the qubit
    ctx : ProjectContext
        Project context with user and project information
    chip_service : ChipService
        Service for chip operations

    Returns
    -------
    QubitResponse
        Qubit data

    """
    logger.debug(f"Fetching qubit {qid} for chip {chip_id}, project: {ctx.project_id}")
    qubit = chip_service.get_qubit(ctx.project_id, chip_id, qid)
    if qubit is None:
        raise HTTPException(status_code=404, detail=f"Qubit {qid} not found in chip {chip_id}")
    return qubit


@router.get(
    "/chips/{chip_id}/couplings",
    response_model=ListCouplingsResponse,
    summary="List couplings for a chip",
    operation_id="listChipCouplings",
)
def list_chip_couplings(
    chip_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    chip_service: Annotated[ChipService, Depends(get_chip_service)],
    limit: Annotated[int, Query(le=512, ge=1)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ListCouplingsResponse:
    """List couplings for a chip with pagination.

    Retrieves coupling data from the separate CouplingDocument collection.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    ctx : ProjectContext
        Project context with user and project information
    chip_service : ChipService
        Service for chip operations
    limit : int
        Maximum number of couplings to return (default 100, max 512)
    offset : int
        Number of couplings to skip for pagination

    Returns
    -------
    ListCouplingsResponse
        List of couplings with pagination info

    """
    logger.debug(f"Listing couplings for chip {chip_id}, project: {ctx.project_id}")
    couplings, total = chip_service.list_couplings(
        project_id=ctx.project_id,
        chip_id=chip_id,
        limit=limit,
        offset=offset,
    )
    return ListCouplingsResponse(couplings=couplings, total=total, limit=limit, offset=offset)


@router.get(
    "/chips/{chip_id}/couplings/{coupling_id}",
    response_model=CouplingResponse,
    summary="Get a single coupling",
    operation_id="getChipCoupling",
)
def get_chip_coupling(
    chip_id: str,
    coupling_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    chip_service: Annotated[ChipService, Depends(get_chip_service)],
) -> CouplingResponse:
    """Get a single coupling by ID.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    coupling_id : str
        ID of the coupling (e.g., "0-1")
    ctx : ProjectContext
        Project context with user and project information
    chip_service : ChipService
        Service for chip operations

    Returns
    -------
    CouplingResponse
        Coupling data

    """
    logger.debug(f"Fetching coupling {coupling_id} for chip {chip_id}, project: {ctx.project_id}")
    coupling = chip_service.get_coupling(ctx.project_id, chip_id, coupling_id)
    if coupling is None:
        raise HTTPException(
            status_code=404, detail=f"Coupling {coupling_id} not found in chip {chip_id}"
        )
    return coupling


@router.get(
    "/chips/{chip_id}/metrics/summary",
    response_model=MetricsSummaryResponse,
    summary="Get aggregated metrics summary",
    operation_id="getChipMetricsSummary",
)
def get_chip_metrics_summary(
    chip_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    chip_service: Annotated[ChipService, Depends(get_chip_service)],
) -> MetricsSummaryResponse:
    """Get aggregated metrics summary for a chip.

    Computes statistics (averages, counts) on the database side.
    Returns ~0.1KB of data, ideal for dashboard overview.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    ctx : ProjectContext
        Project context with user and project information
    chip_service : ChipService
        Service for chip operations

    Returns
    -------
    MetricsSummaryResponse
        Aggregated metrics summary

    """
    logger.debug(f"Fetching metrics summary for chip {chip_id}, project: {ctx.project_id}")
    summary = chip_service.get_metrics_summary(ctx.project_id, chip_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Chip {chip_id} not found")
    return summary


@router.get(
    "/chips/{chip_id}/metrics/heatmap/{metric}",
    response_model=MetricHeatmapResponse,
    summary="Get heatmap data for a single metric",
    operation_id="getChipMetricHeatmap",
)
def get_chip_metric_heatmap(
    chip_id: str,
    metric: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    chip_service: Annotated[ChipService, Depends(get_chip_service)],
) -> MetricHeatmapResponse:
    """Get heatmap data for a single metric.

    Returns only the values needed for heatmap visualization (~5KB).
    Much more efficient than fetching full chip data (~300KB+).

    Supported metrics:
    - Qubit: t1, t2_echo, t2_star, qubit_frequency, anharmonicity,
             average_readout_fidelity, x90_gate_fidelity, x180_gate_fidelity
    - Coupling: zx90_gate_fidelity, bell_state_fidelity, static_zz_interaction

    Parameters
    ----------
    chip_id : str
        ID of the chip
    metric : str
        Name of the metric to retrieve
    ctx : ProjectContext
        Project context with user and project information
    chip_service : ChipService
        Service for chip operations

    Returns
    -------
    MetricHeatmapResponse
        Metric values keyed by qubit/coupling ID

    """
    logger.debug(f"Fetching heatmap for {metric} on chip {chip_id}, project: {ctx.project_id}")
    heatmap = chip_service.get_metric_heatmap(ctx.project_id, chip_id, metric)
    if heatmap is None:
        raise HTTPException(status_code=404, detail=f"Chip {chip_id} not found")
    return heatmap
