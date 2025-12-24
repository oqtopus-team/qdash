"""In-memory implementation of CouplingCalibrationRepository for testing.

This module provides a mock implementation that stores coupling calibration data in memory,
useful for unit testing without requiring a MongoDB instance.
"""

from typing import Any

from qdash.datamodel.coupling import CouplingModel


class InMemoryCouplingCalibrationRepository:
    """In-memory implementation of CouplingCalibrationRepository for testing.

    This implementation stores coupling calibration data in a dictionary,
    making it suitable for unit tests that don't require a real database.

    Example
    -------
        >>> from qdash.datamodel.coupling import CouplingModel
        >>> repo = InMemoryCouplingCalibrationRepository()
        >>> coupling = CouplingModel(qid="0-1", chip_id="chip_1", ...)
        >>> repo.add_coupling("alice", coupling)
        >>> found = repo.find_one(username="alice", qid="0-1", chip_id="chip_1")
        >>> assert found is not None

    """

    def __init__(self) -> None:
        """Initialize with empty storage."""
        self._couplings: dict[str, CouplingModel] = {}

    def _make_key(self, username: str, qid: str, chip_id: str | None) -> str:
        """Create storage key from identifiers."""
        return f"{username}:{chip_id or 'default'}:{qid}"

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
        project_id : str | None
            The project identifier

        Returns
        -------
        CouplingModel
            The updated coupling model

        """
        key = self._make_key(username, qid, chip_id)
        coupling = self._couplings.get(key)

        if coupling is None:
            # Create new coupling if not exists
            coupling = CouplingModel(
                project_id=project_id,
                username=username,
                qid=qid,
                status="",
                chip_id=chip_id,
                data={},
            )
            self._couplings[key] = coupling

        # Merge parameters into data
        for param_name, param_value in output_parameters.items():
            coupling.data[param_name] = param_value

        return coupling

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
        key = self._make_key(username, qid, chip_id)
        return self._couplings.get(key)

    def add_coupling(self, username: str, coupling: CouplingModel) -> None:
        """Add a coupling for testing (test helper).

        Parameters
        ----------
        username : str
            The username
        coupling : CouplingModel
            The coupling to add

        """
        key = self._make_key(username, coupling.qid, coupling.chip_id)
        self._couplings[key] = coupling

    def clear(self) -> None:
        """Clear all stored couplings (useful for test setup/teardown)."""
        self._couplings.clear()
