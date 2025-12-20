"""Device topology router for QDash API."""

import io
import re
from typing import Annotated, Any

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import networkx as nx
import pendulum
from fastapi import APIRouter, Depends
from fastapi.logger import logger
from fastapi.responses import Response
from qdash.api.lib.project import ProjectContext, get_project_context
from qdash.api.lib.topology_config import load_topology
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
from qdash.repository import MongoCalibrationNoteRepository, MongoChipRepository

router = APIRouter()

# Constants for position calculation
POSITION_SCALE = 50  # Grid spacing used in topology
POSITION_DIVISOR = 30  # Divisor for final position


def search_coupling_data_by_control_qid(
    cr_params: dict[str, Any], search_term: str
) -> dict[str, Any]:
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


def is_within_24h(calibrated_at: str | None) -> bool:
    """Check if the calibrated timestamp is within 24 hours.

    Args:
    ----
        calibrated_at: Timestamp string to check

    Returns:
    -------
        bool: True if within 24 hours, False otherwise

    """
    if not calibrated_at:
        return False
    try:
        now = pendulum.now(tz="Asia/Tokyo")
        cutoff = now.subtract(hours=24)
        calibrated_at_dt = pendulum.parse(calibrated_at, tz="Asia/Tokyo")
        if not isinstance(calibrated_at_dt, pendulum.DateTime):
            return False
        return bool(calibrated_at_dt >= cutoff)
    except Exception:
        return False


def get_value_within_24h_fallback(
    data: dict[str, Any],
    use_24h: bool,
    fallback: float,
) -> float:
    """Get calibrated value based on whether it was calibrated within 24h.

    If `use_24h` is True:
        - If data is within 24h: return value
        - Else: return fallback (strict mode)

    If `use_24h` is False:
        - If value exists: return value (regardless of age)
        - Else: return fallback
    """
    value = data.get("value")
    calibrated_at = data.get("calibrated_at")

    if value is None:
        return fallback

    if use_24h:
        return float(value) if is_within_24h(calibrated_at) else fallback

    return float(value)


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


@router.post(
    "/device-topology",
    response_model=Device,
    summary="Get the device topology",
    description="Get the device topology.",
    operation_id="getDeviceTopology",
)
def get_device_topology(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    request: DeviceTopologyRequest,
) -> Device:
    """Get the quantum device topology with filtered qubits and couplings.

    Constructs a device topology based on calibration data, applying filters
    for qubit/coupling fidelity thresholds and optional time windows. Can
    optionally return only the largest connected component of the device.

    Parameters
    ----------
    ctx : ProjectContext
        Project context with user and project information
    request : DeviceTopologyRequest
        Request containing qubit list, device name/id, filtering conditions,
        and optional list of couplings to exclude

    Returns
    -------
    Device
        Device topology containing filtered qubits with positions, fidelities,
        lifetimes, gate durations, and couplings with their fidelities

    """
    logger.info(f"project: {ctx.project_id}, user: {ctx.user.username}")
    qubits = []
    couplings = []
    calibration_note_repo = MongoCalibrationNoteRepository()
    chip_repo = MongoChipRepository()

    latest = calibration_note_repo.find_latest_master_by_project(project_id=ctx.project_id)
    if latest is None:
        raise ValueError(f"No master calibration note found for project {ctx.project_id}")

    cr_params = latest.note["cr_params"]
    drag_hpi_params = latest.note["drag_hpi_params"]
    drag_pi_params = latest.note["drag_pi_params"]

    chip_model = chip_repo.get_current_chip(username=latest.username)
    if chip_model is None:
        raise ValueError(f"No chip found for user {latest.username}")
    # Load topology config for position calculation
    topology = load_topology(chip_model.topology_id)
    # Sort physical qubit indices and create id mapping
    sorted_physical_ids = sorted(request.qubits, key=lambda x: int(x))
    id_mapping = {pid: idx for idx, pid in enumerate(sorted_physical_ids)}
    logger.info(f"id_mapping: {id_mapping}")

    for qid in request.qubits:
        # Get qubit data with timestamp checks
        x90_data = chip_model.qubits[qid].data.get("x90_gate_fidelity", {})
        t1_data = chip_model.qubits[qid].data.get("t1", {})
        t2_data = chip_model.qubits[qid].data.get("t2_echo", {})
        readout_0_data = chip_model.qubits[qid].data.get("readout_fidelity_0", {})
        readout_1_data = chip_model.qubits[qid].data.get("readout_fidelity_1", {})

        x90_gate_fidelity = get_value_within_24h_fallback(
            x90_data, request.condition.qubit_fidelity.is_within_24h, fallback=0.25
        )
        # t1 = t1_data["value"] if is_within_24h(t1_data.get("calibrated_at")) else 100.0
        t1 = get_value_within_24h_fallback(
            t1_data, request.condition.qubit_fidelity.is_within_24h, fallback=100.0
        )
        # t2 = t2_data["value"] if is_within_24h(t2_data.get("calibrated_at")) else 100.0
        t2 = get_value_within_24h_fallback(
            t2_data, request.condition.qubit_fidelity.is_within_24h, fallback=100.0
        )
        drag_hpi_duration = drag_hpi_params.get(qid_to_label(qid), {"duration": 20})["duration"]
        drag_pi_duration = drag_pi_params.get(qid_to_label(qid), {"duration": 20})["duration"]
        # readout_fidelity_0 = (
        #     readout_0_data["value"] if is_within_24h(readout_0_data.get("calibrated_at")) else 0.25
        # )
        readout_fidelity_0 = get_value_within_24h_fallback(
            readout_0_data, request.condition.qubit_fidelity.is_within_24h, fallback=0.25
        )
        # readout_fidelity_1 = (
        #     readout_1_data["value"] if is_within_24h(readout_1_data.get("calibrated_at")) else 0.25
        # )
        readout_fidelity_1 = get_value_within_24h_fallback(
            readout_1_data, request.condition.qubit_fidelity.is_within_24h, fallback=0.25
        )
        # Calculate readout assignment error
        prob_meas1_prep0 = 1 - readout_fidelity_0
        prob_meas0_prep1 = 1 - readout_fidelity_1
        # Calculate readout assignment error
        readout_fidelity = (readout_fidelity_0 + readout_fidelity_1) / 2
        readout_assignment_error = 1 - readout_fidelity
        # Calculate position from topology config
        qubit_pos = topology.qubits[int(qid)]
        qubits.append(
            Qubit(
                id=id_mapping[qid],  # Map to new sequential id
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
            # Get coupling fidelity data with timestamp check
            coupling_data = chip_model.couplings[f"{control}-{target}"].data.get(
                "zx90_gate_fidelity", {}
            )
            # zx90_gate_fidelity = (
            #     coupling_data["value"]
            #     if is_within_24h(coupling_data.get("calibrated_at"))
            #     else 0.25
            # )
            zx90_gate_fidelity = get_value_within_24h_fallback(
                coupling_data,
                request.condition.coupling_fidelity.is_within_24h,
                fallback=0.25,
            )
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
    # Filter couplings based on fidelity threshold
    # filtered_couplings = [
    #     coupling for coupling in couplings if coupling.fidelity >= 0.7 and coupling.fidelity < 1.0
    # ]
    # First filter qubits based on fidelity
    filtered_qubits = [
        qubit
        for qubit in qubits
        if (
            request.condition.qubit_fidelity.min
            <= qubit.fidelity
            <= request.condition.qubit_fidelity.max
        )
    ]

    filtered_qubits = [
        qubit
        for qubit in filtered_qubits
        if (
            request.condition.readout_fidelity.min
            <= 1 - qubit.meas_error.readout_assignment_error
            <= request.condition.readout_fidelity.max
        )
    ]
    # Get set of qubit IDs that passed the fidelity filter
    valid_qubit_ids = {qubit.id for qubit in filtered_qubits}

    # Filter couplings based on both coupling fidelity and connected qubit fidelity
    filtered_couplings = [
        coupling
        for coupling in couplings
        if (
            request.condition.coupling_fidelity.min
            <= coupling.fidelity
            <= request.condition.coupling_fidelity.max
            and coupling.control in valid_qubit_ids
            and coupling.target in valid_qubit_ids
        )
    ]

    if request.condition.only_maximum_connected:
        # Create a graph to find the largest connected component
        g = nx.Graph()
        for coupling in filtered_couplings:
            g.add_edge(coupling.control, coupling.target)

        if g.edges:  # Only find largest component if there are any edges
            # Find the largest connected component
            largest_component = max(nx.connected_components(g), key=len)

            # Filter qubits and couplings to keep only those in the largest component
            filtered_qubits = [qubit for qubit in filtered_qubits if qubit.id in largest_component]
            filtered_couplings = [
                coupling
                for coupling in filtered_couplings
                if coupling.control in largest_component and coupling.target in largest_component
            ]
    # Create new sequential IDs starting from 0
    new_id_mapping = {qubit.id: i for i, qubit in enumerate(filtered_qubits)}

    # Update qubit IDs
    for qubit in filtered_qubits:
        qubit.id = new_id_mapping[qubit.id]

    # Update coupling IDs to match new qubit IDs
    for coupling in filtered_couplings:
        coupling.control = new_id_mapping[coupling.control]
        coupling.target = new_id_mapping[coupling.target]

    return Device(
        name=request.name,
        device_id=request.device_id,
        qubits=filtered_qubits,
        couplings=filtered_couplings,
        calibrated_at=latest.timestamp or "",
    )


def generate_device_plot(data: dict[str, Any]) -> bytes:
    """Generate a plot of the quantum device and return it as bytes."""
    # Create a new graph
    g = nx.Graph()

    # Add nodes (qubits) with their positions
    pos = {}
    for qubit in data["qubits"]:
        g.add_node(qubit["id"], physical_id=qubit["physical_id"], fidelity=qubit["fidelity"])
        pos[qubit["id"]] = (qubit["position"]["x"] * 100, qubit["position"]["y"] * 100)

    # Add edges (couplings)
    for coupling in data["couplings"]:
        g.add_edge(
            coupling["control"],
            coupling["target"],
            fidelity=coupling["fidelity"],
            gate_duration=coupling["gate_duration"]["rzx90"],
        )

    # Set font parameters
    plt.rcParams["font.size"] = 14
    plt.rcParams["font.family"] = "sans-serif"

    # Create the plot with a specific layout for colorbar
    fig, ax = plt.subplots(figsize=(15, 15))

    # Draw nodes
    nx.draw_networkx_nodes(
        g,
        pos,
        node_color=[g.nodes[node]["fidelity"] for node in g.nodes],
        node_size=3000,
        cmap="viridis",
    )

    # Draw edges
    nx.draw_networkx_edges(g, pos, width=3)

    # Add physical ID and fidelity labels in white
    labels = {
        node: f"Q{g.nodes[node]['physical_id']}\n{g.nodes[node]['fidelity']*100:.2f}%"
        for node in g.nodes
    }
    nx.draw_networkx_labels(g, pos, labels, font_size=12, font_weight="bold", font_color="white")

    # Add edge labels with adjusted position
    edge_labels = nx.get_edge_attributes(g, "fidelity")
    edge_labels = {k: f"F={v:.2f}" for k, v in edge_labels.items()}
    nx.draw_networkx_edge_labels(g, pos, edge_labels, font_size=10, label_pos=0.3)

    # Add a colorbar with adjusted position
    qubit_number = len(g.nodes)
    copuling_number = len(g.edges)
    logger.info(f"Qubit number: {qubit_number}, Coupling number: {copuling_number}")
    # ax.text(
    #     0.5,
    #     0.99,
    #     f"Qubit: {qubit_number}, Coupling: {copuling_number}",
    #     transform=ax.transAxes,
    #     ha="center",
    #     fontsize=12,
    #     fontweight="bold",
    # )
    sm = plt.cm.ScalarMappable(
        cmap="viridis",
        norm=mcolors.Normalize(
            vmin=min(nx.get_node_attributes(g, "fidelity").values()),
            vmax=max(nx.get_node_attributes(g, "fidelity").values()),
        ),
    )
    cbar = plt.colorbar(sm, ax=ax, label="Qubit Fidelity (%)", fraction=0.046, pad=0.04)
    cbar.ax.tick_params(labelsize=12)

    ax.set_title(
        f"Quantum Device: {data['name'].upper()}, qubit: {qubit_number}, coupling: {copuling_number}",
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
    "/device-topology/plot",
    response_class=Response,
    summary="Get the device topology plot",
    description="Get the device topology as a PNG image.",
    operation_id="getDeviceTopologyPlot",
)
def get_device_topology_plot(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    device: Device,
) -> Response:
    """Get the device topology as a PNG image.

    Args:
    ----
        ctx: Project context with user and project information
        device: Device topology data

    Returns:
    -------
        Response: PNG image of the device topology

    """
    logger.info(f"project: {ctx.project_id}, user: {ctx.user.username}")
    plot_bytes = generate_device_plot(device.model_dump())
    return Response(content=plot_bytes, media_type="image/png")
