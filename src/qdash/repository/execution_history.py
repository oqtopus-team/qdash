"""MongoDB implementation of ExecutionHistoryRepository.

This module provides the concrete MongoDB implementation for execution
history persistence operations.
"""

import logging
from datetime import datetime
from typing import Any

from bunnet import SortDirection
from pydantic import BaseModel

from qdash.dbmodel.execution_history import ExecutionHistoryDocument

logger = logging.getLogger(__name__)


class ExecutionStartRow(BaseModel):
    """Projection of an execution to the fields the activity chart counts."""

    start_at: datetime | None = None
    status: str


class MongoExecutionHistoryRepository:
    """MongoDB implementation of ExecutionHistoryRepository.

    This class encapsulates all MongoDB-specific logic for execution history
    data access.

    Example
    -------
        >>> repo = MongoExecutionHistoryRepository()
        >>> executions = repo.list_by_chip(
        ...     project_id="proj-1",
        ...     chip_id="64Qv3",
        ...     skip=0,
        ...     limit=20,
        ... )

    """

    @staticmethod
    def _chip_query(
        project_id: str,
        chip_id: str,
        started_between: tuple[datetime, datetime] | None,
    ) -> dict[str, Any]:
        """Filter for a chip's executions, optionally those started in ``[start, end)``."""
        query: dict[str, Any] = {"project_id": project_id, "chip_id": chip_id}
        if started_between is not None:
            start, end = started_between
            query["start_at"] = {"$gte": start, "$lt": end}
        return query

    def list_by_chip(
        self,
        *,
        project_id: str,
        chip_id: str,
        skip: int = 0,
        limit: int = 20,
        started_between: tuple[datetime, datetime] | None = None,
    ) -> list[ExecutionHistoryDocument]:
        """List a chip's executions, newest first, with pagination.

        ``started_between`` restricts the list to executions whose start time falls in
        the half-open window ``[start, end)``; executions without a start time are
        excluded by it.
        """
        results: list[ExecutionHistoryDocument] = (
            ExecutionHistoryDocument.find(
                self._chip_query(project_id, chip_id, started_between),
                sort=[("start_at", SortDirection.DESCENDING)],
            )
            .skip(skip)
            .limit(limit)
            .run()
        )
        return results

    def count_by_chip(
        self,
        *,
        project_id: str,
        chip_id: str,
        started_between: tuple[datetime, datetime] | None = None,
    ) -> int:
        """Count a chip's executions, with the same optional window as ``list_by_chip``."""
        return ExecutionHistoryDocument.find(
            self._chip_query(project_id, chip_id, started_between)
        ).count()

    def list_started_since(
        self,
        *,
        project_id: str,
        chip_id: str,
        since: datetime,
    ) -> list[ExecutionStartRow]:
        """Return start time and status of a chip's executions started at or after ``since``.

        Used for activity charts, so the window is bounded by date rather than by count,
        and only the two counted fields are read from MongoDB.
        """
        results: list[ExecutionStartRow] = (
            ExecutionHistoryDocument.find(
                {"project_id": project_id, "chip_id": chip_id, "start_at": {"$gte": since}},
                sort=[("start_at", SortDirection.ASCENDING)],
            )
            .project(ExecutionStartRow)
            .run()
        )
        return results

    def find_latest_by_project(self, project_id: str) -> ExecutionHistoryDocument | None:
        """Find the most recently started execution for a project."""
        results: list[ExecutionHistoryDocument] = (
            ExecutionHistoryDocument.find(
                {"project_id": project_id},
                sort=[("start_at", SortDirection.DESCENDING)],
            )
            .limit(1)
            .run()
        )
        return results[0] if results else None

    def find_by_id(
        self,
        project_id: str,
        execution_id: str,
    ) -> ExecutionHistoryDocument | None:
        """Find an execution by ID.

        Parameters
        ----------
        project_id : str
            The project identifier
        execution_id : str
            The execution identifier

        Returns
        -------
        ExecutionHistoryDocument | None
            The execution document if found, None otherwise

        """
        return ExecutionHistoryDocument.find_one(
            {"project_id": project_id, "execution_id": execution_id}
        ).run()

    def list_by_flow_run_id(
        self,
        project_id: str,
        flow_run_id: str,
    ) -> list[ExecutionHistoryDocument]:
        """Every execution of one Prefect flow run, oldest first.

        A pipeline run creates one execution per calibration step; they share
        ``note.flow_run_id``.
        """
        docs: list[ExecutionHistoryDocument] = (
            ExecutionHistoryDocument.find(
                {"project_id": project_id, "note.flow_run_id": flow_run_id}
            )
            .sort([("start_at", SortDirection.ASCENDING)])
            .run()
        )
        return docs

    def find_by_flow_run_id(
        self,
        project_id: str,
        flow_run_id: str,
    ) -> ExecutionHistoryDocument | None:
        """Find the QDash execution created by a Prefect flow run."""
        return ExecutionHistoryDocument.find_one(
            {"project_id": project_id, "note.flow_run_id": flow_run_id}
        ).run()
