"""Topology- and relationship-oriented Copilot data loaders."""

from __future__ import annotations

from typing import Any, Protocol


class TopologyContextDataAccessProtocol(Protocol):
    """Subset of data-access methods used for topology-related Copilot helpers."""

    def load_chip(self, chip_id: str) -> Any | None: ...

    def load_qubit(self, chip_id: str, qid: str) -> Any | None: ...

    def load_coupling(self, chip_id: str, coupling_id: str) -> Any | None: ...


class TopologyContextLoader:
    """Load topology, neighbor, coupling, and comparison views for Copilot tools."""

    def __init__(
        self,
        *,
        data_access: TopologyContextDataAccessProtocol,
        compact_number: Any,
        sanitize_for_json: Any,
    ) -> None:
        self._data_access = data_access
        self._compact_number = compact_number
        self._sanitize_for_json = sanitize_for_json

    def load_neighbor_qubit_params(
        self,
        *,
        chip_id: str,
        qid: str,
        param_names: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Load specified parameters from neighboring qubits via topology."""
        topology = self._load_chip_topology_model(chip_id)
        if topology is None:
            return {}

        try:
            qid_int = int(qid)
        except ValueError:
            return {}

        neighbors: set[int] = set()
        for q1, q2 in topology.couplings:
            if q1 == qid_int:
                neighbors.add(q2)
            elif q2 == qid_int:
                neighbors.add(q1)

        result: dict[str, dict[str, Any]] = {}
        for neighbor_id in sorted(neighbors):
            neighbor_qid = str(neighbor_id)
            doc = self._data_access.load_qubit(chip_id, neighbor_qid)
            if doc is None:
                continue
            params = {name: doc.data[name] for name in param_names if name in doc.data}
            if params:
                result[neighbor_qid] = params
        return result

    def load_coupling_params(
        self,
        *,
        chip_id: str,
        qid: str,
        param_names: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Load specified parameters from couplings related to the target qubit."""
        if "-" in qid:
            coupling_ids = [qid]
        else:
            related_coupling_ids = self._resolve_related_coupling_ids(
                chip_id=chip_id,
                qubit_id=qid,
            )
            if not isinstance(related_coupling_ids, list):
                return {}
            coupling_ids = related_coupling_ids

        result: dict[str, dict[str, Any]] = {}
        for coupling_id in coupling_ids:
            doc = self._data_access.load_coupling(chip_id, coupling_id)
            if doc is None:
                continue
            params = {name: doc.data[name] for name in param_names if name in doc.data}
            if params:
                result[coupling_id] = params
        return result

    def load_coupling_params_tool(
        self,
        *,
        chip_id: str,
        coupling_id: str | None = None,
        qubit_id: str | None = None,
        param_names: list[str] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Load coupling parameters by coupling_id or qubit_id."""
        if coupling_id:
            coupling_ids = [coupling_id]
        elif qubit_id:
            resolved_coupling_ids = self._resolve_related_coupling_ids(
                chip_id=chip_id,
                qubit_id=qubit_id,
                missing_chip_error={"error": f"Chip {chip_id} not found or has no topology"},
                invalid_qubit_error={"error": f"Invalid qubit_id: {qubit_id}"},
            )
            if isinstance(resolved_coupling_ids, dict):
                return resolved_coupling_ids
            if resolved_coupling_ids is None:
                return {"error": f"Chip {chip_id} not found or has no topology"}
            coupling_ids = resolved_coupling_ids
        else:
            return {"error": "Either coupling_id or qubit_id must be provided"}

        results: list[dict[str, Any]] = []
        for current_coupling_id in coupling_ids:
            doc = self._data_access.load_coupling(chip_id, current_coupling_id)
            if doc is None:
                continue
            data = dict(doc.data)
            if param_names:
                data = {key: value for key, value in data.items() if key in param_names}
            results.append(
                {
                    "coupling_id": current_coupling_id,
                    "data": self._sanitize_for_json(data),
                }
            )

        if not results:
            return {"error": "No coupling data found"}
        return results

    def load_compare_qubits(
        self,
        *,
        chip_id: str,
        qids: list[str],
        param_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """Load and compare parameters across multiple qubits."""
        comparison: dict[str, dict[str, Any]] = {}
        for qid in qids:
            doc = self._data_access.load_qubit(chip_id, qid)
            if doc is None:
                comparison[qid] = {"error": f"Qubit {qid} not found"}
                continue
            data = dict(doc.data)
            if param_names:
                data = {key: value for key, value in data.items() if key in param_names}

            compact: dict[str, Any] = {}
            for key, value in data.items():
                raw_value = value.get("value") if isinstance(value, dict) and "value" in value else value
                compact[key] = (
                    self._compact_number(raw_value) if isinstance(raw_value, (int, float)) else raw_value
                )
            comparison[qid] = compact

        return {"chip_id": chip_id, "qubits": comparison}

    def load_chip_topology(self, *, chip_id: str) -> dict[str, Any]:
        """Load chip topology information."""
        chip = self._data_access.load_chip(chip_id)
        if chip is None:
            return {"error": f"Chip {chip_id} not found"}
        if chip.topology_id is None:
            return {"error": f"Chip {chip_id} has no topology configured"}

        topology = self._load_topology(chip.topology_id)
        qubit_positions = {
            str(qid): {"row": pos.row, "col": pos.col} for qid, pos in topology.qubits.items()
        }
        couplings = [[q1, q2] for q1, q2 in topology.couplings]
        return {
            "chip_id": chip_id,
            "topology_id": chip.topology_id,
            "grid_size": topology.grid_size,
            "num_qubits": topology.num_qubits,
            "layout_type": topology.layout_type,
            "qubit_positions": qubit_positions,
            "couplings": couplings,
        }

    def _load_chip_topology_model(self, chip_id: str) -> Any | None:
        chip = self._data_access.load_chip(chip_id)
        if chip is None or chip.topology_id is None:
            return None
        return self._load_topology(chip.topology_id)

    def _resolve_related_coupling_ids(
        self,
        *,
        chip_id: str,
        qubit_id: str,
        missing_chip_error: dict[str, Any] | None = None,
        invalid_qubit_error: dict[str, Any] | None = None,
    ) -> list[str] | dict[str, Any] | None:
        topology = self._load_chip_topology_model(chip_id)
        if topology is None:
            return missing_chip_error

        try:
            qid_int = int(qubit_id)
        except ValueError:
            return invalid_qubit_error

        return [
            f"{q1}-{q2}"
            for q1, q2 in topology.couplings
            if q1 == qid_int or q2 == qid_int
        ]

    @staticmethod
    def _load_topology(topology_id: str) -> Any:
        from qdash.common.topology_config import load_topology

        return load_topology(topology_id)
