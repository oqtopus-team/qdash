"""Chip router for QDash API."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pymongo import DESCENDING
from qdash.api.lib.auth import get_current_active_user, get_optional_current_user
from qdash.api.schemas.auth import User
from qdash.api.schemas.chip import (
    ChipDatesResponse,
    ChipResponse,
    CreateChipRequest,
    ListMuxResponse,
    MuxDetailResponse,
    MuxTask,
)
from qdash.api.services.chip_initializer import ChipInitializer
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.execution_counter import ExecutionCounterDocument
from qdash.dbmodel.task import TaskDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

router = APIRouter()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# =============================================================================
# Chip CRUD
# =============================================================================


@router.get("/chip", response_model=list[ChipResponse], summary="Fetch all chips", operation_id="listChips")
def list_chips(
    current_user: Annotated[User, Depends(get_optional_current_user)],
) -> list[ChipResponse]:
    """Fetch all chips.

    Parameters
    ----------
    current_user : User
        Current authenticated user

    Returns
    -------
    list[ChipResponse]
        List of available chips

    """
    logger.debug(f"Listing chips for user: {current_user.username}")
    chips = ChipDocument.find({"username": current_user.username}).run()
    return [
        ChipResponse(
            chip_id=chip.chip_id,
            size=chip.size,
            qubits=chip.qubits,
            couplings=chip.couplings,
            installed_at=chip.installed_at,
        )
        for chip in chips
    ]


@router.post("/chip", response_model=ChipResponse, summary="Create a new chip", operation_id="createChip")
def create_chip(
    request: CreateChipRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> ChipResponse:
    """Create a new chip.

    Parameters
    ----------
    request : CreateChipRequest
        Chip creation request containing chip_id and size
    current_user : User
        Current authenticated user

    Returns
    -------
    ChipResponse
        Created chip information

    Raises
    ------
    HTTPException
        If chip_id already exists or size is invalid

    """
    logger.debug(f"Creating chip {request.chip_id} for user: {current_user.username}")

    try:
        # Use ChipInitializer service to create chip with full initialization
        chip = ChipInitializer.create_chip(
            username=current_user.username,
            chip_id=request.chip_id,
            size=request.size,
        )

        return ChipResponse(
            chip_id=chip.chip_id,
            size=chip.size,
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
    "/chip/{chip_id}/dates",
    response_model=ChipDatesResponse,
    summary="Fetch available dates for a chip",
    operation_id="fetchChipDates",
)
def fetch_chip_dates(
    chip_id: str, current_user: Annotated[User, Depends(get_current_active_user)]
) -> ChipDatesResponse:
    """Fetch available dates for a chip from execution counter.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    current_user : User
        Current authenticated user

    Returns
    -------
    ChipDatesResponse
        List of available dates

    """
    logger.debug(f"Fetching dates for chip {chip_id}, user: {current_user.username}")
    counter_list = ExecutionCounterDocument.find({"chip_id": chip_id, "username": current_user.username}).run()
    if not counter_list:
        # Return empty list for newly created chips with no execution history
        logger.debug(f"No execution counter found for chip {chip_id}, returning empty dates list")
        return ChipDatesResponse(data=[])
    # Extract unique dates from the counter
    dates = [counter.date for counter in counter_list]
    # Return dates in a format matching the API schema
    return ChipDatesResponse(data=dates)


@router.get("/chip/{chip_id}", response_model=ChipResponse, summary="Fetch a chip", operation_id="fetchChip")
def fetch_chip(
    chip_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> ChipResponse:
    """Fetch a chip by its ID.

    Parameters
    ----------
    chip_id : str
        ID of the chip to fetch
    current_user : User
        Current authenticated user

    Returns
    -------
    ChipResponse
        Chip information

    Raises
    ------
    HTTPException
        If chip is not found

    """
    logger.debug(f"Fetching chip {chip_id} for user: {current_user.username}")

    chip = ChipDocument.find_one({"chip_id": chip_id, "username": current_user.username}).run()
    if chip is None:
        raise HTTPException(status_code=404, detail=f"Chip {chip_id} not found")

    return ChipResponse(
        chip_id=chip.chip_id,
        size=chip.size,
        qubits=chip.qubits,
        couplings=chip.couplings,
        installed_at=chip.installed_at,
    )


# =============================================================================
# Mux (Multiplexer) - chip structure information
# =============================================================================


def _build_mux_detail(
    mux_id: int,
    tasks: list,
    task_results: dict[str, dict[str, TaskResultHistoryDocument]],
) -> MuxDetailResponse:
    """Build MuxDetailResponse from task results."""
    qids = [str(mux_id * 4 + i) for i in range(4)]
    detail: dict[str, dict[str, MuxTask]] = {}

    for qid in qids:
        detail[qid] = {}
        qid_results = task_results.get(qid, {})

        for task in tasks:
            result = qid_results.get(task.name)
            if result is None:
                task_result = MuxTask(name=task.name)
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
            detail[qid][task.name] = task_result

    return MuxDetailResponse(mux_id=mux_id, detail=detail)


@router.get(
    "/chip/{chip_id}/mux/{mux_id}",
    response_model=MuxDetailResponse,
    summary="Fetch the multiplexer details",
    operation_id="fetchMuxDetails",
)
def fetch_mux_detail(
    chip_id: str, mux_id: int, current_user: Annotated[User, Depends(get_current_active_user)]
) -> MuxDetailResponse:
    """Fetch the multiplexer details.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    mux_id : int
        ID of the multiplexer
    current_user : User
        Current authenticated user

    Returns
    -------
    MuxDetailResponse
        Multiplexer details

    """
    logger.debug(f"Fetching mux details for chip {chip_id}, user: {current_user.username}")

    # Get all tasks
    tasks = TaskDocument.find({"username": current_user.username}).run()
    task_names = [task.name for task in tasks]
    logger.debug("Tasks: %s", tasks)

    # Calculate qids for this mux
    qids = [str(mux_id * 4 + i) for i in range(4)]

    # Fetch all task results in one query
    all_results = (
        TaskResultHistoryDocument.find(
            {
                "username": current_user.username,
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

    return _build_mux_detail(mux_id, tasks, task_results=task_results)


@router.get(
    "/chip/{chip_id}/mux",
    response_model=ListMuxResponse,
    summary="Fetch the multiplexers",
    operation_id="listMuxes",
    response_model_exclude_none=True,
)
def list_muxes(chip_id: str, current_user: Annotated[User, Depends(get_current_active_user)]) -> ListMuxResponse:
    """Fetch the multiplexers.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    current_user : User
        Current authenticated user

    Returns
    -------
    ListMuxResponse
        List of multiplexer details

    """
    # Get all tasks
    tasks = TaskDocument.find({"username": current_user.username}).run()
    task_names = [task.name for task in tasks]

    # Get chip info
    chip = ChipDocument.find_one({"chip_id": chip_id, "username": current_user.username}).run()
    if chip is None:
        raise HTTPException(status_code=404, detail=f"Chip {chip_id} not found for user {current_user.username}")

    # Calculate mux number
    mux_num = int(chip.size // 4)
    qids = [str(i) for i in range(chip.size)]

    # Fetch all task results in one query
    all_results = (
        TaskResultHistoryDocument.find(
            {
                "username": current_user.username,
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
        muxes[mux_id] = _build_mux_detail(mux_id, tasks, task_results=task_results)

    return ListMuxResponse(muxes=muxes)
