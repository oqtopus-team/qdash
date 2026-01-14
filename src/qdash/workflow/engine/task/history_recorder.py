"""TaskHistoryRecorder for recording task results to persistent storage.

This module provides the TaskHistoryRecorder class that handles recording
task results, chip updates, chip history, and optionally provenance to MongoDB.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from qdash.repository import (
    MongoChipHistoryRepository,
    MongoChipRepository,
    MongoTaskResultHistoryRepository,
)

if TYPE_CHECKING:
    from qdash.datamodel.execution import ExecutionModel
    from qdash.datamodel.task import BaseTaskResultModel, CalibDataModel
    from qdash.workflow.engine.task.provenance_recorder import ProvenanceRecorder

logger = logging.getLogger(__name__)


@runtime_checkable
class TaskResultHistoryRepoProtocol(Protocol):
    """Protocol for task result history repository."""

    def save(self, task: BaseTaskResultModel, execution_model: ExecutionModel) -> None:
        """Save task result."""
        ...


@runtime_checkable
class ChipRepoProtocol(Protocol):
    """Protocol for chip repository."""

    def update_chip_data(self, chip_id: str, calib_data: CalibDataModel, username: str) -> None:
        """Update chip data."""
        ...


@runtime_checkable
class ChipHistoryRepoProtocol(Protocol):
    """Protocol for chip history repository."""

    def create_history(self, username: str) -> None:
        """Create chip history."""
        ...


class TaskHistoryRecorder:
    """Recorder for persisting task results and chip data.

    This class handles:
    - Recording task results to TaskResultHistoryDocument
    - Updating chip calibration data
    - Creating chip history snapshots
    - Optionally recording provenance for data lineage tracking

    Attributes
    ----------
    task_result_history_repo : TaskResultHistoryRepoProtocol
        Repository for task result history
    chip_repo : ChipRepoProtocol
        Repository for chip data
    chip_history_repo : ChipHistoryRepoProtocol
        Repository for chip history
    provenance_recorder : ProvenanceRecorder | None
        Optional recorder for provenance tracking

    """

    def __init__(
        self,
        task_result_history_repo: TaskResultHistoryRepoProtocol | None = None,
        chip_repo: ChipRepoProtocol | None = None,
        chip_history_repo: ChipHistoryRepoProtocol | None = None,
        provenance_recorder: ProvenanceRecorder | None = None,
    ) -> None:
        """Initialize TaskHistoryRecorder.

        Parameters
        ----------
        task_result_history_repo : TaskResultHistoryRepoProtocol | None
            Repository for task result history (default: MongoTaskResultHistoryRepository)
        chip_repo : ChipRepoProtocol | None
            Repository for chip data (default: MongoChipRepository)
        chip_history_repo : ChipHistoryRepoProtocol | None
            Repository for chip history (default: MongoChipHistoryRepository)
        provenance_recorder : ProvenanceRecorder | None
            Optional recorder for provenance tracking (default: None, disabled)

        """
        self.task_result_history_repo = (
            task_result_history_repo or MongoTaskResultHistoryRepository()
        )
        self.chip_repo = chip_repo or MongoChipRepository()
        self.chip_history_repo = chip_history_repo or MongoChipHistoryRepository()
        self.provenance_recorder = provenance_recorder

    def record_task_result(
        self,
        task: BaseTaskResultModel,
        execution_model: ExecutionModel,
    ) -> None:
        """Record a task result to the history.

        This method saves the task result to history and optionally
        records provenance for data lineage tracking.

        Parameters
        ----------
        task : BaseTaskResultModel
            The task result to record
        execution_model : ExecutionModel
            The parent execution context

        """
        try:
            self.task_result_history_repo.save(task, execution_model)
        except Exception as e:
            logger.error(f"Failed to record task result: {e}")
            raise

        # Record provenance if enabled (non-blocking)
        if self.provenance_recorder is not None:
            try:
                self.provenance_recorder.record_from_task(task, execution_model)
            except Exception as e:
                # Log but don't fail the task - provenance is optional
                logger.warning(f"Failed to record provenance for task {task.name}: {e}")

    def update_chip_with_calib_data(
        self,
        chip_id: str,
        calib_data: CalibDataModel,
        username: str,
    ) -> None:
        """Update chip with calibration data.

        Parameters
        ----------
        chip_id : str
            The chip identifier
        calib_data : CalibDataModel
            The calibration data to merge
        username : str
            The user performing the update

        """
        try:
            self.chip_repo.update_chip_data(chip_id, calib_data, username)
        except Exception as e:
            logger.error(f"Failed to update chip data: {e}")
            raise

    def create_chip_history_snapshot(self, username: str) -> None:
        """Create a chip history snapshot.

        Parameters
        ----------
        username : str
            The username for chip lookup

        Note
        ----
        This method does not raise exceptions - errors are logged but
        do not interrupt the workflow (matching original TaskManager behavior).

        """
        try:
            self.chip_history_repo.create_history(username)
        except Exception as e:
            logger.error(f"Failed to create chip history snapshot: {e}")
            # Don't raise - this shouldn't block the workflow

    def record_completed_task(
        self,
        task: BaseTaskResultModel,
        execution_model: ExecutionModel,
        chip_id: str,
        calib_data: CalibDataModel,
        username: str,
        create_history: bool = True,
    ) -> None:
        """Record a completed task with all associated updates.

        This method:
        1. Records the task result to history
        2. Updates chip calibration data
        3. Optionally creates a chip history snapshot

        Parameters
        ----------
        task : BaseTaskResultModel
            The task result to record
        execution_model : ExecutionModel
            The parent execution context
        chip_id : str
            The chip identifier
        calib_data : CalibDataModel
            The calibration data to merge
        username : str
            The user performing the updates
        create_history : bool
            Whether to create a chip history snapshot

        """
        # Record task result
        self.record_task_result(task, execution_model)

        # Update chip data
        self.update_chip_with_calib_data(chip_id, calib_data, username)

        # Create chip history snapshot if requested
        if create_history:
            self.create_chip_history_snapshot(username)
