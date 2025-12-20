"""In-memory implementation of TaskResultHistoryRepository for testing.

This module provides a mock implementation that stores data in memory,
useful for unit testing without requiring a MongoDB instance.
"""

from dataclasses import dataclass
from typing import Any

from qdash.datamodel.execution import ExecutionModel
from qdash.datamodel.task import BaseTaskResultModel


@dataclass
class TaskResultHistoryEntry:
    """In-memory representation of a task result history entry."""

    task_id: str
    name: str
    status: str
    message: str | None
    input_parameters: dict[str, Any]
    output_parameters: dict[str, Any]
    output_parameter_names: list[str]
    note: dict[str, Any] | None
    figure_path: list[str]
    json_figure_path: list[str]
    raw_data_path: list[str]
    start_at: str | None
    end_at: str | None
    elapsed_time: str | None
    task_type: str | None
    project_id: str | None
    chip_id: str
    qid: str


class InMemoryTaskResultHistoryRepository:
    """In-memory implementation of TaskResultHistoryRepository for testing.

    This implementation stores task results in a list, making it suitable
    for unit tests that don't require a real database.

    Example
    -------
        >>> repo = InMemoryTaskResultHistoryRepository()
        >>> repo.save(task_result, execution_model)
        >>> results = repo.find_latest_by_chip_and_qids(
        ...     project_id="proj-1",
        ...     chip_id="chip_1",
        ...     qids=["0", "1"],
        ...     task_names=["CheckRabi"],
        ... )

    """

    def __init__(self) -> None:
        """Initialize with empty storage."""
        self._history: list[TaskResultHistoryEntry] = []

    def save(self, task: BaseTaskResultModel, execution_model: ExecutionModel) -> None:
        """Save a task result to the history.

        Parameters
        ----------
        task : BaseTaskResultModel
            The task result to save
        execution_model : ExecutionModel
            The parent execution context

        """
        entry = TaskResultHistoryEntry(
            task_id=task.task_id,
            name=task.name,
            status=task.status,
            message=task.message,
            input_parameters=task.input_parameters,
            output_parameters=task.output_parameters,
            output_parameter_names=task.output_parameter_names,
            note=task.note,
            figure_path=task.figure_path,
            json_figure_path=task.json_figure_path,
            raw_data_path=task.raw_data_path,
            start_at=task.start_at,
            end_at=task.end_at,
            elapsed_time=task.elapsed_time,
            task_type=task.task_type,
            project_id=execution_model.project_id,
            chip_id=execution_model.chip_id,
            qid=task.qid if hasattr(task, "qid") else "",
        )
        self._history.append(entry)

    def find_latest_by_chip_and_qids(
        self,
        *,
        project_id: str,
        chip_id: str,
        qids: list[str],
        task_names: list[str],
    ) -> list[TaskResultHistoryEntry]:
        """Find the latest task results for specified qubits and tasks.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier
        qids : list[str]
            List of qubit identifiers
        task_names : list[str]
            List of task names to filter

        Returns
        -------
        list[TaskResultHistoryEntry]
            List of task result entries, sorted by end_at descending

        """
        filtered = [
            entry
            for entry in self._history
            if (
                entry.project_id == project_id
                and entry.chip_id == chip_id
                and entry.qid in qids
                and entry.name in task_names
            )
        ]
        # Sort by end_at descending
        return sorted(
            filtered,
            key=lambda x: x.end_at or "",
            reverse=True,
        )

    def get_all(self) -> list[TaskResultHistoryEntry]:
        """Get all stored task results (test helper).

        Returns
        -------
        list[TaskResultHistoryEntry]
            All stored task results

        """
        return list(self._history)

    def clear(self) -> None:
        """Clear all stored history (useful for test setup/teardown)."""
        self._history.clear()
