"""MongoDB implementation of QubitCalibrationRepository.

This module provides the concrete MongoDB implementation for qubit
calibration data persistence operations.
"""

import logging
from typing import Any

from qdash.datamodel.qubit import QubitModel
from qdash.dbmodel.qubit import QubitDocument

logger = logging.getLogger(__name__)


class MongoQubitCalibrationRepository:
    """MongoDB implementation of QubitCalibrationRepository.

    This class encapsulates all MongoDB-specific logic for qubit calibration,
    delegating to the existing QubitDocument methods.

    Note
    ----
        Currently delegates to QubitDocument.update_calib_data() which handles:
        - Data merging
        - Chip document synchronization
        - History recording

        In future refactoring, these concerns may be separated into
        domain services for better testability.

    Example
    -------
        >>> repo = MongoQubitCalibrationRepository()
        >>> updated = repo.update_calib_data(
        ...     username="alice",
        ...     qid="0",
        ...     chip_id="64Qv3",
        ...     output_parameters={"qubit_frequency": {"value": 5.0}},
        ...     project_id="proj-1",
        ... )

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

        Parameters
        ----------
        username : str
            The username performing the update
        qid : str
            The qubit identifier
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
        # Delegate to existing QubitDocument method
        doc = QubitDocument.update_calib_data(
            username=username,
            qid=qid,
            chip_id=chip_id,
            output_parameters=output_parameters,
            project_id=project_id,
        )

        return self._to_model(doc, project_id)

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
        doc = QubitDocument.find_one({"username": username, "qid": qid, "chip_id": chip_id}).run()

        if doc is None:
            return None

        return self._to_model(doc, doc.project_id)

    def _to_model(self, doc: QubitDocument, project_id: str | None) -> QubitModel:
        """Convert a document to a domain model.

        Parameters
        ----------
        doc : QubitDocument
            The MongoDB document
        project_id : str | None
            The project identifier

        Returns
        -------
        QubitModel
            The domain model

        """
        return QubitModel(
            project_id=project_id,
            username=doc.username,
            qid=doc.qid,
            status=doc.status,
            chip_id=doc.chip_id,
            data=doc.data,
            node_info=doc.node_info,
        )
