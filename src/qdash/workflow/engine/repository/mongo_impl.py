"""MongoDB implementations of repository protocols.

This module provides concrete implementations of the repository protocols
using MongoDB (via Bunnet ODM) as the backend.
"""

import logging
from typing import Any

from qdash.datamodel.chip import ChipModel
from qdash.datamodel.execution import ExecutionModel
from qdash.datamodel.task import BaseTaskResultModel, CalibDataModel
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.chip_history import ChipHistoryDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

logger = logging.getLogger(__name__)


class MongoTaskResultHistoryRepository:
    """MongoDB implementation of TaskResultHistoryRepository."""

    def save(self, task: BaseTaskResultModel, execution_model: ExecutionModel) -> None:
        """Save a task result to MongoDB."""
        TaskResultHistoryDocument.upsert_document(task=task, execution_model=execution_model)


class MongoChipRepository:
    """MongoDB implementation of ChipRepository.

    This class provides access to chip data stored in MongoDB via the
    ChipDocument ODM model.

    Example
    -------
        >>> repo = MongoChipRepository()
        >>> chip = repo.get_current_chip(username="alice")
        >>> if chip:
        ...     print(f"Found chip {chip.chip_id}")

    """

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
        try:
            chip_doc = ChipDocument.get_current_chip(username=username)
            return self._to_model(chip_doc)
        except ValueError:
            logger.warning(f"Chip not found for user {username}")
            return None

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
        chip_doc = ChipDocument.get_chip_by_id(username=username, chip_id=chip_id)
        if chip_doc is None:
            return None
        return self._to_model(chip_doc)

    def update_chip_data(
        self,
        chip_id: str,
        calib_data: CalibDataModel,
        username: str,
    ) -> None:
        """Update chip calibration data in MongoDB.

        Parameters
        ----------
        chip_id : str
            The chip ID (for logging purposes)
        calib_data : CalibDataModel
            Calibration data to merge
        username : str
            The username to look up the chip

        """
        try:
            chip = ChipDocument.get_current_chip(username=username)
        except ValueError:
            logger.warning(f"Chip not found for user {username}, skipping update")
            return

        # Merge qubit data
        for qid, params in calib_data.qubit.items():
            if qid not in chip.qubits:
                chip.qubits[qid] = {}
            for param_name, param_value in params.items():
                chip.qubits[qid][param_name] = param_value

        # Merge coupling data
        for qid, params in calib_data.coupling.items():
            if qid not in chip.couplings:
                chip.couplings[qid] = {}
            for param_name, param_value in params.items():
                chip.couplings[qid][param_name] = param_value

        chip.save()

    def _to_model(self, doc: ChipDocument) -> ChipModel:
        """Convert a ChipDocument to a ChipModel.

        Parameters
        ----------
        doc : ChipDocument
            The MongoDB document

        Returns
        -------
        ChipModel
            The domain model

        """
        return ChipModel(
            project_id=doc.project_id,
            chip_id=doc.chip_id,
            username=doc.username,
            size=doc.size,
            topology_id=doc.topology_id,
            qubits=doc.qubits,
            couplings=doc.couplings,
            installed_at=doc.installed_at,
            system_info=doc.system_info,
        )


class MongoChipHistoryRepository:
    """MongoDB implementation of ChipHistoryRepository."""

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
        if chip_id is not None:
            chip_doc = ChipDocument.get_chip_by_id(username=username, chip_id=chip_id)
        else:
            try:
                chip_doc = ChipDocument.get_current_chip(username=username)
            except ValueError:
                chip_doc = None

        if chip_doc is not None:
            ChipHistoryDocument.create_history(chip_doc)


def create_default_repositories() -> dict[str, Any]:
    """Create default MongoDB repository instances.

    Returns
    -------
    dict[str, Any]
        Dictionary containing repository instances

    """
    from qdash.workflow.engine.repository.mongo_calibration_note import (
        MongoCalibrationNoteRepository,
    )

    return {
        "task_result_history": MongoTaskResultHistoryRepository(),
        "chip": MongoChipRepository(),
        "chip_history": MongoChipHistoryRepository(),
        "calibration_note": MongoCalibrationNoteRepository(),
    }
