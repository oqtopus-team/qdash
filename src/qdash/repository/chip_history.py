"""MongoDB implementation of ChipHistoryRepository.

This module provides the concrete MongoDB implementation for chip
history snapshot operations.
"""

import logging
from typing import Any

from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.chip_history import ChipHistoryDocument

logger = logging.getLogger(__name__)


class MongoChipHistoryRepository:
    """MongoDB implementation of ChipHistoryRepository.

    This class handles creating point-in-time snapshots of chip configurations
    for historical tracking and audit purposes.

    Example
    -------
        >>> repo = MongoChipHistoryRepository()
        >>> repo.create_history(username="alice", chip_id="64Qv3")

    """

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

    def find_one(self, query: dict[str, Any]) -> ChipHistoryDocument | None:
        """Find a single chip history document by query.

        Parameters
        ----------
        query : dict[str, Any]
            MongoDB query dict

        Returns
        -------
        ChipHistoryDocument | None
            The matching document, or None if not found

        """
        return ChipHistoryDocument.find_one(query).run()
