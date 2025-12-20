"""In-memory implementation of ChipRepository for testing.

This module provides a mock implementation that stores data in memory,
useful for unit testing without requiring a MongoDB instance.
"""

from typing import Any

from qdash.datamodel.chip import ChipModel
from qdash.datamodel.task import CalibDataModel


class InMemoryChipRepository:
    """In-memory implementation of ChipRepository for testing.

    This implementation stores chips in a dictionary, making it suitable
    for unit tests that don't require a real database.

    Example
    -------
        >>> repo = InMemoryChipRepository()
        >>> chip = ChipModel(chip_id="chip_1", project_id="proj-1", ...)
        >>> repo.create(chip)
        >>> found = repo.find_by_id("proj-1", "chip_1")
        >>> assert found.chip_id == "chip_1"

    """

    def __init__(self) -> None:
        """Initialize with empty storage."""
        self._chips: dict[str, ChipModel] = {}  # key: "{project_id}:{chip_id}"
        self._chips_by_user: dict[str, ChipModel] = {}  # key: username

    def _make_key(self, project_id: str, chip_id: str) -> str:
        """Create storage key from identifiers."""
        return f"{project_id}:{chip_id}"

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
        return [chip for chip in self._chips.values() if chip.project_id == project_id]

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
        key = self._make_key(project_id, chip_id)
        return self._chips.get(key)

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
        key = self._make_key(chip.project_id or "", chip.chip_id)
        if key in self._chips:
            raise ValueError(f"Chip {chip.chip_id} already exists in project {chip.project_id}")
        self._chips[key] = chip
        self._chips_by_user[chip.username] = chip
        return chip

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
        return self._chips_by_user.get(username)

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
        for chip in self._chips.values():
            if chip.username == username and chip.chip_id == chip_id:
                return chip
        return None

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
        chip = self.get_chip_by_id(username, chip_id)
        if chip is None:
            return

        # Merge qubit data
        for qid, data in calib_data.qubit.items():
            if qid in chip.qubits:
                for param_name, param_value in data.items():
                    chip.qubits[qid].data[param_name] = param_value

        # Merge coupling data
        for cid, data in calib_data.coupling.items():
            if cid in chip.couplings:
                for param_name, param_value in data.items():
                    chip.couplings[cid].data[param_name] = param_value

    def clear(self) -> None:
        """Clear all stored chips (useful for test setup/teardown)."""
        self._chips.clear()
        self._chips_by_user.clear()
