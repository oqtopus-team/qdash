"""Finalize executions and their tasks by Prefect flow_run_id."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from qdash.common.utils.datetime import now
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.execution_lock import ExecutionLockDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

if TYPE_CHECKING:
    from collections.abc import Sequence

DEFAULT_OPEN_STATUSES: tuple[str, ...] = ("running", "scheduled")
OPEN_TASK_STATUSES: tuple[str, ...] = ("running", "scheduled", "pending")


def finalize_executions_by_flow_run_id(
    *,
    project_id: str,
    flow_run_id: str,
    status: str,
    message: str,
    from_statuses: Sequence[str] = DEFAULT_OPEN_STATUSES,
    close_tasks: bool = True,
    release_lock: bool = True,
    context: str = "finalize",
    logger: logging.Logger | None = None,
) -> list[str]:
    """Find executions with the given flow_run_id in note and close them.

    Args:
        project_id: Project ID the executions belong to
        flow_run_id: Prefect flow run ID stored in ``note.flow_run_id``
        status: Terminal status to set on matched executions (and tasks, if closed)
        message: Message to record on matched executions (and tasks, if closed)
        from_statuses: Execution statuses eligible to be closed
        close_tasks: Whether to also close open TaskResultHistoryDocument rows
        release_lock: Whether to release the project's ExecutionLockDocument
        context: Label used in log messages to identify the caller
        logger: Logger to use. Defaults to a module-level logger.

    Returns:
        List of execution_ids that were closed.

    """
    if logger is None:
        logger = logging.getLogger(__name__)

    end_time = now()

    executions = ExecutionHistoryDocument.find(
        {
            "project_id": project_id,
            "note.flow_run_id": flow_run_id,
            "status": {"$in": list(from_statuses)},
        }
    ).run()

    if not executions:
        logger.info(
            "%s: no matching executions for flow_run_id=%s",
            context,
            flow_run_id,
        )
        return []

    closed_execution_ids: list[str] = []

    for execution in executions:
        execution_id = execution.execution_id
        logger.info(
            "%s: closing execution %s as %s (flow_run_id=%s)",
            context,
            execution_id,
            status,
            flow_run_id,
        )

        ExecutionHistoryDocument.find(
            {"project_id": project_id, "execution_id": execution_id}
        ).update_many({"$set": {"status": status, "end_at": end_time, "message": message}}).run()

        if close_tasks:
            result = (
                TaskResultHistoryDocument.find(
                    {
                        "project_id": project_id,
                        "execution_id": execution_id,
                        "status": {"$in": list(OPEN_TASK_STATUSES)},
                    }
                )
                .update_many(
                    {
                        "$set": {
                            "status": status,
                            "message": message,
                            "end_at": end_time,
                        }
                    }
                )
                .run()
            )

            task_count = result.modified_count if result else 0
            logger.info(
                "%s: execution %s closed, %d task(s) updated",
                context,
                execution_id,
                task_count,
            )

        closed_execution_ids.append(execution_id)

    if release_lock:
        try:
            lock_doc = ExecutionLockDocument.find_one({"project_id": project_id}).run()
            if lock_doc and lock_doc.locked:
                lock_doc.locked = False
                lock_doc.save()
                logger.info("Released execution lock for project %s", project_id)
        except Exception:
            logger.warning("Failed to release execution lock", exc_info=True)

    return closed_execution_ids
