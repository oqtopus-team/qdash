"""MongoDB implementations of repository protocols.

This module provides concrete implementations of the repository protocols
using MongoDB (via Bunnet ODM) as the backend.
"""

import logging
from typing import Any

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
    """MongoDB implementation of ChipRepository."""

    def get_current_chip(self, username: str) -> dict[str, Any]:
        """Get current chip data from MongoDB.

        Parameters
        ----------
        username : str
            The username to look up the chip

        Returns
        -------
        dict
            Chip data with qubit and coupling keys

        """
        try:
            chip = ChipDocument.get_current_chip(username=username)
            return {
                "qubit": chip.qubit or {},
                "coupling": chip.coupling or {},
            }
        except ValueError:
            logger.warning(f"Chip not found for user {username}")
            return {"qubit": {}, "coupling": {}}

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
            if qid not in chip.qubit:
                chip.qubit[qid] = {}
            for param_name, param_value in params.items():
                chip.qubit[qid][param_name] = param_value

        # Merge coupling data
        for qid, params in calib_data.coupling.items():
            if qid not in chip.coupling:
                chip.coupling[qid] = {}
            for param_name, param_value in params.items():
                chip.coupling[qid][param_name] = param_value

        chip.save()


class MongoChipHistoryRepository:
    """MongoDB implementation of ChipHistoryRepository."""

    def create_history(self, username: str) -> None:
        """Create a chip history snapshot from the current chip state.

        Parameters
        ----------
        username : str
            The username to look up the chip

        """
        chip_doc = ChipDocument.get_current_chip(username=username)
        if chip_doc is not None:
            ChipHistoryDocument.create_history(chip_doc)


def create_default_repositories() -> dict[str, Any]:
    """Create default MongoDB repository instances.

    Returns
    -------
    dict[str, Any]
        Dictionary containing repository instances

    """
    return {
        "task_result_history": MongoTaskResultHistoryRepository(),
        "chip": MongoChipRepository(),
        "chip_history": MongoChipHistoryRepository(),
    }
