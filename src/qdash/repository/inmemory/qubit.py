"""In-memory implementation of QubitCalibrationRepository for testing.

This module provides a mock implementation that stores qubit calibration data in memory,
useful for unit testing without requiring a MongoDB instance.
"""

from typing import Any

from qdash.datamodel.qubit import QubitModel


class InMemoryQubitCalibrationRepository:
    """In-memory implementation of QubitCalibrationRepository for testing.

    This implementation stores qubit calibration data in a dictionary,
    making it suitable for unit tests that don't require a real database.

    Example
    -------
        >>> from qdash.datamodel.qubit import QubitModel
        >>> repo = InMemoryQubitCalibrationRepository()
        >>> qubit = QubitModel(qid="0", chip_id="chip_1", ...)
        >>> repo.add_qubit("alice", qubit)
        >>> found = repo.find_one(username="alice", qid="0", chip_id="chip_1")
        >>> assert found is not None

    """

    def __init__(self) -> None:
        """Initialize with empty storage."""
        self._qubits: dict[str, QubitModel] = {}

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
    ) -> QubitModel:
        """Update qubit calibration data with new measurement results.

        Parameters
        ----------
        username : str
            The username performing the update
        qid : str
            The qubit identifier (e.g., "0", "1")
        chip_id : str
            The chip identifier
        output_parameters : dict[str, Any]
            The new calibration parameters to merge
        project_id : str | None
            The project identifier

        Returns
        -------
        QubitModel
            The updated qubit model

        """
        key = self._make_key(username, qid, chip_id)
        qubit = self._qubits.get(key)

        if qubit is None:
            # Create new qubit if not exists
            qubit = QubitModel(
                project_id=project_id,
                username=username,
                qid=qid,
                status="",
                chip_id=chip_id,
                data={},
                best_data={},
                node_info=None,
            )
            self._qubits[key] = qubit

        # Merge parameters into data
        for param_name, param_value in output_parameters.items():
            qubit.data[param_name] = param_value

        return qubit

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
        key = self._make_key(username, qid, chip_id)
        return self._qubits.get(key)

    def add_qubit(self, username: str, qubit: QubitModel) -> None:
        """Add a qubit for testing (test helper).

        Parameters
        ----------
        username : str
            The username
        qubit : QubitModel
            The qubit to add

        """
        key = self._make_key(username, qubit.qid, qubit.chip_id)
        self._qubits[key] = qubit

    def clear(self) -> None:
        """Clear all stored qubits (useful for test setup/teardown)."""
        self._qubits.clear()
