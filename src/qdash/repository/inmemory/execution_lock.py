"""In-memory implementation of ExecutionLockRepository for testing.

This module provides a mock implementation that stores lock states in memory,
useful for unit testing without requiring a MongoDB instance.
"""

from qdash.common.execution_resources import ExecutionResourceScope


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
        self._claims: dict[str, dict[str | None, list[ExecutionResourceScope]]] = {}

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

    def try_lock(
        self,
        project_id: str,
        execution_id: str | None = None,
        chip_id: str = "",
        resources: tuple[str, ...] = (),
        exclusive: bool = True,
    ) -> bool:
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
        claims = self._claims.setdefault(project_id, {})
        scope = ExecutionResourceScope(chip_id=chip_id, resources=resources, exclusive=exclusive)
        for owner, held_scopes in claims.items():
            if execution_id is not None and owner == execution_id:
                continue
            for held in held_scopes:
                same_chip = not scope.chip_id or not held.chip_id or scope.chip_id == held.chip_id
                if same_chip and (
                    scope.exclusive
                    or held.exclusive
                    or bool(set(scope.resources).intersection(held.resources))
                ):
                    return False
        if self._locks.get(project_id, False) and not claims:
            return execution_id is not None and self._owners.get(project_id) == execution_id
        owned = claims.setdefault(execution_id, [])
        if scope not in owned:
            owned.append(scope)
        self._locks[project_id] = True
        self._owners[project_id] = execution_id
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
        self._claims.pop(project_id, None)
        self._locks[project_id] = True
        self._owners[project_id] = execution_id

    def unlock(self, project_id: str, execution_id: str | None = None) -> None:
        """Release the execution lock.

        Parameters
        ----------
        project_id : str
            The project identifier

        """
        if execution_id is None:
            self._claims.pop(project_id, None)
        else:
            if not self._claims.get(project_id) and self._owners.get(project_id) != execution_id:
                return
            self._claims.get(project_id, {}).pop(execution_id, None)
        remaining = self._claims.get(project_id, {})
        self._locks[project_id] = bool(remaining)
        self._owners[project_id] = next(iter(remaining), None)

    def clear(self) -> None:
        """Clear all locks (useful for test setup/teardown)."""
        self._locks.clear()
        self._owners.clear()
        self._claims.clear()
