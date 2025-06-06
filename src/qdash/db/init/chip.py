"""Chip initialization module."""

from qdash.datamodel.coupling import CouplingModel, EdgeInfoModel
from qdash.datamodel.qubit import NodeInfoModel, PositionModel, QubitModel
from qdash.db.init.coupling import bi_direction
from qdash.db.init.initialize import initialize
from qdash.db.init.qubit import qubit_lattice
from qdash.dbmodel.chip import ChipDocument


def generate_qubit_data(num_qubits: int, pos: dict, chip_id: str) -> dict:
    """Generate qubit data for the given number of qubits and positions.

    Args:
    ----
        num_qubits (int): Number of qubits.
        pos (dict): Dictionary of positions for each qubit.

    Returns:
    -------
        dict: Dictionary of qubit data.

    """
    qubits = {}
    for i in range(num_qubits):
        qubits[f"{i}"] = QubitModel(
            chip_id=chip_id,
            qid=f"{i}",
            status="pending",
            node_info=NodeInfoModel(
                position=PositionModel(
                    x=pos[i][0],
                    y=pos[i][1],
                ),
            ),
            data={},
            best_data={},
        )
    return qubits


def generate_coupling_data(edges: list[tuple[int, int]], chip_id: str) -> dict:
    """Generate coupling data for the given edges.

    Args:
    ----
        edges (list[tuple[int, int]]): List of edges represented as tuples of node indices.

    Returns:
    -------
        dict: Dictionary of coupling data.

    """
    edges = bi_direction(edges)
    coupling = {}
    for edge in edges:
        coupling[f"{edge[0]}-{edge[1]}"] = CouplingModel(
            qid=f"{edge[0]}-{edge[1]}",
            status="pending",
            chip_id=chip_id,
            data={},
            best_data={},
            edge_info=EdgeInfoModel(size=4, fill="", source=f"{edge[0]}", target=f"{edge[1]}"),
        )
    return coupling


def init_chip_document(username: str, chip_id: str) -> ChipDocument:
    """Initialize and return a ChipDocument."""
    initialize()
    num_qubits = 64
    _, edges, pos = qubit_lattice(64, 4)
    nodes, edges, pos = qubit_lattice(64, 4)
    qubits = generate_qubit_data(num_qubits, pos, chip_id)
    couplings = generate_coupling_data(edges, chip_id)
    chip = ChipDocument(
        username=username,
        chip_id=chip_id,
        size=64,
        qubits=qubits,
        couplings=couplings,
        system_info={},
    )
    chip.save()
    return chip
