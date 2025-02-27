from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Header
from neodbmodel.chip import ChipDocument
from neodbmodel.execution_history import ExecutionHistoryDocument
from neodbmodel.initialize import initialize
from pydantic import BaseModel, Field, field_validator
from server.lib.current_user import get_current_user_id

if TYPE_CHECKING:
    from pydantic.validators import FieldValidationInfo
from pymongo import DESCENDING

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
    """Task is a Pydantic model that represents a task in the execution response.

    Attributes
    ----------
        task_id (str): The ID of the task.
        name (str): The name of the task.
        upstream_id (Optional[str]): The ID of the upstream task.
        status (str): The current status of the task.
        message (str): The message associated with the task.
        input_parameters (dict[str, Any]): The input parameters of the task.
        output_parameters (dict[str, Any]): The output parameters of the task.
        output_parameter_names (List[str]): The names of the output parameters.
        note (dict[str, Any]): The note associated with the task.
        figure_path (List[str]): The paths to the figures associated with the task.
        start_at (Optional[str]): The start time of the task.
        end_at (Optional[str]): The end time of the task.
        elapsed_time (Optional[str]): The total elapsed time of the task.
        task_type (str): The type of the task.

    """

    task_id: str
    qid: str = ""
    name: str
    upstream_id: str | None = ""
    status: str
    message: str
    input_parameters: dict[str, Any] = Field(default_factory=dict)
    output_parameters: dict[str, Any] = Field(default_factory=dict)
    output_parameter_names: list[str] = Field(default_factory=list)
    note: dict[str, Any] = Field(default_factory=dict)
    figure_path: list[str] = Field(default_factory=list)
    raw_data_path: list[str] = Field(default_factory=list)
    start_at: str | None = None
    end_at: str | None = None
    elapsed_time: str | None = None
    task_type: str

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


@router.get(
    "/chip", response_model=list[ChipResponse], summary="Fetch all chips", operation_id="listChips"
)
def list_chips(x_user_id: str | None = Header(None, description="User ID")) -> list[ChipResponse]:
    """Fetch all chips.

    Parameters
    ----------
    current_user_id : str
        Current user ID from authentication

    Returns
    -------
    list[ChipResponse]
        List of available chips

    """
    username = x_user_id or "default_user"
    logger.debug(f"Listing chips for user: {username}")
    initialize()
    chips = ChipDocument.find().run()
    return [ChipResponse(chip_id=chip.chip_id) for chip in chips]


@router.get(
    "/chip/{chip_id}", response_model=ChipResponse, summary="Fetch a chip", operation_id="fetchChip"
)
def fetch_chip(
    chip_id: str, x_user_id: str | None = Header(None, description="User ID")
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
    username = x_user_id or "default_user"
    logger.debug(f"Fetching chip {chip_id} for user: {username}")
    initialize()
    chip = ChipDocument.find_one({"chip_id": chip_id}).run()
    return ChipResponse(
        chip_id=chip.chip_id,
        size=chip.size,
        qubits=chip.qubits,
        couplings=chip.couplings,
    )


@router.get(
    "/chip/{chip_id}/execution",
    response_model=list[ExecutionResponseSummary],
    summary="Fetch executions",
    operation_id="listExecutionsByChipId",
)
def list_executions_by_chip_id(
    chip_id: str, x_user_id: str | None = Header(None, description="User ID")
) -> list[ExecutionResponseSummary]:
    """Fetch all executions for a given chip.

    Parameters
    ----------
    chip_id : str
        ID of the chip to fetch executions for
    current_user_id : str
        Current user ID from authentication

    Returns
    -------
    list[ExecutionResponseSummary]
        List of executions for the chip

    """
    username = x_user_id or "default_user"
    logger.debug(f"Listing executions for chip {chip_id}, user: {username}")
    initialize()
    executions = (
        ExecutionHistoryDocument.find({"chip_id": chip_id}, sort=[("start_at", DESCENDING)])
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
    chip_id: str, execution_id: str, x_user_id: str | None = Header(None, description="User ID")
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
    username = x_user_id or "default_user"
    logger.debug(f"Fetching execution {execution_id} for chip {chip_id}, user: {username}")
    initialize()
    execution = ExecutionHistoryDocument.find_one(
        {
            "execution_id": execution_id,
            "chip_id": chip_id,
        }
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
