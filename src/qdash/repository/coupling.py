"""MongoDB implementation of CouplingCalibrationRepository.

This module provides the concrete MongoDB implementation for coupling
calibration data persistence operations.
"""

import logging
from typing import Any

from qdash.datamodel.coupling import CouplingModel
from qdash.dbmodel.coupling import CouplingDocument

logger = logging.getLogger(__name__)


class MongoCouplingCalibrationRepository:
    """MongoDB implementation of CouplingCalibrationRepository.

    This class encapsulates all MongoDB-specific logic for coupling calibration,
    delegating to the existing CouplingDocument methods.

    Note
    ----
        Currently delegates to CouplingDocument.update_calib_data() which handles:
        - Data merging
        - Chip document synchronization
        - History recording

        In future refactoring, these concerns may be separated into
        domain services for better testability.

    Example
    -------
        >>> repo = MongoCouplingCalibrationRepository()
        >>> updated = repo.update_calib_data(
        ...     username="alice",
        ...     qid="0-1",
        ...     chip_id="64Qv3",
        ...     output_parameters={"zx90_gate_fidelity": {"value": 0.99}},
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
    ) -> CouplingModel:
        """Update coupling calibration data with new measurement results.

        Parameters
        ----------
        username : str
            The username performing the update
        qid : str
            The coupling identifier (e.g., "0-1")
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
        # Delegate to existing CouplingDocument method
        doc = CouplingDocument.update_calib_data(
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
        doc = CouplingDocument.find_one(
            {"username": username, "qid": qid, "chip_id": chip_id}
        ).run()

        if doc is None:
            return None

        return self._to_model(doc, doc.project_id)

    def get_calibration_data(
        self,
        *,
        project_id: str,
        chip_id: str,
        qid: str,
    ) -> dict[str, Any]:
        """Get calibration data for a coupling.

        This method retrieves the calibration data dictionary for a specific coupling,
        which can be used to populate input_parameters in task preprocessing.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier
        qid : str
            The coupling identifier (e.g., "0-1")

        Returns
        -------
        dict[str, Any]
            The calibration data dictionary, or empty dict if not found.
            Format: {"param_name": {"value": ..., "unit": ..., ...}, ...}

        """
        doc = CouplingDocument.find_one(
            {"project_id": project_id, "chip_id": chip_id, "qid": qid}
        ).run()

        if doc is None:
            return {}

        return dict(doc.data)

    def _to_model(self, doc: CouplingDocument, project_id: str | None) -> CouplingModel:
        """Convert a document to a domain model.

        Parameters
        ----------
        doc : CouplingDocument
            The MongoDB document
        project_id : str | None
            The project identifier

        Returns
        -------
        CouplingModel
            The domain model

        """
        return CouplingModel(
            project_id=project_id,
            username=doc.username,
            qid=doc.qid,
            status=doc.status,
            chip_id=doc.chip_id,
            data=doc.data,
        )
