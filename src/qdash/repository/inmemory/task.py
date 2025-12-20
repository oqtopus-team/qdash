"""In-memory implementation of TaskRepository for testing.

This module provides a mock implementation that stores task definitions in memory,
useful for unit testing without requiring a MongoDB instance.
"""


class InMemoryTaskRepository:
    """In-memory implementation of TaskRepository for testing.

    This implementation stores task definitions in a dictionary, making it
    suitable for unit tests that don't require a real database.

    Example
    -------
        >>> repo = InMemoryTaskRepository()
        >>> repo.add_tasks("alice", ["CheckFreq", "CheckRabi"])
        >>> names = repo.get_task_names("alice")
        >>> assert "CheckFreq" in names

    """

    def __init__(self) -> None:
        """Initialize with empty storage."""
        self._tasks: dict[str, list[str]] = {}

    def get_task_names(self, username: str) -> list[str]:
        """Get all task names available for a user.

        Parameters
        ----------
        username : str
            The username to look up tasks for

        Returns
        -------
        list[str]
            List of available task names

        """
        return self._tasks.get(username, [])

    def add_tasks(self, username: str, task_names: list[str]) -> None:
        """Add tasks for a user (test helper).

        Parameters
        ----------
        username : str
            The username
        task_names : list[str]
            List of task names to add

        """
        if username not in self._tasks:
            self._tasks[username] = []
        self._tasks[username].extend(task_names)

    def clear(self) -> None:
        """Clear all stored tasks (useful for test setup/teardown)."""
        self._tasks.clear()
