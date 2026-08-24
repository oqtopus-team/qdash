"""Execution service for QDash API.

This module provides business logic for execution operations,
abstracting away the repository layer from the routers.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any, NamedTuple
from uuid import UUID

from bunnet import SortDirection
from fastapi import HTTPException
from prefect.client.orchestration import get_client
from prefect.client.schemas.filters import FlowRunFilter, FlowRunFilterId
from prefect.states import Cancelling

from qdash.api.schemas.execution import (
    CancelExecutionResponse,
    ExecutionLockStatusResponse,
    ExecutionResponseDetail,
    ExecutionResponseSummary,
    Task,
)
from qdash.common.utils.datetime import now, parse_elapsed_time
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.repository.execution_finalizer import finalize_executions_by_flow_run_id

if TYPE_CHECKING:
    from qdash.dbmodel.execution_history import ExecutionHistoryDocument
    from qdash.repository.execution_history import MongoExecutionHistoryRepository
    from qdash.repository.execution_lock import MongoExecutionLockRepository

logger = logging.getLogger(__name__)

_OPEN_EXECUTION_STATUSES = ("running", "scheduled")
_RECONCILE_TIMEOUT_SECONDS = 5.0


class _ReconcileOutcome(NamedTuple):
    """How an open execution should be closed when its flow run is already terminal."""

    status: str
    message: str
    close_tasks: bool


_TERMINAL_STATE_OUTCOMES: dict[str, _ReconcileOutcome] = {
    "FAILED": _ReconcileOutcome(
        "failed", "Flow run failed before the execution was closed", close_tasks=True
    ),
    "CRASHED": _ReconcileOutcome(
        "failed", "Flow run crashed before the execution was closed", close_tasks=True
    ),
    "CANCELLED": _ReconcileOutcome("cancelled", "Execution was cancelled", close_tasks=True),
}

_COMPLETED_STATE_OUTCOMES: dict[str, _ReconcileOutcome] = {
    "scheduled": _ReconcileOutcome(
        "completed",
        "Flow run completed without starting a calibration execution",
        close_tasks=False,
    ),
    "running": _ReconcileOutcome(
        "failed", "Flow run completed but the execution was never closed", close_tasks=True
    ),
}


def _reconcile_outcome(
    flow_run_state: str | None, execution_status: str
) -> _ReconcileOutcome | None:
    """Resolve how to close one execution, or None to leave it open.

    A completed flow run means different things depending on how far the
    execution got: a ``scheduled`` row was never picked up and is simply
    completed, while a ``running`` row should have been closed by the flow
    itself and is therefore failed. Every other terminal state closes the
    execution the same way regardless of how far it got.

    Parameters
    ----------
    flow_run_state : str | None
        The Prefect flow run state type, or None when Prefect did not
        report the run.
    execution_status : str
        The current status of the execution document.

    Returns
    -------
    _ReconcileOutcome | None
        The terminal status, message and task handling to apply, or None
        when the execution should be left untouched.

    """
    if flow_run_state == "COMPLETED":
        return _COMPLETED_STATE_OUTCOMES.get(execution_status)
    if flow_run_state is None:
        return None
    return _TERMINAL_STATE_OUTCOMES.get(flow_run_state)


class ExecutionService:
    """Service for execution-related operations.

    This class encapsulates the business logic for execution operations,
    using repository abstractions for data access.

    Parameters
    ----------
    execution_history_repository : MongoExecutionHistoryRepository
        Repository for execution history access
    execution_lock_repository : MongoExecutionLockRepository
        Repository for execution lock operations

    """

    def __init__(
        self,
        execution_history_repository: MongoExecutionHistoryRepository,
        execution_lock_repository: MongoExecutionLockRepository,
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
                message=execution.message,
                user_id=execution.user_id,
                username=execution.username,
                start_at=execution.start_at,
                end_at=execution.end_at,
                elapsed_time=parse_elapsed_time(execution.elapsed_time),
                tags=execution.tags,
                note=execution.note,
            )
            for execution in executions
        ]

    def count_executions(
        self,
        project_id: str,
        chip_id: str,
    ) -> int:
        """Count executions for a chip.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier

        Returns
        -------
        int
            Total number of executions for the chip

        """
        return self._history_repo.count_by_chip(
            project_id=project_id,
            chip_id=chip_id,
        )

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
            # Flow dispatch endpoints return a Prefect flow-run ID before the
            # worker has created its QDash execution. Accept that ID as an
            # alias once the worker stores it in execution.note.flow_run_id.
            execution = self._history_repo.find_by_flow_run_id(project_id, execution_id)
        if execution is None:
            return None

        self._reconcile_with_prefect([execution])

        # Fetch tasks directly from task_result_history collection
        tasks = self._fetch_tasks_for_execution(project_id, execution.execution_id)

        return ExecutionResponseDetail(
            name=f"{execution.name}-{execution.execution_id}",
            status=execution.status,
            message=execution.message,
            flow_name=execution.name,
            user_id=execution.user_id,
            username=execution.username,
            start_at=execution.start_at,
            end_at=execution.end_at,
            elapsed_time=parse_elapsed_time(execution.elapsed_time),
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
        latest = self._history_repo.find_latest_by_project(project_id)
        if latest is None:
            return ExecutionLockStatusResponse(lock=bool(status))
        return ExecutionLockStatusResponse(
            lock=bool(status),
            execution_id=latest.execution_id,
            chip_id=latest.chip_id,
            name=latest.name,
            status=latest.status,
        )

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

    def _reconcile_with_prefect(self, executions: list[ExecutionHistoryDocument]) -> None:
        """Close executions whose Prefect flow run has already finished.

        When the Prefect runner dies before an execution's own closing hooks
        run, the execution can be left ``running`` or ``scheduled`` in Mongo
        forever (issue #1111). This cross-checks any still-open execution
        against Prefect and finalizes it if the underlying flow run has
        already reached a terminal state, patching the passed-in documents
        in place so callers see the reconciled state without a second
        database round trip.

        Parameters
        ----------
        executions : list[ExecutionHistoryDocument]
            Execution documents to reconcile. Only documents whose status is
            "running" or "scheduled" and whose note contains a valid
            ``flow_run_id`` are considered; others are left untouched.

        """
        try:
            targets: dict[str, list[ExecutionHistoryDocument]] = {}
            for doc in executions:
                if doc.status not in _OPEN_EXECUTION_STATUSES:
                    continue
                flow_run_id = (doc.note or {}).get("flow_run_id")
                if not flow_run_id or not isinstance(flow_run_id, str):
                    continue
                try:
                    UUID(flow_run_id)
                except ValueError:
                    continue
                targets.setdefault(flow_run_id, []).append(doc)

            if not targets:
                return

            uuids = [UUID(flow_run_id) for flow_run_id in targets]
            with get_client(
                sync_client=True,
                httpx_settings={"timeout": _RECONCILE_TIMEOUT_SECONDS},
            ) as client:
                runs = client.read_flow_runs(
                    flow_run_filter=FlowRunFilter(id=FlowRunFilterId(any_=uuids)),
                    limit=len(uuids),
                )

            run_states = {
                str(run.id): (run.state.type.value.upper() if run.state else None) for run in runs
            }

            for flow_run_id, docs in targets.items():
                project_id = docs[0].project_id
                if not project_id:
                    continue

                state = run_states.get(flow_run_id)

                by_outcome: dict[_ReconcileOutcome, list[ExecutionHistoryDocument]] = {}
                for doc in docs:
                    outcome = _reconcile_outcome(state, doc.status)
                    if outcome is not None:
                        by_outcome.setdefault(outcome, []).append(doc)

                for outcome, outcome_docs in by_outcome.items():
                    self._close_reconciled_docs(
                        project_id=project_id,
                        flow_run_id=flow_run_id,
                        docs=outcome_docs,
                        status=outcome.status,
                        message=outcome.message,
                        close_tasks=outcome.close_tasks,
                    )
        except Exception:
            logger.warning("Prefect reconciliation failed", exc_info=True)

    @staticmethod
    def _close_reconciled_docs(
        *,
        project_id: str,
        flow_run_id: str,
        docs: list[ExecutionHistoryDocument],
        status: str,
        message: str,
        close_tasks: bool,
    ) -> None:
        """Finalize a group of same-flow-run-id executions and patch them in place.

        Parameters
        ----------
        project_id : str
            The project identifier.
        flow_run_id : str
            The Prefect flow run ID shared by the given documents.
        docs : list[ExecutionHistoryDocument]
            Execution documents to finalize.
        status : str
            Terminal status to set.
        message : str
            Message to record.
        close_tasks : bool
            Whether to also close non-terminal task_result_history rows.

        """
        end_time = now()
        for from_status in {doc.status for doc in docs}:
            finalize_executions_by_flow_run_id(
                project_id=project_id,
                flow_run_id=flow_run_id,
                status=status,
                message=message,
                from_statuses=(from_status,),
                close_tasks=close_tasks,
                context="prefect_reconcile",
                logger=logger,
            )
        for doc in docs:
            doc.status = status
            doc.end_at = end_time
            doc.message = message

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
                    user_id=doc.user_id,
                    username=doc.username,
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
