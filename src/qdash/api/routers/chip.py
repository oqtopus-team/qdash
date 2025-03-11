from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated, Any

import pendulum
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator
from qdash.api.lib.auth import get_current_active_user, get_optional_current_user
from qdash.api.lib.current_user import get_current_user_id
from qdash.api.schemas.auth import User
from qdash.datamodel.task import OutputParameterModel
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.task import TaskDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

if TYPE_CHECKING:
    from pydantic.validators import FieldValidationInfo
from pymongo import ASCENDING, DESCENDING

router = APIRouter()

# ロガーの設定
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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
    raw_data_path: list[str] | None = None
    start_at: str | None = None
    end_at: str | None = None
    elapsed_time: str | None = None
    task_type: str | None = None

    @field_validator("name", mode="before")
    def modify_name(cls, v: str, info: FieldValidationInfo) -> str:  # noqa: N805
        data = info.data
        qid = data.get("qid")
        if qid:
            return f"{qid}-{v}"
        return v


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


@router.get(
    "/chip", response_model=list[ChipResponse], summary="Fetch all chips", operation_id="listChips"
)
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


@router.get(
    "/chip/{chip_id}", response_model=ChipResponse, summary="Fetch a chip", operation_id="fetchChip"
)
def fetch_chip(
    chip_id: str, current_user: Annotated[User, Depends(get_current_active_user)]
) -> ChipResponse:
    """Fetch a chip by its ID.

    Parameters
    ----------
    chip_id : str
        ID of the chip to fetch
    current_user_id : str
        Current user ID from authentication

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
        Flattened list of tasks

    """
    flat_tasks = []
    logger.debug("Flattening task_results: %s", task_results)

    for key, result in task_results.items():
        if not isinstance(result, dict):
            result = result.model_dump()  # noqa: PLW2901
        logger.debug("Processing key: %s, result: %s", key, result)

        if "global_tasks" in result:
            logger.debug("Found %d global_tasks in %s", len(result["global_tasks"]), key)
            flat_tasks.extend(result["global_tasks"])

        if "qubit_tasks" in result:
            for qid, tasks in result["qubit_tasks"].items():
                logger.debug("Found %d qubit_tasks under qid %s", len(tasks), qid)
                for task in tasks:
                    if "qid" not in task or not task["qid"]:
                        task["qid"] = qid
                    flat_tasks.append(task)

        if "coupling_tasks" in result:
            for sub_key, tasks in result["coupling_tasks"].items():
                logger.debug("Found %d coupling_tasks under key %s", len(tasks), sub_key)
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
    current_user_id : str
        Current user ID from authentication

    Returns
    -------
    ExecutionResponseDetail
        Detailed execution information

    """
    logger.debug(
        f"Fetching execution {execution_id} for chip {chip_id}, user: {current_user.username}"
    )
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


def _build_mux_detail(mux_id: int, tasks: list, current_user: User) -> MuxDetailResponse:
    qids = [str(mux_id * 4 + i) for i in range(4)]
    detail: dict[str, dict[str, Task]] = {}
    for qid in qids:
        detail[qid] = {}  # qidごとの辞書を初期化
        for task in tasks:
            logger.debug("Task: %s", task)
            result = TaskResultHistoryDocument.find_one(
                {"name": task.name, "username": current_user.username, "qid": qid},
                sort=[("end_at", DESCENDING)],
            ).run()
            if result is None:
                task_result = Task(
                    name=task.name,
                )
                detail[qid][task.name] = task_result
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
    tasks = TaskDocument.find({"username": current_user.username}).run()
    logger.debug("Tasks: %s", tasks)
    return _build_mux_detail(mux_id, tasks, current_user)


@router.get(
    "/chip/{chip_id}/mux",
    response_model=ListMuxResponse,
    summary="Fetch the multiplexers",
    operation_id="listMuxes",
    response_model_exclude_none=True,
)
def list_muxes(
    chip_id: str, current_user: Annotated[User, Depends(get_current_active_user)]
) -> ListMuxResponse:
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
    logger.debug(f"Fetching muxes for chip {chip_id}, user: {current_user.username}")
    tasks = TaskDocument.find({"username": current_user.username}).run()
    logger.debug("Tasks: %s", tasks)
    muxes: dict[int, MuxDetailResponse] = {}
    chip = ChipDocument.find_one({"chip_id": chip_id, "username": current_user.username}).run()
    if chip is None:
        raise ValueError(f"Chip {chip_id} not found for user {current_user.username}")
    mux_num = int(chip.size // 4)
    for mux_id in range(mux_num):
        muxes[mux_id] = _build_mux_detail(mux_id, tasks, current_user)
    return ListMuxResponse(muxes=muxes)


class LatestTaskGroupedByChipResponse(BaseModel):
    """ChipTaskResponse is a Pydantic model that represents the response for fetching the tasks of a chip."""

    task_name: str
    result: dict[str, Task]


@router.get(
    "/chip/{chip_id}/task/{task_name}",
    summary="Fetch the multiplexers",
    operation_id="fetchLatestTaskGroupedByChip",
    response_model=LatestTaskGroupedByChipResponse,
    response_model_exclude_none=True,
)
def fetch_latest_task_grouped_by_chip(
    chip_id: str, task_name: str, current_user: Annotated[User, Depends(get_current_active_user)]
) -> LatestTaskGroupedByChipResponse:
    """Fetch the multiplexers."""
    logger.debug(f"Fetching muxes for chip {chip_id}, user: {current_user.username}")
    chip = ChipDocument.find_one({"chip_id": chip_id, "username": current_user.username}).run()
    if chip is None:
        raise ValueError(f"Chip {chip_id} not found for user {current_user.username}")
    qids = [str(qid) for qid in range(chip.size)]
    results = {}
    for qid in qids:
        result = TaskResultHistoryDocument.find_one(
            {"name": task_name, "username": current_user.username, "qid": qid},
            sort=[("end_at", DESCENDING)],
        ).run()
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
                raw_data_path=result.raw_data_path,
                start_at=result.start_at,
                end_at=result.end_at,
                elapsed_time=result.elapsed_time,
                task_type=result.task_type,
            )
        else:
            task_result = Task(name=task_name)
        results[qid] = task_result
    return LatestTaskGroupedByChipResponse(task_name=task_name, result=results)


class TimeSeriesProjection(BaseModel):
    """TimeSeriesProjection is a Pydantic model that represents the projection for time series data."""

    qid: str
    output_parameters: dict[str, Any]
    start_at: str

    class Settings:
        projection = {
            "qid": 1,
            "output_parameters": 1,
            "start_at": 1,
            "_id": 0,
        }


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

        timeseries_by_qid[qid].append(task_result.output_parameters[parameter])

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
    return _fetch_timeseries_data(
        chip_id, tag, parameter, current_user, start_at=start_at, end_at=end_at
    )
