"""MongoDB implementation of ExecutionHistoryRepository.

This module provides the concrete MongoDB implementation for execution
history persistence operations.
"""

import logging
from typing import Any

from bunnet import SortDirection

from qdash.dbmodel.execution_history import ExecutionHistoryDocument

logger = logging.getLogger(__name__)


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

    def list_by_chip(
        self,
        *,
        project_id: str,
        chip_id: str,
        skip: int = 0,
        limit: int = 20,
    ) -> list[ExecutionHistoryDocument]:
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
        list[ExecutionHistoryDocument]
            List of execution history documents

        """
        results: list[ExecutionHistoryDocument] = (
            ExecutionHistoryDocument.find(
                {"project_id": project_id, "chip_id": chip_id},
                sort=[("start_at", SortDirection.DESCENDING)],
            )
            .skip(skip)
            .limit(limit)
            .run()
        )
        return results

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
