"""Execution service for QDash API.

This module provides business logic for execution operations,
abstracting away the repository layer from the routers.
"""

import logging
from typing import Any

from qdash.api.schemas.execution import (
    ExecutionLockStatusResponse,
    ExecutionResponseDetail,
    ExecutionResponseSummary,
    Task,
)

logger = logging.getLogger(__name__)


class ExecutionService:
    """Service for execution-related operations.

    This class encapsulates the business logic for execution operations,
    using repository abstractions for data access.

    Parameters
    ----------
    execution_history_repository : Any
        Repository for execution history access
    execution_lock_repository : Any
        Repository for execution lock operations

    """

    def __init__(
        self,
        execution_history_repository: Any,
        execution_lock_repository: Any,
    ) -> None:
        """Initialize the service with repositories."""
        self._history_repo = execution_history_repository
        self._lock_repo = execution_lock_repository

    def list_executions(
        self,
        project_id: str,
        chip_id: str,
        skip: int = 0,
        limit: int = 20,
    ) -> list[ExecutionResponseSummary]:
        """List executions for a chip with pagination.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier
        skip : int
            Number of items to skip
        limit : int
            Number of items to return

        Returns
        -------
        list[ExecutionResponseSummary]
            List of execution summaries

        """
        executions = self._history_repo.list_by_chip(
            project_id=project_id,
            chip_id=chip_id,
            skip=skip,
            limit=limit,
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

    def get_execution(
        self,
        project_id: str,
        execution_id: str,
    ) -> ExecutionResponseDetail | None:
        """Get execution detail by ID.

        Parameters
        ----------
        project_id : str
            The project identifier
        execution_id : str
            The execution identifier

        Returns
        -------
        ExecutionResponseDetail | None
            The execution detail or None if not found

        """
        execution = self._history_repo.find_by_id(project_id, execution_id)
        if execution is None:
            return None

        flat_tasks = self._flatten_tasks(execution.task_results)
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

    def get_lock_status(self, project_id: str) -> ExecutionLockStatusResponse:
        """Get the execution lock status.

        Parameters
        ----------
        project_id : str
            The project identifier

        Returns
        -------
        ExecutionLockStatusResponse
            The lock status response

        """
        status = self._lock_repo.get_lock_status(project_id)
        if status is None:
            return ExecutionLockStatusResponse(lock=False)
        return ExecutionLockStatusResponse(lock=status)

    def _flatten_tasks(self, task_results: dict[str, Any]) -> list[dict[str, Any]]:
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
        grouped_tasks: dict[str, list[dict[str, Any]]] = {}

        for result in task_results.values():
            if not isinstance(result, dict):
                result = result.model_dump()  # noqa: PLW2901

            # グローバルタスクの処理
            if "global_tasks" in result:
                if "global" not in grouped_tasks:
                    grouped_tasks["global"] = []
                grouped_tasks["global"].extend(result["global_tasks"])

            if "system_tasks" in result:
                if "system" not in grouped_tasks:
                    grouped_tasks["system"] = []
                grouped_tasks["system"].extend(result["system_tasks"])

            # キュービットタスクの処理
            if "qubit_tasks" in result:
                for qid, tasks in result["qubit_tasks"].items():
                    if qid not in grouped_tasks:
                        grouped_tasks[qid] = []
                    for task in tasks:
                        if "qid" not in task or not task["qid"]:
                            task["qid"] = qid
                        grouped_tasks[qid].append(task)

            # カップリングタスクの処理
            if "coupling_tasks" in result:
                for tasks in result["coupling_tasks"].values():
                    if "coupling" not in grouped_tasks:
                        grouped_tasks["coupling"] = []
                    grouped_tasks["coupling"].extend(tasks)

        # 各グループ内でstart_atによるソート
        for group_tasks in grouped_tasks.values():
            group_tasks.sort(key=lambda x: x.get("start_at", "") or "9999-12-31T23:59:59")

        # グループ自体をstart_atの早い順にソート
        def get_group_completion_time(group: list[dict[str, Any]]) -> str:
            completed_tasks = [t for t in group if t.get("start_at")]
            if not completed_tasks:
                return "9999-12-31T23:59:59"
            return max(str(t["start_at"]) for t in completed_tasks)

        sorted_groups = sorted(grouped_tasks.items(), key=lambda x: get_group_completion_time(x[1]))

        # ソートされたグループを1つのリストに結合
        flat_tasks = []
        for _, tasks in sorted_groups:
            flat_tasks.extend(tasks)

        return flat_tasks
