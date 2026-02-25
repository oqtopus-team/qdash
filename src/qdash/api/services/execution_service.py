"""Execution service for QDash API.

This module provides business logic for execution operations,
abstracting away the repository layer from the routers.
"""

import logging
from datetime import timedelta
from typing import Any
from uuid import UUID

from bunnet import SortDirection
from fastapi import HTTPException
from prefect.client.orchestration import get_client
from prefect.states import Cancelling
from qdash.api.schemas.execution import (
    CancelExecutionResponse,
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
            flow_name=execution.name,
            start_at=execution.start_at,
            end_at=execution.end_at,
            elapsed_time=execution.elapsed_time,
            task=tasks,
            note=execution.note,
            tags=execution.tags,
            chip_id=execution.chip_id,
        )

    def get_execution_metadata(
        self,
        project_id: str,
        execution_id: str,
    ) -> dict[str, Any] | None:
        """Get raw execution metadata fields for re-execution.

        Parameters
        ----------
        project_id : str
            The project identifier
        execution_id : str
            The execution identifier

        Returns
        -------
        dict[str, Any] | None
            Dictionary with chip_id, name, tags, username, or None if not found

        """
        execution = self._history_repo.find_by_id(project_id, execution_id)
        if execution is None:
            return None
        return {
            "chip_id": execution.chip_id,
            "name": execution.name,
            "tags": execution.tags,
            "username": execution.username,
        }

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

    async def cancel_execution(
        self,
        flow_run_id: str,
        project_id: str,
    ) -> CancelExecutionResponse:
        """Cancel a running or scheduled flow run via Prefect.

        Parameters
        ----------
        flow_run_id : str
            The Prefect flow run UUID
        project_id : str
            The project identifier (used to verify ownership)

        Returns
        -------
        CancelExecutionResponse
            The cancellation result

        """
        try:
            parsed_flow_run_id = UUID(flow_run_id)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid flow run ID format: {flow_run_id}. Must be a valid UUID.",
            )

        try:
            async with get_client() as client:
                flow_run = await client.read_flow_run(parsed_flow_run_id)

                # Verify the flow run belongs to the requesting project
                run_project_id = (flow_run.parameters or {}).get("project_id")
                if run_project_id and run_project_id != project_id:
                    raise HTTPException(
                        status_code=403,
                        detail="You do not have permission to cancel this execution.",
                    )

                cancellable_states = {"SCHEDULED", "PENDING", "RUNNING", "PAUSED"}
                current_state = flow_run.state.type.value.upper() if flow_run.state else "UNKNOWN"

                if current_state not in cancellable_states:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"Execution cannot be cancelled: current state is '{current_state}'. "
                            f"Only executions in {', '.join(sorted(cancellable_states))} state can be cancelled."
                        ),
                    )

                await client.set_flow_run_state(
                    flow_run_id=parsed_flow_run_id,
                    state=Cancelling(),
                    force=True,
                )

                logger.info(
                    f"Cancellation requested for flow run {flow_run_id} "
                    f"(was in state: {current_state})"
                )

                return CancelExecutionResponse(
                    execution_id=flow_run_id,
                    status="cancelling",
                    message=f"Cancellation requested for flow run {flow_run_id}",
                )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to cancel flow run {flow_run_id}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to cancel execution: {e}",
            )

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
            # Convert elapsed_time from seconds (float) to timedelta with validation
            elapsed = None
            if doc.elapsed_time is not None:
                try:
                    if isinstance(doc.elapsed_time, (int, float)) and doc.elapsed_time >= 0:
                        elapsed = timedelta(seconds=doc.elapsed_time)
                except (ValueError, OverflowError):
                    pass  # Keep elapsed as None for invalid values
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
                    run_parameters=doc.run_parameters,
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
