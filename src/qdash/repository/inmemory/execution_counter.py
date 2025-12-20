"""In-memory implementation of ExecutionCounterRepository for testing.

This module provides a mock implementation that stores data in memory,
useful for unit testing without requiring a MongoDB instance.
"""


class InMemoryExecutionCounterRepository:
    """In-memory implementation of ExecutionCounterRepository for testing.

    This implementation stores counters in a dictionary, making it suitable
    for unit tests that don't require a real database.

    Example
    -------
        >>> repo = InMemoryExecutionCounterRepository()
        >>> index1 = repo.get_next_index("20240101", "alice", "chip_1", "proj-1")
        >>> assert index1 == 0
        >>> index2 = repo.get_next_index("20240101", "alice", "chip_1", "proj-1")
        >>> assert index2 == 1

    """

    def __init__(self) -> None:
        """Initialize with empty storage."""
        self._counters: dict[str, int] = {}
        self._dates: dict[str, list[str]] = {}  # key: "{project_id}:{chip_id}"

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
        counter_key = f"{date}:{username}:{chip_id}:{project_id}"
        current = self._counters.get(counter_key, -1)
        next_index = current + 1
        self._counters[counter_key] = next_index

        # Track dates for chip
        dates_key = f"{project_id}:{chip_id}"
        if dates_key not in self._dates:
            self._dates[dates_key] = []
        if date not in self._dates[dates_key]:
            self._dates[dates_key].append(date)

        return next_index

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
        key = f"{project_id}:{chip_id}"
        return self._dates.get(key, [])

    def clear(self) -> None:
        """Clear all stored counters (useful for test setup/teardown)."""
        self._counters.clear()
        self._dates.clear()
