from __future__ import annotations

import logging
from typing import Annotated, Any

import pendulum
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from pymongo import ASCENDING, DESCENDING
from qdash.api.lib.auth import get_current_active_user, get_optional_current_user
from qdash.api.schemas.auth import User
from qdash.api.services.chip_initializer import ChipInitializer
from qdash.api.services.response_processor import response_processor
from qdash.datamodel.task import OutputParameterModel
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.chip_history import ChipHistoryDocument
from qdash.dbmodel.execution_counter import ExecutionCounterDocument
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.task import TaskDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

router = APIRouter()

# ロガーの設定
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
QUBIT_FIDELITY_THRESHOLD = 0.99
COUPLING_FIDELITY_THRESHOLD = 0.75


class ExecutionResponseSummary(BaseModel):
    """ExecutionResponseSummaryV2 is a Pydantic model that represents the summary of an execution response.

    Attributes
    ----------
        name (str): The name of the execution.
        status (str): The current status of the execution.
        start_at (str): The start time of the execution.
        end_at (str): The end time of the execution.
        elapsed_time (str): The total elapsed time of the execution.

    """

    name: str
    execution_id: str
    status: str
    start_at: str
    end_at: str
    elapsed_time: str
    tags: list[str]
    note: dict


class Task(BaseModel):
    """Task is a Pydantic model that represents a task."""

    task_id: str | None = None
    qid: str | None = None
    name: str = ""  # Default empty string for name
    upstream_id: str | None = None
    status: str = "pending"  # Default status
    message: str | None = None
    input_parameters: dict[str, Any] | None = None
    output_parameters: dict[str, Any] | None = None
    output_parameter_names: list[str] | None = None
    note: dict[str, Any] | None = None
    figure_path: list[str] | None = None
    json_figure_path: list[str] | None = None
    raw_data_path: list[str] | None = None
    start_at: str | None = None
    end_at: str | None = None
    elapsed_time: str | None = None
    task_type: str | None = None
    default_view: bool = True
    over_threshold: bool = False


class ExecutionResponseDetail(BaseModel):
    """ExecutionResponseDetailV2 is a Pydantic model that represents the detail of an execution response.

    Attributes
    ----------
        name (str): The name of the execution.
        status (str): The current status of the execution.
        start_at (str): The start time

    """

    name: str
    status: str
    start_at: str
    end_at: str
    elapsed_time: str
    task: list[Task]
    note: dict


class ChipResponse(BaseModel):
    """Chip is a Pydantic model that represents a chip.

    Attributes
    ----------
        chip_id (str): The ID of the chip.
        name (str): The name of the chip.

    """

    chip_id: str
    size: int = 64
    qubits: dict[str, Any] = {}
    couplings: dict[str, Any] = {}
    installed_at: str = ""


class CreateChipRequest(BaseModel):
    """Request model for creating a new chip.

    Attributes
    ----------
        chip_id (str): The ID of the chip to create.
        size (int): The size of the chip (64, 144, 256, or 1024).

    """

    chip_id: str
    size: int = 64


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


class ChipDatesResponse(BaseModel):
    """Response model for chip dates."""

    data: list[str]


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
    list[str]
        List of available dates in ISO format

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
def fetch_chip(chip_id: str, current_user: Annotated[User, Depends(get_current_active_user)]) -> ChipResponse:
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

    """
    logger.debug(f"Fetching chip {chip_id} for user: {current_user.username}")

    chip = ChipDocument.find_one({"chip_id": chip_id, "username": current_user.username}).run()
    return ChipResponse(
        chip_id=chip.chip_id,
        size=chip.size,
        qubits=chip.qubits,
        couplings=chip.couplings,
        installed_at=chip.installed_at,
    )


@router.get(
    "/chip/{chip_id}/execution",
    response_model=list[ExecutionResponseSummary],
    summary="Fetch executions",
    operation_id="listExecutionsByChipId",
)
def list_executions_by_chip_id(
    chip_id: str, current_user: Annotated[User, Depends(get_current_active_user)]
) -> list[ExecutionResponseSummary]:
    """Fetch all executions for a given chip.

    Parameters
    ----------
    chip_id : str
        ID of the chip to fetch executions for
    current_user : str
        Current user ID from authentication

    Returns
    -------
    list[ExecutionResponseSummary]
        List of executions for the chip

    """
    logger.debug(f"Listing executions for chip {chip_id}, user: {current_user.username}")
    executions = (
        ExecutionHistoryDocument.find(
            {"chip_id": chip_id, "username": current_user.username}, sort=[("start_at", DESCENDING)]
        )
        .limit(50)
        .run()
    )
    return [
        ExecutionResponseSummary(
            name=f"{execution.name}-{execution.execution_id}",
            execution_id=execution.execution_id,
            status=execution.status,
            start_at=execution.start_at,
            end_at=execution.end_at,
            elapsed_time=execution.elapsed_time,
            tags=execution.tags,
            note=execution.note,
        )
        for execution in executions
    ]


def flatten_tasks(task_results: dict) -> list[dict]:
    """Flatten the task results into a list of tasks.

    Parameters
    ----------
    task_results : dict
        Task results to flatten

    Returns
    -------
    list[dict]
        Flattened list of tasks, sorted by completion time within qid groups

    """
    # グループごとのタスクを保持する辞書
    grouped_tasks: dict[str, list[dict]] = {}
    logger.debug("Flattening task_results: %s", task_results)

    for key, result in task_results.items():
        if not isinstance(result, dict):
            result = result.model_dump()  # noqa: PLW2901
        logger.debug("Processing key: %s, result: %s", key, result)

        # グローバルタスクの処理
        if "global_tasks" in result:
            logger.debug("Found %d global_tasks in %s", len(result["global_tasks"]), key)
            if "global" not in grouped_tasks:
                grouped_tasks["global"] = []
            grouped_tasks["global"].extend(result["global_tasks"])

        if "system_tasks" in result:
            logger.debug("Found %d system_tasks in %s", len(result["system_tasks"]), key)
            if "system" not in grouped_tasks:
                grouped_tasks["system"] = []
            grouped_tasks["system"].extend(result["system_tasks"])

        # キュービットタスクの処理
        if "qubit_tasks" in result:
            for qid, tasks in result["qubit_tasks"].items():
                logger.debug("Found %d qubit_tasks under qid %s", len(tasks), qid)
                if qid not in grouped_tasks:
                    grouped_tasks[qid] = []
                for task in tasks:
                    if "qid" not in task or not task["qid"]:
                        task["qid"] = qid
                    grouped_tasks[qid].append(task)

        # カップリングタスクの処理
        if "coupling_tasks" in result:
            for sub_key, tasks in result["coupling_tasks"].items():
                logger.debug("Found %d coupling_tasks under key %s", len(tasks), sub_key)
                if "coupling" not in grouped_tasks:
                    grouped_tasks["coupling"] = []
                grouped_tasks["coupling"].extend(tasks)

    # 各グループ内でstart_atによるソート
    for group_tasks in grouped_tasks.values():
        group_tasks.sort(key=lambda x: x.get("start_at", "") or "9999-12-31T23:59:59")

    # グループ自体をstart_atの早い順にソート
    def get_group_completion_time(group: list[dict]) -> str:
        completed_tasks = [t for t in group if t.get("start_at")]
        if not completed_tasks:
            return "9999-12-31T23:59:59"
        return max(str(t["start_at"]) for t in completed_tasks)

    sorted_groups = sorted(grouped_tasks.items(), key=lambda x: get_group_completion_time(x[1]))

    # ソートされたグループを1つのリストに結合
    flat_tasks = []
    for _, tasks in sorted_groups:
        flat_tasks.extend(tasks)

    logger.debug("Total flattened tasks: %d", len(flat_tasks))
    return flat_tasks


@router.get(
    "/chip/{chip_id}/execution/{execution_id}",
    response_model=ExecutionResponseDetail,
    summary="Fetch an execution by its ID",
    operation_id="fetchExecutionByChipId",
)
def fetch_execution_by_chip_id(
    chip_id: str, execution_id: str, current_user: Annotated[User, Depends(get_current_active_user)]
) -> ExecutionResponseDetail:
    """Return the execution detail by its ID.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    execution_id : str
        ID of the execution to fetch
    current_user : User
        Current authenticated user

    Returns
    -------
    ExecutionResponseDetail
        Detailed execution information

    """
    logger.debug(f"Fetching execution {execution_id} for chip {chip_id}, user: {current_user.username}")
    execution = ExecutionHistoryDocument.find_one(
        {"execution_id": execution_id, "chip_id": chip_id, "username": current_user.username}
    ).run()
    flat_tasks = flatten_tasks(execution.task_results)
    tasks = [Task(**task) for task in flat_tasks]

    return ExecutionResponseDetail(
        name=f"{execution.name}-{execution.execution_id}",
        status=execution.status,
        start_at=execution.start_at,
        end_at=execution.end_at,
        elapsed_time=execution.elapsed_time,
        task=tasks,
        note=execution.note,
    )


class MuxDetailResponse(BaseModel):
    """MuxDetailResponse is a Pydantic model that represents the response for fetching the multiplexer details."""

    mux_id: int
    detail: dict[str, dict[str, Task]]


class ListMuxResponse(BaseModel):
    """ListMuxResponse is a Pydantic model that represents the response for fetching the multiplexers."""

    muxes: dict[int, MuxDetailResponse]


def _build_mux_detail(
    mux_id: int,
    tasks: list,
    task_results: dict[str, dict[str, TaskResultHistoryDocument]],
) -> MuxDetailResponse:
    qids = [str(mux_id * 4 + i) for i in range(4)]
    detail: dict[str, dict[str, Task]] = {}

    for qid in qids:
        detail[qid] = {}
        qid_results = task_results.get(qid, {})

        for task in tasks:
            result = qid_results.get(task.name)
            if result is None:
                task_result = Task(name=task.name)
            else:
                task_result = Task(
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
        Multiplexdetails

    """
    # Get all tasks
    tasks = TaskDocument.find({"username": current_user.username}).run()
    task_names = [task.name for task in tasks]

    # Get chip info
    chip = ChipDocument.find_one({"chip_id": chip_id, "username": current_user.username}).run()
    if chip is None:
        raise ValueError(f"Chip {chip_id} not found for user {current_user.username}")

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


class LatestTaskGroupedByChipResponse(BaseModel):
    """ChipTaskResponse is a Pydantic model that represents the response for fetching the tasks of a chip."""

    task_name: str
    result: dict[str, Task]


@router.get(
    "/chip/{chip_id}/task/qubit/{task_name}/history/{recorded_date}",
    summary="Fetch historical task results",
    operation_id="fetchHistoricalQubitTaskGroupedByChip",
    response_model=LatestTaskGroupedByChipResponse,
    response_model_exclude_none=True,
)
def fetch_historical_qubit_task_grouped_by_chip(
    chip_id: str,
    task_name: str,
    recorded_date: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> LatestTaskGroupedByChipResponse:
    """Fetch historical task results for a specific date.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    task_name : str
        Name of the task to fetch
    recorded_date : str
        Date to fetch history for (ISO format YYYY-MM-DD)
    current_user : User
        Current authenticated user

    Returns
    -------
    LatestTaskGroupedByChipResponse
        Historical task results for all qubits on the specified date

    """
    logger.debug(f"Fetching historical task results for chip {chip_id}, task {task_name}, date {recorded_date}")

    # Get chip info
    chip = ChipHistoryDocument.find_one(
        {"chip_id": chip_id, "username": current_user.username, "recorded_date": recorded_date}
    ).run()
    if chip is None:
        raise ValueError(f"Chip {chip_id} not found for user {current_user.username}")

    # Get qids
    qids = list(chip.qubits.keys())
    parsed_date = pendulum.from_format(recorded_date, "YYYYMMDD", tz="Asia/Tokyo")

    start_time = parsed_date.start_of("day")
    end_time = parsed_date.end_of("day")
    all_results = (
        TaskResultHistoryDocument.find(
            {
                "username": current_user.username,
                "chip_id": chip_id,
                "name": task_name,
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
            task_result = Task(
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
            task_result = Task(name=task_name)
        results[qid] = task_result

    response = LatestTaskGroupedByChipResponse(task_name=task_name, result=results)
    return response_processor.process_task_response(response, task_name)


@router.get(
    "/chip/{chip_id}/task/qubit/{task_name}/latest",
    summary="Fetch latest qubit task results with optional outlier filtering",
    operation_id="fetchLatestQubitTaskGroupedByChip",
    response_model=LatestTaskGroupedByChipResponse,
    response_model_exclude_none=True,
)
def fetch_latest_qubit_task_grouped_by_chip(
    chip_id: str, task_name: str, current_user: Annotated[User, Depends(get_current_active_user)]
) -> LatestTaskGroupedByChipResponse:
    """Fetch latest qubit task results with optional defensive outlier filtering."""
    logger.debug(f"Fetching qubit tasks for chip {chip_id}, user: {current_user.username}")

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
                "name": task_name,
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
            task_result = Task(
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
            task_result = Task(name=task_name)
        results[qid] = task_result

    response = LatestTaskGroupedByChipResponse(task_name=task_name, result=results)
    return response_processor.process_task_response(response, task_name)


class TaskHistoryResponse(BaseModel):
    name: str
    data: dict[str, Task]


@router.get(
    "/chip/{chip_id}/task/qubit/{qid}/task/{task_name}",
    summary="Fetch Qubit Task History",
    operation_id="fetchQubitTaskHistory",
    response_model=TaskHistoryResponse,
    response_model_exclude_none=True,
)
def fetch_qubit_task_history(
    chip_id: str, qid: str, task_name: str, current_user: Annotated[User, Depends(get_optional_current_user)]
) -> TaskHistoryResponse:
    """Fetch latest qubit task results with optional defensive outlier filtering."""
    logger.debug(f"Fetching qubit tasks for chip {chip_id}, user: {current_user.username}")

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
                "name": task_name,
                "qid": qid,
            }
        )
        .sort([("end_at", DESCENDING)])
        .run()
    )

    # Organize results by qid
    data = {}
    for result in all_results:
        data[result.task_id] = Task(
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

    return TaskHistoryResponse(name=task_name, data=data)


@router.get(
    "/chip/{chip_id}/task/coupling/{task_name}/history/{recorded_date}",
    summary="Fetch historical task results",
    operation_id="fetchHistoricalCouplingTaskGroupedByChip",
    response_model=LatestTaskGroupedByChipResponse,
    response_model_exclude_none=True,
)
def fetch_historical_coupling_task_grouped_by_chip(
    chip_id: str,
    task_name: str,
    recorded_date: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> LatestTaskGroupedByChipResponse:
    """Fetch historical task results for a specific date.

    Parameters
    ----------
    chip_id : str
        ID of the chip
    task_name : str
        Name of the task to fetch
    recorded_date : str
        Date to fetch history for (ISO format YYYY-MM-DD)
    current_user : User
        Current authenticated user

    Returns
    -------
    LatestTaskGroupedByChipResponse
        Historical task results for all qubits on the specified date

    """
    logger.debug(f"Fetching historical task results for chip {chip_id}, task {task_name}, date {recorded_date}")

    # Get chip info
    chip = ChipHistoryDocument.find_one(
        {"chip_id": chip_id, "username": current_user.username, "recorded_date": recorded_date}
    ).run()
    if chip is None:
        raise ValueError(f"Chip {chip_id} not found for user {current_user.username}")

    # Get qids
    qids = list(chip.couplings.keys())

    parsed_date = pendulum.from_format(recorded_date, "YYYYMMDD", tz="Asia/Tokyo")

    start_time = parsed_date.start_of("day")
    end_time = parsed_date.end_of("day")

    all_results = (
        TaskResultHistoryDocument.find(
            {
                "username": current_user.username,
                "chip_id": chip_id,
                "name": task_name,
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
            task_result = Task(
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
            task_result = Task(name=task_name, default_view=False)
        results[qid] = task_result

    response = LatestTaskGroupedByChipResponse(task_name=task_name, result=results)
    return response_processor.process_task_response(response, task_name)


@router.get(
    "/chip/{chip_id}/task/coupling/{task_name}/latest",
    summary="Fetch the multiplexers",
    operation_id="fetchLatestCouplingTaskGroupedByChip",
    response_model=LatestTaskGroupedByChipResponse,
    response_model_exclude_none=True,
)
def fetch_latest_coupling_task_grouped_by_chip(
    chip_id: str, task_name: str, current_user: Annotated[User, Depends(get_current_active_user)]
) -> LatestTaskGroupedByChipResponse:
    """Fetch the multiplexers."""
    logger.debug(f"Fetching muxes for chip {chip_id}, user: {current_user.username}")

    # Get chip info
    chip = ChipDocument.find_one({"chip_id": chip_id, "username": current_user.username}).run()
    if chip is None:
        raise ValueError(f"Chip {chip_id} not found for user {current_user.username}")

    # Get qids
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
                "name": task_name,
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
            task_result = Task(
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
            task_result = Task(name=task_name, default_view=False)
        results[qid] = task_result

    response = LatestTaskGroupedByChipResponse(task_name=task_name, result=results)
    return response_processor.process_task_response(response, task_name)


class TimeSeriesProjection(BaseModel):
    """TimeSeriesProjection is a Pydantic model that represents the projection for time series data."""

    qid: str
    output_parameters: dict[str, Any]
    start_at: str


class TimeSeriesData(BaseModel):
    """TimeSeriesData is a Pydantic model that represents the time series data."""

    data: dict[str, list[OutputParameterModel]] = {}

    model_config = ConfigDict(arbitrary_types_allowed=True)


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
    start_at : str | None
        The start time in ISO format (optional, defaults to 7 days ago)
    end_at : str | None
        The end time in ISO format (optional, defaults to now)
    tag : str
        The tag to filter by
    parameter : str
        The parameter to fetch
    current_user : User
        The current user
    target_qid : str | None
        If provided, only return data for this specific qid

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
    "/chip/{chip_id}/parameter/{parameter}/qid/{qid}",
    summary="Fetch the timeseries task result by tag and parameter for a specific qid",
    response_model=TimeSeriesData,
    operation_id="fetchTimeseriesTaskResultByTagAndParameterAndQid",
)
def fetch_timeseries_task_result_by_tag_and_parameter_and_qid(
    chip_id: str,
    tag: str,
    parameter: str,
    qid: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    start_at: str,
    end_at: str,
) -> TimeSeriesData:
    """Fetch the timeseries task result by tag and parameter for a specific qid.

    Returns
    -------
        TimeSeriesData: Time series data for the specified qid.

    """
    logger.debug(f"Fetching timeseries task result for tag {tag}, parameter {parameter}, qid {qid}")
    return _fetch_timeseries_data(chip_id, tag, parameter, current_user, qid, start_at, end_at)


@router.get(
    "/chip/{chip_id}/parameter/{parameter}",
    summary="Fetch the timeseries task result by tag and parameter for all qids",
    response_model=TimeSeriesData,
    operation_id="fetchTimeseriesTaskResultByTagAndParameter",
)
def fetch_timeseries_task_result_by_tag_and_parameter(
    chip_id: str,
    tag: str,
    parameter: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    start_at: str,
    end_at: str,
) -> TimeSeriesData:
    """Fetch the timeseries task result by tag and parameter for all qids.

    Returns
    -------
        TimeSeriesData: Time series data for all qids.

    """
    logger.debug(f"Fetching timeseries task result for tag {tag}, parameter {parameter}")
    return _fetch_timeseries_data(chip_id, tag, parameter, current_user, start_at=start_at, end_at=end_at)
