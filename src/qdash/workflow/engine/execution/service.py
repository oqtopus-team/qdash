"""ExecutionService for managing execution lifecycle with persistence.

This module provides the ExecutionService class that orchestrates execution
state management and persistence through the repository layer.
"""

import logging
from collections.abc import Callable
from typing import Any, cast

from qdash.datamodel.execution import (
    ExecutionModel,
    ExecutionStatusModel,
)
from qdash.datamodel.system_info import SystemInfoModel
from qdash.datamodel.task import CalibDataModel
from qdash.dbmodel.initialize import initialize
from qdash.repository import MongoExecutionRepository
from qdash.repository.protocols import ExecutionRepository
from qdash.workflow.engine.execution.models import ExecutionNote
from qdash.workflow.engine.execution.state_manager import (
    ExecutionStateManager,
)

initialize()

logger = logging.getLogger(__name__)


class ExecutionService:
    """Service for managing execution lifecycle with persistence.

    This class orchestrates:

    - Execution state transitions via ExecutionStateManager
    - Persistence via ExecutionRepository
    - Optimistic locking for concurrent updates

    Attributes
    ----------
    state_manager : ExecutionStateManager
        Manager for execution state (pure logic)
    repository : ExecutionRepository
        Repository for persistence operations

    Example
    -------
    ```python
    service = ExecutionService.create(
        username="alice",
        execution_id="20240101-001",
        calib_data_path="/app/calib_data/alice/20240101/001",
        chip_id="chip_1",
        name="My Calibration",
        tags=["daily"],
    )

    # Start execution
    service.start()

    # Merge calibration data
    service.merge_calib_data(calib_data)

    # Complete execution
    service.complete()
    ```
    """

    state_manager: ExecutionStateManager
    repository: ExecutionRepository

    def __init__(
        self,
        state_manager: ExecutionStateManager,
        repository: ExecutionRepository | None = None,
    ):
        """Initialize ExecutionService.

        Parameters
        ----------
        state_manager : ExecutionStateManager
            Manager for execution state
        repository : ExecutionRepository | None
            Repository for persistence (defaults to MongoExecutionRepository)
        """
        self.state_manager = state_manager
        self.repository = repository or MongoExecutionRepository()

    @classmethod
    def create(
        cls,
        username: str,
        execution_id: str,
        calib_data_path: str,
        chip_id: str,
        name: str = "",
        tags: list[str] | None = None,
        note: dict[str, Any] | None = None,
        project_id: str | None = None,
        repository: ExecutionRepository | None = None,
    ) -> "ExecutionService":
        """Create a new ExecutionService with initial state.

        Parameters
        ----------
        username : str
            Username for the execution
        execution_id : str
            Unique execution identifier
        calib_data_path : str
            Path for calibration data storage
        chip_id : str
            Target chip ID
        name : str
            Human-readable execution name
        tags : list[str] | None
            Tags for categorization
        note : dict | None
            Additional notes
        project_id : str | None
            Project identifier
        repository : ExecutionRepository | None
            Custom repository (defaults to MongoDB)

        Returns
        -------
        ExecutionService
            New service instance with initialized state
        """
        state_manager = ExecutionStateManager(
            username=username,
            execution_id=execution_id,
            calib_data_path=calib_data_path,
            chip_id=chip_id,
            name=name,
            tags=tags or [],
            note=ExecutionNote.from_dict(note),
            project_id=project_id,
            status=ExecutionStatusModel.SCHEDULED,
        )

        return cls(state_manager=state_manager, repository=repository)

    @classmethod
    def from_existing(
        cls,
        execution_id: str,
        repository: ExecutionRepository | None = None,
    ) -> "ExecutionService | None":
        """Load an existing execution from the repository.

        Parameters
        ----------
        execution_id : str
            Execution ID to load
        repository : ExecutionRepository | None
            Custom repository (defaults to MongoDB)

        Returns
        -------
        ExecutionService | None
            Service instance if found, None otherwise
        """
        repo = repository or MongoExecutionRepository()
        model = repo.find_by_id(execution_id)

        if model is None:
            return None

        state_manager = ExecutionStateManager.from_datamodel(model)
        return cls(state_manager=state_manager, repository=repo)

    def save(self) -> "ExecutionService":
        """Save current state to repository.

        Returns
        -------
        ExecutionService
            Self for method chaining
        """
        model = self.state_manager.to_datamodel()
        self.repository.save(model)
        return self

    def start(self) -> "ExecutionService":
        """Start the execution and persist.

        Returns
        -------
        ExecutionService
            Self for method chaining
        """
        self.state_manager.start()
        return self.save()

    def complete(self) -> "ExecutionService":
        """Complete the execution and persist.

        Returns
        -------
        ExecutionService
            Self for method chaining
        """
        self.state_manager.complete()
        return self.save()

    def fail(self) -> "ExecutionService":
        """Fail the execution and persist.

        Returns
        -------
        ExecutionService
            Self for method chaining
        """
        self.state_manager.fail()
        return self.save()

    def reload(self) -> "ExecutionService":
        """Reload state from repository.

        Note: calib_data is preserved from the current in-memory state since
        it is no longer persisted to the database. This ensures workflow
        tasks can continue to access calibration data accumulated during
        the current execution.

        Returns
        -------
        ExecutionService
            Self for method chaining

        Raises
        ------
        ValueError
            If execution not found in repository
        """
        # Preserve in-memory calib_data before reload
        current_calib_data = self.state_manager.calib_data

        model = self.repository.find_by_id(self.state_manager.execution_id)
        if model is None:
            raise ValueError(f"Execution {self.state_manager.execution_id} not found")
        self.state_manager = ExecutionStateManager.from_datamodel(model)

        # Restore in-memory calib_data (not persisted to DB)
        self.state_manager.calib_data = current_calib_data
        return self

    def merge_calib_data(self, calib_data: CalibDataModel) -> "ExecutionService":
        """Merge calibration data into in-memory state.

        Note: calib_data is no longer persisted to the database to reduce
        document size. It is only maintained in-memory during workflow
        execution. Persistent calibration data is stored in qubit/coupling
        collections.

        Parameters
        ----------
        calib_data : CalibDataModel
            Calibration data to merge

        Returns
        -------
        ExecutionService
            Self for method chaining
        """
        # Only update in-memory state, not persisted to DB
        self.state_manager.merge_calib_data(calib_data)
        return self

    def update_note(self, key: str, value: Any) -> "ExecutionService":
        """Update a note entry and persist.

        For known fields (stage_results, github_push_results, config_commit_id),
        use the appropriate setter. For other keys, they are stored in 'extra'.

        Parameters
        ----------
        key : str
            Note key
        value : Any
            Note value

        Returns
        -------
        ExecutionService
            Self for method chaining
        """

        def update_func(model: ExecutionModel) -> None:
            model.note[key] = value

        self._update_with_lock(update_func)
        # Store in extra field for unknown keys
        self.state_manager.note.extra[key] = value
        return self

    def _update_with_lock(self, update_func: Callable[[ExecutionModel], None]) -> None:
        """Update with optimistic locking via repository.

        Parameters
        ----------
        update_func : callable
            Function to apply to the model
        """
        initial_model = self.state_manager.to_datamodel()
        self.repository.update_with_optimistic_lock(
            execution_id=self.state_manager.execution_id,
            update_func=update_func,
            initial_model=initial_model,
        )

    # === Property accessors for compatibility ===

    @property
    def execution_id(self) -> str:
        """Get execution ID."""
        return str(self.state_manager.execution_id)

    @property
    def username(self) -> str:
        """Get username."""
        return str(self.state_manager.username)

    @property
    def chip_id(self) -> str:
        """Get chip ID."""
        return str(self.state_manager.chip_id)

    @property
    def calib_data_path(self) -> str:
        """Get calibration data path."""
        return str(self.state_manager.calib_data_path)

    @property
    def status(self) -> ExecutionStatusModel:
        """Get execution status."""
        return self.state_manager.status

    @property
    def calib_data(self) -> CalibDataModel:
        """Get calibration data."""
        return self.state_manager.calib_data

    @property
    def note(self) -> ExecutionNote:
        """Get note (returns ExecutionNote model)."""
        return self.state_manager.note

    @note.setter
    def note(self, value: ExecutionNote | dict[str, Any]) -> None:
        """Set note."""
        if isinstance(value, dict):
            self.state_manager.note = ExecutionNote.from_dict(value)
        else:
            self.state_manager.note = value

    def to_datamodel(self) -> ExecutionModel:
        """Convert to ExecutionModel.

        Returns
        -------
        ExecutionModel
            The execution model
        """
        return self.state_manager.to_datamodel()

    # === Additional properties for ExecutionManager compatibility ===

    @property
    def name(self) -> str:
        """Get execution name."""
        return str(self.state_manager.name)

    @property
    def project_id(self) -> str | None:
        """Get project ID."""
        return cast(str | None, self.state_manager.project_id)

    @property
    def tags(self) -> list[str]:
        """Get tags."""
        return list(self.state_manager.tags)

    @property
    def start_at(self) -> str:
        """Get start time."""
        return str(self.state_manager.start_at)

    @property
    def end_at(self) -> str:
        """Get end time."""
        return str(self.state_manager.end_at)

    @property
    def elapsed_time(self) -> str:
        """Get elapsed time."""
        return str(self.state_manager.elapsed_time)

    @property
    def system_info(self) -> SystemInfoModel:
        """Get system info."""
        return self.state_manager.system_info

    @property
    def message(self) -> str:
        """Get message."""
        return str(self.state_manager.message)

    # === Methods for ExecutionManager compatibility ===

    def update_with_calib_data(
        self,
        calib_data: CalibDataModel,
    ) -> "ExecutionService":
        """Update execution with calibration data.

        This is a replacement for ExecutionManager.update_with_task_manager().

        Note: calib_data is only updated in-memory and stored in qubit/coupling
        collections. Task results are persisted separately to task_result_history
        collection by TaskResultHistoryRepository.

        Parameters
        ----------
        calib_data : CalibDataModel
            Calibration data to merge

        Returns
        -------
        ExecutionService
            Self for method chaining
        """
        self.state_manager.merge_calib_data(calib_data)
        return self

    def start_execution(self) -> "ExecutionService":
        """Start the execution (alias for start()).

        Returns
        -------
        ExecutionService
            Self for method chaining
        """
        return self.start()

    def complete_execution(self) -> "ExecutionService":
        """Complete the execution (alias for complete()).

        Returns
        -------
        ExecutionService
            Self for method chaining
        """
        return self.complete()

    def fail_execution(self) -> "ExecutionService":
        """Fail the execution (alias for fail()).

        Returns
        -------
        ExecutionService
            Self for method chaining
        """
        return self.fail()

    def save_with_tags(self) -> "ExecutionService":
        """Save current state to repository and auto-register tags.

        Note: Tags are automatically registered by the repository's save() method,
        so this method is now equivalent to save(). Kept for backward compatibility.

        Returns
        -------
        ExecutionService
            Self for method chaining
        """
        # Tags are auto-registered in MongoExecutionRepository.save()
        return self.save()

    def ensure_saved(self) -> "ExecutionService":
        """Ensure execution exists in database (upsert if not found).

        Returns
        -------
        ExecutionService
            Self for method chaining
        """
        model = self.repository.find_by_id(self.state_manager.execution_id)
        if model is None:
            self.save()
        return self
