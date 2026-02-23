"""Device topology service for QDash API.

This module provides business logic for building and filtering quantum
device topologies, abstracting away the data assembly from the router.
"""

from __future__ import annotations

import io
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import networkx as nx
from qdash.api.schemas.device_topology import (
    Coupling,
    CouplingGateDuration,
    Device,
    DeviceTopologyRequest,
    MeasError,
    Position,
    Qubit,
    QubitGateDuration,
    QubitLifetime,
)
from qdash.common.datetime_utils import now, to_datetime
from qdash.common.qubit_utils import qid_to_label
from qdash.common.topology_config import load_topology

if TYPE_CHECKING:
    from qdash.repository.protocols import CalibrationNoteRepository, ChipRepository

logger = logging.getLogger(__name__)

# Constants for position calculation
POSITION_SCALE = 50
POSITION_DIVISOR = 30

assert POSITION_DIVISOR != 0, "POSITION_DIVISOR must not be zero"


def _is_within_24h(calibrated_at: str | None) -> bool:
    """Check if the calibrated timestamp is within 24 hours."""
    if not calibrated_at:
        return False
    try:
        cutoff = now() - timedelta(hours=24)
        calibrated_at_dt = to_datetime(calibrated_at)
        if calibrated_at_dt is None:
            return False
        return bool(calibrated_at_dt >= cutoff)
    except Exception:
        return False


def _get_value_within_24h_fallback(data: dict[str, Any], use_24h: bool, fallback: float) -> float:
    """Get calibrated value with optional 24h freshness check."""
    value = data.get("value")
    calibrated_at = data.get("calibrated_at")
    if value is None:
        return fallback
    if use_24h:
        return float(value) if _is_within_24h(calibrated_at) else fallback
    return float(value)


def _search_coupling_data_by_control_qid(
    cr_params: dict[str, Any], search_term: str
) -> dict[str, Any]:
    """Search for coupling data by control qubit id."""
    filtered = {}
    for key, value in cr_params.items():
        left_side = key.split("-")[0] if "-" in key else key
        if left_side == search_term:
            filtered[key] = value
    return filtered


def _normalize_coupling_key(control: str, target: str) -> str:
    """Normalize coupling key by sorting the qubits."""
    qubits = sorted([control, target])
    return f"{qubits[0]}-{qubits[1]}"


def _split_q_string(cr_label: str) -> tuple[str, str]:
    """Split a string of the form 'Q31-Q29' into two parts."""
    parts = cr_label.split("-")
    if len(parts) != 2:
        raise ValueError("Invalid format. Expected 'Q31-Q29'.")
    left = parts[0][1:] if parts[0].startswith("Q") else parts[0]
    right = parts[1][1:] if parts[1].startswith("Q") else parts[1]
    return str(int(left)), str(int(right))


class DeviceTopologyService:
    """Service for building and filtering quantum device topologies."""

    def __init__(
        self,
        chip_repository: ChipRepository,
        calibration_note_repository: CalibrationNoteRepository,
    ) -> None:
        self._chip_repo = chip_repository
        self._calibration_note_repo = calibration_note_repository

    def build_device_topology(
        self,
        project_id: str,
        request: DeviceTopologyRequest,
    ) -> Device:
        """Build a filtered device topology from calibration data.

        Parameters
        ----------
        project_id : str
            Project ID for scoping
        request : DeviceTopologyRequest
            Request with qubit list, conditions, and exclusions

        Returns
        -------
        Device
            Filtered device topology

        """
        latest = self._calibration_note_repo.find_latest_master_by_project(project_id=project_id)
        if latest is None:
            raise ValueError(f"No master calibration note found for project {project_id}")

        cr_params = latest.note["cr_params"]
        drag_hpi_params = latest.note["drag_hpi_params"]
        drag_pi_params = latest.note["drag_pi_params"]

        chip_model = self._chip_repo.get_current_chip(username=latest.username)
        if chip_model is None:
            raise ValueError(f"No chip found for user {latest.username}")

        qubit_models = self._chip_repo.get_all_qubit_models(project_id, chip_model.chip_id)
        coupling_models = self._chip_repo.get_all_coupling_models(project_id, chip_model.chip_id)

        topology = load_topology(chip_model.topology_id)
        sorted_physical_ids = sorted(request.qubits, key=lambda x: int(x))
        id_mapping = {pid: idx for idx, pid in enumerate(sorted_physical_ids)}

        qubits = self._build_qubits(
            request, qubit_models, topology, id_mapping, drag_hpi_params, drag_pi_params
        )
        couplings = self._build_couplings(request, cr_params, coupling_models, topology, id_mapping)

        filtered_qubits, filtered_couplings = self._apply_filters(qubits, couplings, request)

        return Device(
            name=request.name,
            device_id=request.device_id,
            qubits=filtered_qubits,
            couplings=filtered_couplings,
            calibrated_at=latest.timestamp or "",
        )

    def _build_qubits(
        self,
        request: DeviceTopologyRequest,
        qubit_models: dict[str, Any],
        topology: Any,
        id_mapping: dict[str, int],
        drag_hpi_params: dict[str, Any],
        drag_pi_params: dict[str, Any],
    ) -> list[Qubit]:
        """Build qubit list from calibration data."""
        qubits = []
        for qid in request.qubits:
            qubit_doc = qubit_models.get(qid)
            if qubit_doc is None:
                continue

            use_24h = request.condition.qubit_fidelity.is_within_24h
            x90_gate_fidelity = _get_value_within_24h_fallback(
                qubit_doc.data.get("x90_gate_fidelity", {}), use_24h, 0.25
            )
            t1 = _get_value_within_24h_fallback(qubit_doc.data.get("t1", {}), use_24h, 100.0)
            t2 = _get_value_within_24h_fallback(qubit_doc.data.get("t2_echo", {}), use_24h, 100.0)
            drag_hpi_duration = drag_hpi_params.get(
                qid_to_label(qid, topology.num_qubits), {"duration": 20}
            )["duration"]
            drag_pi_duration = drag_pi_params.get(
                qid_to_label(qid, topology.num_qubits), {"duration": 20}
            )["duration"]
            readout_fidelity_0 = _get_value_within_24h_fallback(
                qubit_doc.data.get("readout_fidelity_0", {}), use_24h, 0.25
            )
            readout_fidelity_1 = _get_value_within_24h_fallback(
                qubit_doc.data.get("readout_fidelity_1", {}), use_24h, 0.25
            )

            prob_meas1_prep0 = 1 - readout_fidelity_0
            prob_meas0_prep1 = 1 - readout_fidelity_1
            readout_fidelity = (readout_fidelity_0 + readout_fidelity_1) / 2
            readout_assignment_error = 1 - readout_fidelity

            qubit_pos = topology.qubits[int(qid)]
            qubits.append(
                Qubit(
                    id=id_mapping[qid],
                    physical_id=int(qid),
                    position=Position(
                        x=qubit_pos.col * POSITION_SCALE / POSITION_DIVISOR,
                        y=-1 * qubit_pos.row * POSITION_SCALE / POSITION_DIVISOR,
                    ),
                    fidelity=x90_gate_fidelity,
                    meas_error=MeasError(
                        prob_meas1_prep0=prob_meas1_prep0,
                        prob_meas0_prep1=prob_meas0_prep1,
                        readout_assignment_error=readout_assignment_error,
                    ),
                    qubit_lifetime=QubitLifetime(t1=t1, t2=t2),
                    gate_duration=QubitGateDuration(rz=0, sx=drag_hpi_duration, x=drag_pi_duration),
                )
            )

        # Normalize positions
        if qubits:
            min_x = min(q.position.x for q in qubits)
            min_y = min(q.position.y for q in qubits)
            for qubit in qubits:
                qubit.position.x -= min_x
                qubit.position.y -= min_y

        return qubits

    def _build_couplings(
        self,
        request: DeviceTopologyRequest,
        cr_params: dict[str, Any],
        coupling_models: dict[str, Any],
        topology: Any,
        id_mapping: dict[str, int],
    ) -> list[Coupling]:
        """Build coupling list from calibration data."""
        couplings = []
        for qid in request.qubits:
            search_result = _search_coupling_data_by_control_qid(
                cr_params, qid_to_label(qid, topology.num_qubits)
            )
            for cr_key, cr_value in search_result.items():
                control, target = _split_q_string(cr_key)
                cr_duration = cr_value.get("duration", 20)

                coupling_key = f"{control}-{target}"
                coupling_doc = coupling_models.get(coupling_key)
                coupling_data = (
                    coupling_doc.data.get("zx90_gate_fidelity", {}) if coupling_doc else {}
                )
                zx90_gate_fidelity = _get_value_within_24h_fallback(
                    coupling_data,
                    request.condition.coupling_fidelity.is_within_24h,
                    fallback=0.25,
                )

                if control in id_mapping and target in id_mapping:
                    current_coupling = _normalize_coupling_key(control, target)
                    excluded_couplings = {
                        _normalize_coupling_key(*c.split("-")) for c in request.exclude_couplings
                    }
                    if current_coupling not in excluded_couplings:
                        couplings.append(
                            Coupling(
                                control=id_mapping[control],
                                target=id_mapping[target],
                                fidelity=zx90_gate_fidelity,
                                gate_duration=CouplingGateDuration(rzx90=cr_duration),
                            )
                        )
        return couplings

    def _apply_filters(
        self,
        qubits: list[Qubit],
        couplings: list[Coupling],
        request: DeviceTopologyRequest,
    ) -> tuple[list[Qubit], list[Coupling]]:
        """Apply fidelity filters and optional largest-component extraction."""
        filtered_qubits = [
            q
            for q in qubits
            if request.condition.qubit_fidelity.min
            <= q.fidelity
            <= request.condition.qubit_fidelity.max
        ]
        filtered_qubits = [
            q
            for q in filtered_qubits
            if (
                request.condition.readout_fidelity.min
                <= 1 - q.meas_error.readout_assignment_error
                <= request.condition.readout_fidelity.max
            )
        ]
        valid_qubit_ids = {q.id for q in filtered_qubits}

        filtered_couplings = [
            c
            for c in couplings
            if (
                request.condition.coupling_fidelity.min
                <= c.fidelity
                <= request.condition.coupling_fidelity.max
                and c.control in valid_qubit_ids
                and c.target in valid_qubit_ids
            )
        ]

        if request.condition.only_maximum_connected:
            g = nx.Graph()
            for c in filtered_couplings:
                g.add_edge(c.control, c.target)
            components = list(nx.connected_components(g))
            if components:
                largest_component = max(components, key=len)
                filtered_qubits = [q for q in filtered_qubits if q.id in largest_component]
                filtered_couplings = [
                    c
                    for c in filtered_couplings
                    if c.control in largest_component and c.target in largest_component
                ]

        # Re-index IDs sequentially
        new_id_mapping = {q.id: i for i, q in enumerate(filtered_qubits)}
        for q in filtered_qubits:
            q.id = new_id_mapping[q.id]
        for c in filtered_couplings:
            c.control = new_id_mapping[c.control]
            c.target = new_id_mapping[c.target]

        return filtered_qubits, filtered_couplings

    @staticmethod
    def generate_plot(data: dict[str, Any]) -> bytes:
        """Generate a plot of the quantum device and return it as bytes."""
        g = nx.Graph()
        pos = {}
        for qubit in data["qubits"]:
            g.add_node(qubit["id"], physical_id=qubit["physical_id"], fidelity=qubit["fidelity"])
            pos[qubit["id"]] = (qubit["position"]["x"] * 100, qubit["position"]["y"] * 100)

        for coupling in data["couplings"]:
            g.add_edge(
                coupling["control"],
                coupling["target"],
                fidelity=coupling["fidelity"],
                gate_duration=coupling["gate_duration"]["rzx90"],
            )

        plt.rcParams["font.size"] = 14
        plt.rcParams["font.family"] = "sans-serif"

        fig, ax = plt.subplots(figsize=(15, 15))
        nx.draw_networkx_nodes(
            g,
            pos,
            node_color=[g.nodes[node]["fidelity"] for node in g.nodes],
            node_size=3000,
            cmap="viridis",
        )
        nx.draw_networkx_edges(g, pos, width=3)

        labels = {
            node: f"Q{g.nodes[node]['physical_id']}\n{g.nodes[node]['fidelity']*100:.2f}%"
            for node in g.nodes
        }
        nx.draw_networkx_labels(
            g, pos, labels, font_size=12, font_weight="bold", font_color="white"
        )

        edge_labels = nx.get_edge_attributes(g, "fidelity")
        edge_labels = {k: f"F={v:.2f}" for k, v in edge_labels.items()}
        nx.draw_networkx_edge_labels(g, pos, edge_labels, font_size=10, label_pos=0.3)

        qubit_number = len(g.nodes)
        coupling_number = len(g.edges)

        fidelity_values = list(nx.get_node_attributes(g, "fidelity").values())
        vmin, vmax = (min(fidelity_values), max(fidelity_values)) if fidelity_values else (0, 1)
        sm = plt.cm.ScalarMappable(cmap="viridis", norm=mcolors.Normalize(vmin=vmin, vmax=vmax))
        cbar = plt.colorbar(sm, ax=ax, label="Qubit Fidelity (%)", fraction=0.046, pad=0.04)
        cbar.ax.tick_params(labelsize=12)

        title = (
            f"Quantum Device: {data['name'].upper()}, "
            f"qubit: {qubit_number}, coupling: {coupling_number}"
        )
        ax.set_title(
            title,
            pad=20,
            fontsize=16,
            fontweight="bold",
        )

        if pos:
            x_coords = [coord[0] for coord in pos.values()]
            y_coords = [coord[1] for coord in pos.values()]
            margin = 50
            ax.set_xlim(min(x_coords) - margin, max(x_coords) + margin)
            ax.set_ylim(min(y_coords) - margin, max(y_coords) + margin)
        ax.axis("off")
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", bbox_inches="tight", dpi=300)
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()
