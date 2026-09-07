"""In-memory implementation of ExecutionLockRepository for testing.

This module provides a mock implementation that stores lock states in memory,
useful for unit testing without requiring a MongoDB instance.
"""


class InMemoryExecutionLockRepository:
    """In-memory implementation of ExecutionLockRepository for testing.

    This implementation stores lock states in a dictionary, making it
    suitable for unit tests that don't require a real database.

    Example
    -------
        >>> repo = InMemoryExecutionLockRepository()
        >>> assert not repo.is_locked("proj-1")
        >>> repo.lock("proj-1")
        >>> assert repo.is_locked("proj-1")
        >>> repo.unlock("proj-1")
        >>> assert not repo.is_locked("proj-1")

    """

    def __init__(self) -> None:
        """Initialize with empty storage."""
        self._locks: dict[str, bool] = {}
        self._owners: dict[str, str | None] = {}

    def is_locked(self, project_id: str) -> bool:
        """Check if the project is currently locked.

        Parameters
        ----------
        project_id : str
            The project identifier

        Returns
        -------
        bool
            True if locked, False otherwise

        """
        return self._locks.get(project_id, False)

    def try_lock(self, project_id: str, execution_id: str | None = None) -> bool:
        """Atomically acquire the execution lock, unless another execution holds it.

        Parameters
        ----------
        project_id : str
            The project identifier
        execution_id : str | None
            The execution that will own the lock

        Returns
        -------
        bool
            True when the lock was acquired or already owned, False when held

        """
        if self._locks.get(project_id, False) and (
            execution_id is None or self._owners.get(project_id) != execution_id
        ):
            return False
        self.lock(project_id, execution_id)
        return True

    def lock(self, project_id: str, execution_id: str | None = None) -> None:
        """Acquire the execution lock.

        Parameters
        ----------
        project_id : str
            The project identifier
        execution_id : str | None
            The execution that owns the lock, if known

        """
        self._locks[project_id] = True
        self._owners[project_id] = execution_id

    def unlock(self, project_id: str) -> None:
        """Release the execution lock.

        Parameters
        ----------
        project_id : str
            The project identifier

        """
        self._locks[project_id] = False
        self._owners[project_id] = None

    def clear(self) -> None:
        """Clear all locks (useful for test setup/teardown)."""
        self._locks.clear()
        self._owners.clear()
