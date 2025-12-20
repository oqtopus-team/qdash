"""In-memory implementation of ExecutionRepository for testing.

This module provides a mock implementation that stores data in memory,
useful for unit testing without requiring a MongoDB instance.
"""

from collections.abc import Callable

from qdash.datamodel.execution import ExecutionModel


class InMemoryExecutionRepository:
    """In-memory implementation of ExecutionRepository for testing.

    This implementation stores executions in a dictionary, making it
    suitable for unit tests that don't require a real database.

    Example
    -------
        >>> repo = InMemoryExecutionRepository()
        >>> model = ExecutionModel(execution_id="exec-001", ...)
        >>> repo.save(model)
        >>> found = repo.find_by_id("exec-001")
        >>> assert found.execution_id == "exec-001"

    """

    def __init__(self) -> None:
        """Initialize with empty storage."""
        self._executions: dict[str, ExecutionModel] = {}

    def save(self, execution: ExecutionModel) -> None:
        """Save execution state to in-memory storage.

        Parameters
        ----------
        execution : ExecutionModel
            The execution model to save

        """
        self._executions[execution.execution_id] = execution

    def find_by_id(self, execution_id: str) -> ExecutionModel | None:
        """Find execution by ID.

        Parameters
        ----------
        execution_id : str
            The execution identifier

        Returns
        -------
        ExecutionModel | None
            The execution model if found, None otherwise

        """
        return self._executions.get(execution_id)

    def update_with_optimistic_lock(
        self,
        execution_id: str,
        update_func: Callable[[ExecutionModel], None],
        initial_model: ExecutionModel | None = None,
    ) -> ExecutionModel:
        """Update execution with optimistic locking simulation.

        In-memory implementation doesn't need real locking but maintains
        the same interface for testing.

        Parameters
        ----------
        execution_id : str
            The execution identifier
        update_func : callable
            Function that takes ExecutionModel and modifies it in place
        initial_model : ExecutionModel | None
            Initial model to use if document doesn't exist

        Returns
        -------
        ExecutionModel
            The updated execution model

        Raises
        ------
        ValueError
            If execution not found and no initial model provided

        """
        model = self._executions.get(execution_id)
        if model is None:
            if initial_model is not None:
                model = initial_model
                self._executions[execution_id] = model
            else:
                raise ValueError(f"Execution {execution_id} not found")

        update_func(model)
        return model

    def clear(self) -> None:
        """Clear all stored executions (useful for test setup/teardown)."""
        self._executions.clear()
