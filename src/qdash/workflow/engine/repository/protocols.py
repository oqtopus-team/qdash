"""Repository layer protocols for calibration workflows.

This module defines abstract interfaces (protocols) for data access operations
in calibration workflows.
"""

from typing import Any, Callable, Protocol, runtime_checkable

from qdash.datamodel.execution import ExecutionModel
from qdash.datamodel.task import BaseTaskResultModel, CalibDataModel


@runtime_checkable
class TaskResultHistoryRepository(Protocol):
    """Protocol for task result history persistence operations."""

    def save(self, task: BaseTaskResultModel, execution_model: ExecutionModel) -> None:
        """Save a task result to the history.

        Parameters
        ----------
        task : BaseTaskResultModel
            The task result to save
        execution_model : ExecutionModel
            The parent execution context

        """
        ...


@runtime_checkable
class ChipRepository(Protocol):
    """Protocol for chip data access operations."""

    def get_current_chip(self, username: str) -> dict[str, Any]:
        """Get the current chip data.

        Parameters
        ----------
        username : str
            The username to look up the chip

        Returns
        -------
        dict
            The chip data including qubit and coupling parameters

        """
        ...

    def update_chip_data(
        self,
        chip_id: str,
        calib_data: CalibDataModel,
        username: str,
    ) -> None:
        """Update chip calibration data.

        Parameters
        ----------
        chip_id : str
            The chip identifier
        calib_data : CalibDataModel
            The calibration data to merge
        username : str
            The user performing the update

        """
        ...


@runtime_checkable
class ChipHistoryRepository(Protocol):
    """Protocol for chip history recording operations."""

    def create_history(self, username: str) -> None:
        """Create a chip history snapshot from the current chip state.

        Parameters
        ----------
        username : str
            The username to look up the chip

        """
        ...


@runtime_checkable
class CalibDataSaver(Protocol):
    """Protocol for saving calibration artifacts (figures, raw data, JSON)."""

    def save_figures(
        self,
        figures: list[Any],
        task_name: str,
        task_type: str,
        qid: str,
        output_dir: str | None = None,
    ) -> tuple[list[str], list[str]]:
        """Save figures as PNG and JSON.

        Parameters
        ----------
        figures : list
            List of plotly figures to save
        task_name : str
            The name of the task
        task_type : str
            The type of task (qubit, coupling, global, system)
        qid : str
            The qubit identifier (empty for global/system tasks)

        Returns
        -------
        tuple[list[str], list[str]]
            Tuple of (png_paths, json_paths)

        """
        ...

    def save_raw_data(
        self,
        raw_data: list[Any],
        task_name: str,
        task_type: str,
        qid: str,
        output_dir: str | None = None,
    ) -> list[str]:
        """Save raw data as CSV files.

        Parameters
        ----------
        raw_data : list
            List of numpy arrays to save
        task_name : str
            The name of the task
        task_type : str
            The type of task
        qid : str
            The qubit identifier

        Returns
        -------
        list[str]
            List of saved file paths

        """
        ...

    def save_task_json(self, task_id: str, task_data: dict[str, Any]) -> str:
        """Save task data as JSON.

        Parameters
        ----------
        task_id : str
            The task identifier
        task_data : dict
            The task data to save

        Returns
        -------
        str
            Path to the saved JSON file

        """
        ...


@runtime_checkable
class ExecutionRepository(Protocol):
    """Protocol for execution state persistence operations."""

    def save(self, execution: ExecutionModel) -> None:
        """Save execution state to the database.

        Parameters
        ----------
        execution : ExecutionModel
            The execution model to save

        """
        ...

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
        ...

    def update_with_optimistic_lock(
        self,
        execution_id: str,
        update_func: Callable[[ExecutionModel], None],
    ) -> ExecutionModel:
        """Update execution with optimistic locking.

        This method reads the current state, applies the update function,
        and saves with version checking to handle concurrent modifications.

        Parameters
        ----------
        execution_id : str
            The execution identifier
        update_func : callable
            Function that takes ExecutionModel and modifies it in place

        Returns
        -------
        ExecutionModel
            The updated execution model

        """
        ...
