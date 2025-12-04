"""Execution router for QDash API."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from pymongo import DESCENDING
from qdash.api.lib.auth import get_current_active_user
from qdash.api.schemas.auth import User
from qdash.api.schemas.error import Detail
from qdash.api.schemas.execution import (
    ExecutionLockStatusResponse,
    ExecutionResponseDetail,
    ExecutionResponseSummary,
    ListExecutionsResponse,
    Task,
)
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.execution_lock import ExecutionLockDocument
from starlette.exceptions import HTTPException

router = APIRouter()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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
    "/executions/figure",
    responses={404: {"model": Detail}},
    response_class=FileResponse,
    summary="Get a calibration figure by its path",
    operation_id="getFigureByPath",
)
def get_figure_by_path(path: str):
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
    # FileResponse を使うことで Content-Length が設定され、chunked encoding が不要になる
    return FileResponse(path, media_type="image/png")


@router.get(
    "/executions/lock-status",
    summary="Get the execution lock status",
    operation_id="getExecutionLockStatus",
    response_model=ExecutionLockStatusResponse,
)
def get_execution_lock_status() -> ExecutionLockStatusResponse:
    """Fetch the current status of the execution lock.

    The execution lock prevents concurrent calibration workflows from running
    simultaneously. This endpoint checks whether a lock is currently held.

    Returns
    -------
    ExecutionLockStatusResponse
        Response containing lock status (True if locked, False if available)

    """
    status = ExecutionLockDocument.get_lock_status()
    if status is None:
        return ExecutionLockStatusResponse(lock=False)
    return ExecutionLockStatusResponse(lock=status)


@router.get(
    "/executions",
    response_model=ListExecutionsResponse,
    summary="List executions",
    operation_id="listExecutions",
)
def list_executions(
    current_user: Annotated[User, Depends(get_current_active_user)],
    chip_id: Annotated[str, Query(description="Chip ID to filter executions")],
    skip: Annotated[int, Query(ge=0, description="Number of items to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Number of items to return")] = 20,
) -> ListExecutionsResponse:
    """List executions for a given chip with pagination.

    Parameters
    ----------
    current_user : User
        Current authenticated user
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
    logger.debug(f"Listing executions for chip {chip_id}, user: {current_user.username}, skip: {skip}, limit: {limit}")
    executions = (
        ExecutionHistoryDocument.find(
            {"chip_id": chip_id, "username": current_user.username}, sort=[("start_at", DESCENDING)]
        )
        .skip(skip)
        .limit(limit)
        .run()
    )
    return ListExecutionsResponse(
        executions=[
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
        ],
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
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> ExecutionResponseDetail:
    """Return the execution detail by its ID.

    Parameters
    ----------
    execution_id : str
        ID of the execution to fetch
    current_user : User
        Current authenticated user

    Returns
    -------
    ExecutionResponseDetail
        Detailed execution information

    """
    logger.debug(f"Fetching execution {execution_id}, user: {current_user.username}")
    execution = ExecutionHistoryDocument.find_one(
        {"execution_id": execution_id, "username": current_user.username}
    ).run()
    if execution is None:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")
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
