"""MongoDB implementation of ChipRepository.

This module provides the concrete MongoDB implementation for chip
data persistence operations.
"""

import logging
from typing import Any

from qdash.datamodel.chip import ChipModel
from qdash.datamodel.task import CalibDataModel
from qdash.dbmodel.chip import ChipDocument

logger = logging.getLogger(__name__)


class MongoChipRepository:
    """MongoDB implementation of ChipRepository.

    This class encapsulates all MongoDB-specific logic for chip data access,
    providing a clean abstraction over the underlying database operations.

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
        docs = ChipDocument.find({"project_id": project_id}).run()
        return [self._to_model(doc) for doc in docs]

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
        doc = ChipDocument.find_one({"project_id": project_id, "chip_id": chip_id}).run()
        if doc is None:
            return None
        return self._to_model(doc)

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
        # Check for existing chip
        existing = ChipDocument.find_one(
            {"project_id": chip.project_id, "chip_id": chip.chip_id}
        ).run()
        if existing is not None:
            raise ValueError(f"Chip {chip.chip_id} already exists in project {chip.project_id}")

        # Create new document
        doc = ChipDocument(
            project_id=chip.project_id,
            chip_id=chip.chip_id,
            username=chip.username,
            size=chip.size,
            topology_id=chip.topology_id,
            qubits=chip.qubits,
            couplings=chip.couplings,
            installed_at=chip.installed_at,
            system_info=chip.system_info,
        )
        doc.insert()
        return self._to_model(doc)

    def find_one_document(self, query: dict[str, Any]) -> ChipDocument | None:
        """Find a single chip document by query.

        Parameters
        ----------
        query : dict[str, Any]
            MongoDB query dict

        Returns
        -------
        ChipDocument | None
            The chip document if found, None otherwise

        """
        return ChipDocument.find_one(query).run()

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
        doc = self.find_one_document({"username": username})
        if doc is None:
            return None
        return self._to_model(doc)

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
        doc = ChipDocument.find_one({"username": username, "chip_id": chip_id}).run()
        if doc is None:
            return None
        return self._to_model(doc)

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
        ChipDocument.update_chip_data(
            chip_id=chip_id,
            calib_data=calib_data,
            username=username,
        )

    def _to_model(self, doc: ChipDocument) -> ChipModel:
        """Convert a document to a domain model.

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
