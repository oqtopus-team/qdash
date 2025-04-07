import io
import re
from datetime import datetime, timezone
from typing import Annotated

import matplotlib.pyplot as plt
import networkx as nx
from fastapi import APIRouter, Depends
from fastapi.logger import logger
from fastapi.responses import Response
from pydantic import BaseModel
from qdash.api.lib.auth import get_current_active_user
from qdash.api.schemas.auth import User
from qdash.dbmodel.calibration_note import CalibrationNoteDocument
from qdash.dbmodel.chip import ChipDocument

router = APIRouter()


class Position(BaseModel):
    """Position of the qubit on the device."""

    x: float
    y: float


class MeasError(BaseModel):
    """Measurement error of the qubit."""

    prob_meas1_prep0: float
    prob_meas0_prep1: float
    readout_assignment_error: float


class QubitLifetime(BaseModel):
    """Qubit lifetime of the qubit."""

    t1: float
    t2: float


class QubitGateDuration(BaseModel):
    """Gate duration of the qubit."""

    rz: int
    sx: int
    x: int


class Qubit(BaseModel):
    """Qubit information."""

    id: int
    physical_id: int
    position: Position
    fidelity: float
    meas_error: MeasError
    qubit_lifetime: QubitLifetime
    gate_duration: QubitGateDuration


class CouplingGateDuration(BaseModel):
    """Gate duration of the coupling."""

    rzx90: int


class Coupling(BaseModel):
    """Coupling information."""

    control: int
    target: int
    fidelity: float
    gate_duration: CouplingGateDuration


class Device(BaseModel):
    """Device information."""

    name: str
    device_id: str
    qubits: list[Qubit]
    couplings: list[Coupling]
    calibrated_at: datetime


def search_coupling_data_by_control_qid(cr_params: dict, search_term: str) -> dict:
    """Search for coupling data by control qubit id."""
    filtered = {}
    for key, value in cr_params.items():
        # キーが '-' を含む場合は、左側を抽出
        left_side = key.split("-")[0] if "-" in key else key
        if left_side == search_term:
            filtered[key] = value
    return filtered


def qid_to_label(qid: str) -> str:
    """Convert a numeric qid string to a label with at least two digits. e.g. '0' -> 'Q00'."""
    if re.fullmatch(r"\d+", qid):
        return "Q" + qid.zfill(2)
    error_message = "Invalid qid format."
    raise ValueError(error_message)


def normalize_coupling_key(control: str, target: str) -> str:
    """Normalize coupling key by sorting the qubits.

    This ensures that "0-1" and "1-0" are treated as the same coupling.
    """
    qubits = sorted([control, target])
    return f"{qubits[0]}-{qubits[1]}"


def split_q_string(cr_label: str) -> tuple[str, str]:
    """Split a string of the form "Q31-Q29" into two parts.

    Args:
    ----
        cr_label (str): "Q31-Q29" string.

    Returns:
    -------
        tuple: example ("31", "29") or ("4", "5") if the string is in the correct format.
               Leading zeros are removed.

    Raises:
    ------
        ValueError: If the input string is not in the correct format.

    """
    parts = cr_label.split("-")
    expected_parts_count = 2
    error_message = "Invalid format. Expected 'Q31-Q29' or 'Q31-Q29'."
    if len(parts) != expected_parts_count:
        raise ValueError(error_message)

    # Remove the leading 'Q' if present and convert to integer to remove leading zeros
    left = parts[0][1:] if parts[0].startswith("Q") else parts[0]
    right = parts[1][1:] if parts[1].startswith("Q") else parts[1]

    # Convert to integer to remove leading zeros, then back to string
    left = str(int(left))
    right = str(int(right))

    return left, right


class DeviceTopologyRequst(BaseModel):
    """Request model for device topology."""

    name: str = "anemone"
    device_id: str = "anemone"
    qubits: list[str] = ["0", "1", "2", "3", "4", "5"]
    exclude_couplings: list[str] = []


@router.post(
    "/device_topology",
    response_model=Device,
    summary="Get the device topology",
    description="Get the device topology.",
    operation_id="getDeviceTopology",
)
def get_device_topology(
    current_user: Annotated[User, Depends(get_current_active_user)],
    request: DeviceTopologyRequst,
) -> Device:
    """Get the device topology."""
    logger.info(f"current user: {current_user.username}")
    qubits = []
    couplings = []
    latest = (
        CalibrationNoteDocument.find({"task_id": "master"}).sort([("timestamp", -1)]).limit(1).run()
    )[0]
    cr_params = latest.note["cr_params"]
    drag_hpi_params = latest.note["drag_hpi_params"]
    drag_pi_params = latest.note["drag_pi_params"]
    chip_docs = ChipDocument.find_one({"chip_id": "64Q", "username": latest.username}).run()
    # Sort physical qubit indices and create id mapping
    sorted_physical_ids = sorted(request.qubits)
    id_mapping = {pid: idx for idx, pid in enumerate(sorted_physical_ids)}
    logger.info(f"id_mapping: {id_mapping}")

    for qid in request.qubits:
        x90_gate_fidelity = (chip_docs.qubits[qid].data.get("x90_gate_fidelity") or {"value": 0.5})[
            "value"
        ]
        t1 = (chip_docs.qubits[qid].data.get("t1") or {"value": 100.0})["value"]
        t2 = (chip_docs.qubits[qid].data.get("t2_echo") or {"value": 100.0})["value"]
        drag_hpi_duration = drag_hpi_params.get(qid_to_label(qid), {"duration": 20})["duration"]
        drag_pi_duration = drag_pi_params.get(qid_to_label(qid), {"duration": 20})["duration"]
        readout_fidelity_0 = (
            chip_docs.qubits[qid].data.get("readout_fidelity_0") or {"value": 0.5}
        )["value"]
        readout_fidelity_1 = (
            chip_docs.qubits[qid].data.get("readout_fidelity_1") or {"value": 0.5}
        )["value"]
        # Calculate readout assignment error
        prob_meas1_prep0 = 1 - readout_fidelity_0
        prob_meas0_prep1 = 1 - readout_fidelity_1
        # Calculate readout assignment error
        readout_assignment_error = 1 - (readout_fidelity_0 + readout_fidelity_1) / 2

        qubits.append(
            Qubit(
                id=id_mapping[qid],  # Map to new sequential id
                physical_id=int(qid),
                position=Position(
                    x=chip_docs.qubits[qid].node_info.position.x,
                    y=chip_docs.qubits[qid].node_info.position.y,
                ),
                fidelity=x90_gate_fidelity,
                meas_error=MeasError(
                    prob_meas1_prep0=prob_meas1_prep0,
                    prob_meas0_prep1=prob_meas0_prep1,
                    readout_assignment_error=readout_assignment_error,
                ),
                qubit_lifetime=QubitLifetime(
                    t1=t1,
                    t2=t2,
                ),
                gate_duration=QubitGateDuration(
                    rz=0,
                    sx=drag_hpi_duration,
                    x=drag_pi_duration,
                ),
            )
        )

    # Adjust positions to make (min_x, min_y) the origin while maintaining relative positions
    min_x = min(qubit.position.x for qubit in qubits)
    min_y = min(qubit.position.y for qubit in qubits)

    # Update positions
    for qubit in qubits:
        qubit.position.x -= min_x
        qubit.position.y -= min_y

    # Process couplings
    for qid in request.qubits:
        search_result = search_coupling_data_by_control_qid(cr_params, qid_to_label(qid))
        for cr_key, cr_value in search_result.items():
            target = cr_value["target"]
            control, target = split_q_string(cr_key)
            cr_duration = cr_value.get("duration", 20)
            zx90_gate_fidelity = (
                chip_docs.couplings[f"{control}-{target}"].data.get("zx90_gate_fidelity")
                or {"value": 0.5}
            )["value"]
            # Only append if both control and target qubits exist in id_mapping and coupling is not excluded
            if control in id_mapping and target in id_mapping:
                # Normalize both the current coupling key and all excluded couplings
                current_coupling = normalize_coupling_key(control, target)
                excluded_couplings = {
                    normalize_coupling_key(*coupling.split("-"))
                    for coupling in request.exclude_couplings
                }

                if current_coupling not in excluded_couplings:
                    couplings.append(
                        Coupling(
                            control=id_mapping[control],  # Map to new sequential id
                            target=id_mapping[target],  # Map to new sequential id
                            fidelity=zx90_gate_fidelity,
                            gate_duration=CouplingGateDuration(rzx90=cr_duration),
                        )
                    )
    return Device(
        name=request.name,
        device_id=request.device_id,
        qubits=qubits,
        couplings=couplings,
        calibrated_at=datetime.now(tz=timezone.utc),
    )


def generate_device_plot(data: dict) -> bytes:
    """Generate a plot of the quantum device and return it as bytes."""
    # Create a new graph
    G = nx.Graph()

    # Add nodes (qubits) with their positions
    pos = {}
    for qubit in data["qubits"]:
        G.add_node(qubit["id"], physical_id=qubit["physical_id"], fidelity=qubit["fidelity"])
        pos[qubit["id"]] = (qubit["position"]["x"], qubit["position"]["y"])

    # Add edges (couplings)
    for coupling in data["couplings"]:
        G.add_edge(
            coupling["control"],
            coupling["target"],
            fidelity=coupling["fidelity"],
            gate_duration=coupling["gate_duration"]["rzx90"],
        )

    # Set font parameters
    plt.rcParams["font.size"] = 14
    plt.rcParams["font.family"] = "sans-serif"

    # Create the plot with a specific layout for colorbar
    fig, ax = plt.subplots(figsize=(10, 10))

    # Draw nodes
    nx.draw_networkx_nodes(
        G,
        pos,
        node_color=[G.nodes[node]["fidelity"] for node in G.nodes],
        node_size=3000,
        cmap="viridis",
    )

    # Draw edges
    nx.draw_networkx_edges(G, pos, width=3)

    # Add physical ID and fidelity labels in white
    labels = {
        node: f"Q{G.nodes[node]['physical_id']}\n{G.nodes[node]['fidelity']*100:.2f}%"
        for node in G.nodes
    }
    nx.draw_networkx_labels(G, pos, labels, font_size=12, font_weight="bold", font_color="white")

    # Add edge labels with adjusted position
    edge_labels = nx.get_edge_attributes(G, "fidelity")
    edge_labels = {k: f"F={v:.2f}" for k, v in edge_labels.items()}
    nx.draw_networkx_edge_labels(G, pos, edge_labels, font_size=10, label_pos=0.3)

    # Add a colorbar with adjusted position
    sm = plt.cm.ScalarMappable(
        cmap="viridis",
        norm=plt.Normalize(
            vmin=min(nx.get_node_attributes(G, "fidelity").values()),
            vmax=max(nx.get_node_attributes(G, "fidelity").values()),
        ),
    )
    cbar = plt.colorbar(sm, ax=ax, label="Qubit Fidelity (%)", fraction=0.046, pad=0.04)
    cbar.ax.tick_params(labelsize=12)

    ax.set_title(
        f"Quantum Device: {data['name'].upper()}",
        pad=20,
        fontsize=16,
        fontweight="bold",
    )

    # Adjust the plot limits with margins
    x_coords = [coord[0] for coord in pos.values()]
    y_coords = [coord[1] for coord in pos.values()]
    x_min, x_max = min(x_coords), max(x_coords)
    y_min, y_max = min(y_coords), max(y_coords)
    margin = 50  # Add margin to prevent cutoff

    ax.set_xlim(x_min - margin, x_max + margin)
    ax.set_ylim(y_min - margin, y_max + margin)
    ax.axis("off")  # Hide axes
    plt.tight_layout()

    # Save plot to bytes
    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", dpi=300)
    plt.close(fig)  # Close the figure to free memory
    buf.seek(0)
    return buf.getvalue()


@router.post(
    "/device_topology/plot",
    response_class=Response,
    summary="Get the device topology plot",
    description="Get the device topology as a PNG image.",
    operation_id="getDeviceTopologyPlot",
)
def get_device_topology_plot(
    current_user: Annotated[User, Depends(get_current_active_user)],
    device: Device,
) -> Response:
    """Get the device topology as a PNG image.

    Args:
    ----
        current_user: Authenticated user
        device: Device topology data

    Returns:
    -------
        Response: PNG image of the device topology

    """
    logger.info(f"current user: {current_user.username}")
    plot_bytes = generate_device_plot(device.model_dump())
    return Response(content=plot_bytes, media_type="image/png")
