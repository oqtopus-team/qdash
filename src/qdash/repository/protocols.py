"""Repository layer protocols for QDash.

This module defines abstract interfaces (protocols) for data access operations
used by both API and workflow components.

The protocols follow the Repository pattern, providing:
- Abstraction over data storage (MongoDB, in-memory, etc.)
- Testability through dependency injection
- Clear separation between domain logic and data access
"""

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from qdash.datamodel.calibration_note import CalibrationNoteModel
from qdash.datamodel.chip import ChipModel
from qdash.datamodel.coupling import CouplingModel
from qdash.datamodel.execution import ExecutionModel
from qdash.datamodel.qubit import QubitModel
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

    def find_latest_by_chip_and_qids(
        self,
        *,
        project_id: str,
        chip_id: str,
        qids: list[str],
        task_names: list[str],
    ) -> list[Any]:
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
        list[Any]
            List of task result documents, sorted by end_at descending

        """
        ...


@runtime_checkable
class ChipRepository(Protocol):
    """Protocol for chip data access operations.

    This repository provides access to chip data, which contains qubit and coupling
    calibration parameters.

    Example
    -------
        >>> repo = MongoChipRepository()
        >>> chips = repo.list_by_project(project_id="proj-1")
        >>> chip = repo.find_by_id(project_id="proj-1", chip_id="64Qv3")

    """

    def list_by_project(self, project_id: str) -> list[ChipModel]:
        """List all chips in a project.

        Parameters
        ----------
        project_id : str
            The project identifier

        Returns
        -------
        list[ChipModel]
            List of chips in the project

        """
        ...

    def find_by_id(self, project_id: str, chip_id: str) -> ChipModel | None:
        """Find a chip by project_id and chip_id.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier

        Returns
        -------
        ChipModel | None
            The chip if found, None otherwise

        """
        ...

    def create(self, chip: ChipModel) -> ChipModel:
        """Create a new chip.

        Parameters
        ----------
        chip : ChipModel
            The chip to create

        Returns
        -------
        ChipModel
            The created chip

        Raises
        ------
        ValueError
            If a chip with the same chip_id already exists in the project

        """
        ...

    def get_current_chip(self, username: str) -> ChipModel | None:
        """Get the most recently installed chip for a user.

        Parameters
        ----------
        username : str
            The username to look up the chip

        Returns
        -------
        ChipModel | None
            The current chip or None if not found

        """
        ...

    def get_chip_by_id(self, username: str, chip_id: str) -> ChipModel | None:
        """Get a specific chip by chip_id and username.

        Parameters
        ----------
        username : str
            The username of the chip owner
        chip_id : str
            The specific chip ID to retrieve

        Returns
        -------
        ChipModel | None
            The chip if found, None otherwise

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

    # Optimized methods for scalability

    def list_summary_by_project(self, project_id: str) -> list[dict[str, Any]]:
        """List chips with summary info only."""
        ...

    def find_summary_by_id(self, project_id: str, chip_id: str) -> dict[str, Any] | None:
        """Find chip summary by ID."""
        ...

    def list_qubits(
        self,
        project_id: str,
        chip_id: str,
        limit: int = 50,
        offset: int = 0,
        qids: list[str] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """List qubits with pagination."""
        ...

    def find_qubit(self, project_id: str, chip_id: str, qid: str) -> dict[str, Any] | None:
        """Find a single qubit."""
        ...

    def list_couplings(
        self,
        project_id: str,
        chip_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List couplings with pagination."""
        ...

    def find_coupling(
        self, project_id: str, chip_id: str, coupling_id: str
    ) -> dict[str, Any] | None:
        """Find a single coupling."""
        ...

    def aggregate_metrics_summary(
        self,
        project_id: str,
        chip_id: str,
        metric_keys: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Aggregate metrics summary using MongoDB pipeline."""
        ...

    def aggregate_metric_heatmap(
        self,
        project_id: str,
        chip_id: str,
        metric: str,
        is_coupling: bool = False,
    ) -> dict[str, Any] | None:
        """Aggregate heatmap data for a single metric."""
        ...

    def get_qubit_ids(self, project_id: str, chip_id: str) -> list[str]:
        """Get all qubit IDs for a chip."""
        ...

    def get_coupling_ids(self, project_id: str, chip_id: str) -> list[str]:
        """Get all coupling IDs for a chip."""
        ...

    def get_qubits_by_ids(
        self, project_id: str, chip_id: str, qids: list[str]
    ) -> dict[str, dict[str, Any]]:
        """Get multiple qubits by their IDs."""
        ...

    def get_couplings_by_ids(
        self, project_id: str, chip_id: str, coupling_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        """Get multiple couplings by their IDs."""
        ...

    def get_all_qubit_models(self, project_id: str, chip_id: str) -> dict[str, Any]:
        """Get all qubit documents as a dict keyed by qubit ID."""
        ...

    def get_all_coupling_models(self, project_id: str, chip_id: str) -> dict[str, Any]:
        """Get all coupling documents as a dict keyed by coupling ID."""
        ...

    def get_qubit_count(self, project_id: str, chip_id: str) -> int:
        """Get the number of qubits for a chip."""
        ...


@runtime_checkable
class ChipHistoryRepository(Protocol):
    """Protocol for chip history recording operations."""

    def create_history(self, username: str, chip_id: str | None = None) -> None:
        """Create a chip history snapshot.

        Parameters
        ----------
        username : str
            The username to look up the chip
        chip_id : str, optional
            The specific chip ID to create history for.
            If None, uses the current (most recently installed) chip.

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
        initial_model: ExecutionModel | None = None,
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
        initial_model : ExecutionModel | None
            Optional initial model to use instead of fetching from database

        Returns
        -------
        ExecutionModel
            The updated execution model

        """
        ...


@runtime_checkable
class CalibrationNoteRepository(Protocol):
    """Protocol for calibration note persistence operations.

    This protocol abstracts the storage mechanism for calibration notes,
    allowing for different implementations (MongoDB, in-memory for testing, etc.).

    Example
    -------
        >>> repo = MongoCalibrationNoteRepository()
        >>> note = repo.find_latest_master(project_id="proj-1", chip_id="64Qv3")
        >>> if note:
        ...     print(note.note)

    """

    def find_one(
        self,
        *,
        project_id: str | None = None,
        username: str | None = None,
        chip_id: str | None = None,
        execution_id: str | None = None,
        task_id: str | None = None,
    ) -> CalibrationNoteModel | None:
        """Find a single calibration note by query parameters.

        All parameters are optional and used as filters. At least one
        parameter should be provided for meaningful results.

        Parameters
        ----------
        project_id : str, optional
            The project identifier
        username : str, optional
            The username who created the note
        chip_id : str, optional
            The chip identifier
        execution_id : str, optional
            The execution identifier
        task_id : str, optional
            The task identifier (e.g., "master" for master notes)

        Returns
        -------
        CalibrationNoteModel | None
            The found note or None if not found

        """
        ...

    def find_latest_master(
        self,
        *,
        chip_id: str | None = None,
        project_id: str | None = None,
        username: str | None = None,
    ) -> CalibrationNoteModel | None:
        """Find the latest master calibration note for a chip.

        Master notes (task_id="master") contain aggregated calibration data.
        This method returns the most recently updated master note.

        Parameters
        ----------
        chip_id : str, optional
            The chip identifier
        project_id : str, optional
            The project identifier
        username : str, optional
            The username who created the note

        Returns
        -------
        CalibrationNoteModel | None
            The latest master note or None if not found

        """
        ...

    def find_latest_master_by_project(
        self,
        project_id: str,
    ) -> CalibrationNoteModel | None:
        """Find the latest master calibration note for a project.

        Convenience method that finds the latest master note by project_id only.

        Parameters
        ----------
        project_id : str
            The project identifier

        Returns
        -------
        CalibrationNoteModel | None
            The latest master note or None if not found

        """
        ...

    def upsert(self, note: CalibrationNoteModel) -> CalibrationNoteModel:
        """Create or update a calibration note.

        If a note with matching identifiers (project_id, username, chip_id,
        execution_id, task_id) exists, it will be updated. Otherwise, a new
        note will be created.

        Parameters
        ----------
        note : CalibrationNoteModel
            The note to create or update

        Returns
        -------
        CalibrationNoteModel
            The saved note with updated timestamp

        """
        ...


@runtime_checkable
class QubitCalibrationRepository(Protocol):
    """Protocol for qubit calibration data operations.

    This repository handles updating qubit calibration data, which involves:
    - Merging new calibration parameters into existing data
    - Synchronizing data with ChipDocument
    - Recording history

    Note
    ----
        The update operation affects multiple collections (qubit, chip, history).
        In the future, this may be refactored to separate the business logic
        into a domain service.

    """

    def update_calib_data(
        self,
        *,
        username: str,
        qid: str,
        chip_id: str,
        output_parameters: dict[str, Any],
        project_id: str | None,
    ) -> QubitModel:
        """Update qubit calibration data with new measurement results.

        This method:
        1. Merges new parameters into existing qubit data
        2. Updates the qubit data in the chip document
        3. Records a history snapshot

        Parameters
        ----------
        username : str
            The username performing the update
        qid : str
            The qubit identifier (e.g., "0", "1")
        chip_id : str
            The chip identifier
        output_parameters : dict[str, Any]
            The new calibration parameters to merge
        project_id : str
            The project identifier

        Returns
        -------
        QubitModel
            The updated qubit model

        Raises
        ------
        ValueError
            If the qubit or chip is not found

        """
        ...

    def find_one(
        self,
        *,
        username: str,
        qid: str,
        chip_id: str,
    ) -> QubitModel | None:
        """Find a qubit by identifiers.

        Parameters
        ----------
        username : str
            The username
        qid : str
            The qubit identifier
        chip_id : str
            The chip identifier

        Returns
        -------
        QubitModel | None
            The qubit model if found, None otherwise

        """
        ...


@runtime_checkable
class CouplingCalibrationRepository(Protocol):
    """Protocol for coupling calibration data operations.

    This repository handles updating coupling calibration data between qubits.
    Similar to QubitCalibrationRepository, updates affect multiple collections.

    """

    def update_calib_data(
        self,
        *,
        username: str,
        qid: str,
        chip_id: str,
        output_parameters: dict[str, Any],
        project_id: str | None,
    ) -> CouplingModel:
        """Update coupling calibration data with new measurement results.

        Parameters
        ----------
        username : str
            The username performing the update
        qid : str
            The coupling identifier (e.g., "0-1" for coupling between qubits 0 and 1)
        chip_id : str
            The chip identifier
        output_parameters : dict[str, Any]
            The new calibration parameters to merge
        project_id : str
            The project identifier

        Returns
        -------
        CouplingModel
            The updated coupling model

        Raises
        ------
        ValueError
            If the coupling or chip is not found

        """
        ...

    def find_one(
        self,
        *,
        username: str,
        qid: str,
        chip_id: str,
    ) -> CouplingModel | None:
        """Find a coupling by identifiers.

        Parameters
        ----------
        username : str
            The username
        qid : str
            The coupling identifier
        chip_id : str
            The chip identifier

        Returns
        -------
        CouplingModel | None
            The coupling model if found, None otherwise

        """
        ...


@runtime_checkable
class ExecutionCounterRepository(Protocol):
    """Protocol for execution counter operations.

    This repository provides atomic counter generation for execution IDs.
    The counter is scoped by date, username, chip_id, and project_id.

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
        ...

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
        ...


@runtime_checkable
class ExecutionLockRepository(Protocol):
    """Protocol for execution lock operations.

    This repository provides mutual exclusion for calibration sessions.
    Only one calibration can run per project at a time.

    Example
    -------
        >>> repo = MongoExecutionLockRepository()
        >>> if not repo.is_locked(project_id="proj-1"):
        ...     repo.lock(project_id="proj-1")
        ...     try:
        ...         # run calibration
        ...     finally:
        ...         repo.unlock(project_id="proj-1")

    """

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
        ...

    def lock(self, project_id: str) -> None:
        """Acquire the execution lock.

        Parameters
        ----------
        project_id : str
            The project identifier

        """
        ...

    def unlock(self, project_id: str) -> None:
        """Release the execution lock.

        Parameters
        ----------
        project_id : str
            The project identifier

        """
        ...


@runtime_checkable
class UserRepository(Protocol):
    """Protocol for user data access.

    This repository provides read access to user information.
    Used primarily for resolving default project IDs.

    """

    def get_default_project_id(self, username: str) -> str | None:
        """Get the user's default project ID.

        Parameters
        ----------
        username : str
            The username to look up

        Returns
        -------
        str | None
            The default project ID, or None if not set or user not found

        """
        ...


@runtime_checkable
class TaskRepository(Protocol):
    """Protocol for task definition access.

    This repository provides read access to task definitions used for
    validating task names before execution.

    Example
    -------
        >>> repo = MongoTaskRepository()
        >>> names = repo.get_task_names(username="alice")
        >>> if "CheckFreq" in names:
        ...     print("Task is valid")

    """

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
        ...
