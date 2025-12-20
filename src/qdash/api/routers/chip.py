"""Chip router for QDash API."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pymongo import DESCENDING
from qdash.api.lib.project import (
    ProjectContext,
    get_project_context,
    get_project_context_owner,
)
from qdash.api.lib.config_loader import ConfigLoader
from qdash.api.routers.task_file import (
    CALIBTASKS_BASE_PATH,
    collect_tasks_from_directory,
)
from qdash.api.schemas.chip import (
    ChipDatesResponse,
    ChipResponse,
    CreateChipRequest,
    ListChipsResponse,
    ListMuxResponse,
    MuxDetailResponse,
    MuxTask,
)
from qdash.api.services.chip_initializer import ChipInitializer
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.execution_counter import ExecutionCounterDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

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
) -> ListChipsResponse:
    """List all chips in the current project.

    Parameters
    ----------
    ctx : ProjectContext
        Project context with user and project information

    Returns
    -------
    ListChipsResponse
        Wrapped list of available chips

    """
    logger.debug(f"Listing chips for project: {ctx.project_id}")
    chips = ChipDocument.find({"project_id": ctx.project_id}).run()
    return ListChipsResponse(
        chips=[
            ChipResponse(
                chip_id=chip.chip_id,
                size=chip.size,
                topology_id=chip.topology_id,
                qubits=chip.qubits,
                couplings=chip.couplings,
                installed_at=chip.installed_at,
            )
            for chip in chips
        ]
    )


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
        raise HTTPException(status_code=500, detail=f"Failed to create chip: {str(e)}") from e


@router.get(
    "/chips/{chip_id}/dates",
    response_model=ChipDatesResponse,
    summary="Get available dates for a chip",
    operation_id="getChipDates",
)
def get_chip_dates(
    chip_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> ChipDatesResponse:
    """Fetch available dates for a chip from execution counter.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    ctx : ProjectContext
        Project context with user and project information

    Returns
    -------
    ChipDatesResponse
        List of available dates

    """
    logger.debug(f"Fetching dates for chip {chip_id}, project: {ctx.project_id}")
    counter_list = ExecutionCounterDocument.find(
        {"project_id": ctx.project_id, "chip_id": chip_id}
    ).run()
    if not counter_list:
        # Return empty list for newly created chips with no execution history
        logger.debug(f"No execution counter found for chip {chip_id}, returning empty dates list")
        return ChipDatesResponse(data=[])
    # Extract unique dates from the counter
    dates = [counter.date for counter in counter_list]
    # Return dates in a format matching the API schema
    return ChipDatesResponse(data=dates)


@router.get(
    "/chips/{chip_id}", response_model=ChipResponse, summary="Get a chip", operation_id="getChip"
)
def get_chip(
    chip_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> ChipResponse:
    """Get a chip by its ID.

    Parameters
    ----------
    chip_id : str
        ID of the chip to fetch
    ctx : ProjectContext
        Project context with user and project information

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

    chip = ChipDocument.find_one({"project_id": ctx.project_id, "chip_id": chip_id}).run()
    if chip is None:
        raise HTTPException(status_code=404, detail=f"Chip {chip_id} not found")

    return ChipResponse(
        chip_id=chip.chip_id,
        size=chip.size,
        topology_id=chip.topology_id,
        qubits=chip.qubits,
        couplings=chip.couplings,
        installed_at=chip.installed_at,
    )


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


def _build_mux_detail(
    mux_id: int,
    task_names: list[str],
    task_results: dict[str, dict[str, TaskResultHistoryDocument]],
) -> MuxDetailResponse:
    """Build MuxDetailResponse from task results."""
    qids = [str(mux_id * 4 + i) for i in range(4)]
    detail: dict[str, dict[str, MuxTask]] = {}

    for qid in qids:
        detail[qid] = {}
        qid_results = task_results.get(qid, {})

        for task_name in task_names:
            result = qid_results.get(task_name)
            if result is None:
                task_result = MuxTask(name=task_name)
            else:
                task_result = MuxTask(
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
                )
            detail[qid][task_name] = task_result

    return MuxDetailResponse(mux_id=mux_id, detail=detail)


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

    Returns
    -------
    MuxDetailResponse
        Multiplexer details

    """
    logger.debug(f"Fetching mux details for chip {chip_id}, project: {ctx.project_id}")

    # Get task names from task files instead of database
    task_names = _get_task_names_from_files()
    logger.debug("Task names from files: %s", task_names)

    # Calculate qids for this mux
    qids = [str(mux_id * 4 + i) for i in range(4)]

    # Fetch all task results in one query
    all_results = (
        TaskResultHistoryDocument.find(
            {
                "project_id": ctx.project_id,
                "chip_id": chip_id,
                "qid": {"$in": qids},
                "name": {"$in": task_names},
            }
        )
        .sort([("end_at", DESCENDING)])
        .run()
    )

    # Organize results by qid and task name
    task_results: dict[str, dict[str, TaskResultHistoryDocument]] = {}
    for result in all_results:
        if result.qid not in task_results:
            task_results[result.qid] = {}
        if result.name not in task_results[result.qid]:
            task_results[result.qid][result.name] = result

    return _build_mux_detail(mux_id, task_names, task_results=task_results)


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
) -> ListMuxResponse:
    """List all multiplexers for a chip.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    ctx : ProjectContext
        Project context with user and project information

    Returns
    -------
    ListMuxResponse
        List of multiplexer details

    """
    # Get task names from task files instead of database
    task_names = _get_task_names_from_files()

    # Get chip info
    chip = ChipDocument.find_one({"project_id": ctx.project_id, "chip_id": chip_id}).run()
    if chip is None:
        raise HTTPException(
            status_code=404, detail=f"Chip {chip_id} not found in project {ctx.project_id}"
        )

    # Calculate mux number
    mux_num = int(chip.size // 4)
    qids = [str(i) for i in range(chip.size)]

    # Fetch all task results in one query
    all_results = (
        TaskResultHistoryDocument.find(
            {
                "project_id": ctx.project_id,
                "chip_id": chip_id,
                "qid": {"$in": qids},
                "name": {"$in": task_names},
            }
        )
        .sort([("end_at", DESCENDING)])
        .run()
    )

    # Organize results by qid and task name
    task_results: dict[str, dict[str, TaskResultHistoryDocument]] = {}
    for result in all_results:
        if result.qid not in task_results:
            task_results[result.qid] = {}
        if result.name not in task_results[result.qid]:
            task_results[result.qid][result.name] = result

    # Build mux details
    muxes: dict[int, MuxDetailResponse] = {}
    for mux_id in range(mux_num):
        muxes[mux_id] = _build_mux_detail(mux_id, task_names, task_results=task_results)

    return ListMuxResponse(muxes=muxes)
