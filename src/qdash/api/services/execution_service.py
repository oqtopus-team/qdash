"""Execution service for QDash API.

This module provides business logic for execution operations,
abstracting away the repository layer from the routers.
"""

import logging
from datetime import timedelta
from typing import Any

from bunnet import SortDirection
from qdash.api.schemas.execution import (
    ExecutionLockStatusResponse,
    ExecutionResponseDetail,
    ExecutionResponseSummary,
    Task,
)
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

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

        # Fetch tasks directly from task_result_history collection
        tasks = self._fetch_tasks_for_execution(project_id, execution_id)

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

    def _fetch_tasks_for_execution(
        self,
        project_id: str,
        execution_id: str,
    ) -> list[Task]:
        """Fetch tasks for an execution from task_result_history collection.

        Parameters
        ----------
        project_id : str
            The project identifier
        execution_id : str
            The execution identifier

        Returns
        -------
        list[Task]
            List of tasks, sorted by start_at

        """
        # Query task_result_history collection directly
        task_docs: list[TaskResultHistoryDocument] = (
            TaskResultHistoryDocument.find(
                {
                    "project_id": project_id,
                    "execution_id": execution_id,
                }
            )
            .sort([("start_at", SortDirection.ASCENDING)])
            .run()
        )

        # Convert documents to Task schema objects
        tasks = []
        for doc in task_docs:
            # Convert elapsed_time from seconds (float) to timedelta
            elapsed = timedelta(seconds=doc.elapsed_time) if doc.elapsed_time is not None else None
            tasks.append(
                Task(
                    task_id=doc.task_id,
                    qid=doc.qid,
                    name=doc.name,
                    upstream_id=doc.upstream_id,
                    status=doc.status,
                    message=doc.message,
                    input_parameters=doc.input_parameters,
                    output_parameters=doc.output_parameters,
                    output_parameter_names=doc.output_parameter_names,
                    note=doc.note,
                    figure_path=doc.figure_path,
                    json_figure_path=doc.json_figure_path,
                    raw_data_path=doc.raw_data_path,
                    start_at=doc.start_at,
                    end_at=doc.end_at,
                    elapsed_time=elapsed,
                    task_type=doc.task_type,
                )
            )

        return tasks
