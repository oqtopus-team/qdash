"""MongoDB implementation of ExecutionCounterRepository.

This module provides the concrete MongoDB implementation for execution
counter operations.
"""

import logging

from qdash.dbmodel.execution_counter import ExecutionCounterDocument

logger = logging.getLogger(__name__)


class MongoExecutionCounterRepository:
    """MongoDB implementation of ExecutionCounterRepository.

    This class provides atomic counter generation for execution IDs,
    scoped by date, username, chip_id, and project_id.

    Example
    -------
        >>> repo = MongoExecutionCounterRepository()
        >>> index = repo.get_next_index(
        ...     date="20240115",
        ...     username="alice",
        ...     chip_id="64Qv3",
        ...     project_id="proj-1"
        ... )
        >>> print(index)  # 0, 1, 2, ...

    """

    def get_next_index(
        self,
        date: str,
        username: str,
        chip_id: str,
        project_id: str | None,
    ) -> int:
        """Get the next execution index atomically.

        Parameters
        ----------
        date : str
            The date string (e.g., "20240115")
        username : str
            The username
        chip_id : str
            The chip identifier
        project_id : str | None
            The project identifier

        Returns
        -------
        int
            The next index (0 on first call, then 1, 2, 3...)

        """
        result: int = ExecutionCounterDocument.get_next_index(
            date=date,
            username=username,
            chip_id=chip_id,
            project_id=project_id,
        )
        return result

    def get_dates_for_chip(
        self,
        project_id: str,
        chip_id: str,
    ) -> list[str]:
        """Get all dates with execution records for a chip.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier

        Returns
        -------
        list[str]
            List of date strings (e.g., ["20240115", "20240116"])

        """
        counter_list = ExecutionCounterDocument.find(
            {"project_id": project_id, "chip_id": chip_id}
        ).run()
        return [counter.date for counter in counter_list]
