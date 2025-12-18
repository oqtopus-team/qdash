"""Chip initialization module."""

from qdash.datamodel.coupling import CouplingModel
from qdash.datamodel.qubit import QubitModel
from qdash.db.init.coupling import bi_direction, generate_coupling
from qdash.db.init.qubit import (
    generate_dummy_data,  # qubit_lattice
    qubit_lattice,
)
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.initialize import initialize

CHIP_SIZE_64 = 64
CHIP_SIZE_144 = 144
CHIP_SIZE_256 = 256
CHIP_SIZE_1024 = 1024


def generate_qubit_data(
    num_qubits: int, pos: dict[int, tuple[int, int]], chip_id: str, username: str
) -> dict[str, QubitModel]:
    """Generate qubit data for the given number of qubits and positions.

    Args:
    ----
        num_qubits (int): Number of qubits.
        pos (dict): Dictionary of positions for each qubit (deprecated, kept for compatibility).
        chip_id (str): Chip ID.
        username (str): Username of the user creating the qubits.

    Returns:
    -------
        dict: Dictionary of qubit data.

    """
    qubits = {}
    for i in range(num_qubits):
        qubits[f"{i}"] = QubitModel(
            username=username,
            chip_id=chip_id,
            qid=f"{i}",
            status="pending",
            data={},
            best_data={},
        )
    return qubits


def generate_coupling_data(
    edges: list[tuple[int, int]], chip_id: str, username: str
) -> dict[str, CouplingModel]:
    """Generate coupling data for the given edges.

    Args:
    ----
        edges (list[tuple[int, int]]): List of edges represented as tuples of node indices.
        chip_id (str): Chip ID.
        username (str): Username of the user creating the couplings.

    Returns:
    -------
        dict: Dictionary of coupling data.

    """
    edges = bi_direction(edges)
    coupling = {}
    for edge in edges:
        coupling[f"{edge[0]}-{edge[1]}"] = CouplingModel(
            username=username,
            qid=f"{edge[0]}-{edge[1]}",
            status="pending",
            chip_id=chip_id,
            data={},
            best_data={},
        )
    return coupling


# def init_chip_document(username: str, chip_id: str) -> ChipDocument:
#     """Initialize and return a ChipDocument."""
#     initialize()
#     num_qubits = 64
#     _, edges, pos = qubit_lattice(64, 4)
#     nodes, edges, pos = qubit_lattice(64, 4)
#     qubits = generate_qubit_data(num_qubits, pos, chip_id, username=username)
#     couplings = generate_coupling_data(edges, chip_id, username=username)
#     chip = ChipDocument(
#         username=username,
#         chip_id=chip_id,
#         size=64,
#         qubits=qubits,
#         couplings=couplings,
#         system_info={},
#     )
#     chip.save()
#     return chip


def init_chip_document(
    username: str = "admin",
    chip_id: str = "64Q",
    size: int = CHIP_SIZE_64,
) -> None:
    """Add a new chip to the database.

    This function adds a new chip to the database by initializing the
    necessary data.

    Args:
    ----
        username (str): The username for the initialization.
        chip_id (str): The chip ID for the initialization.
        size (int): The size of the chip, either CHIP_SIZE_64 or CHIP_SIZE_144.

    """
    try:
        # Initialize chip data
        initialize()

        if size not in [CHIP_SIZE_64, CHIP_SIZE_144, CHIP_SIZE_256, CHIP_SIZE_1024]:
            msg = "Size must be either CHIP_SIZE_64 or CHIP_SIZE_144 or CHIP_SIZE_256."
            raise ValueError(msg)  # noqa: TRY301
        # Removed unused variable 'd'
        if size == CHIP_SIZE_64:
            d = 4
        elif size == CHIP_SIZE_144:
            d = 6
        elif size == CHIP_SIZE_256:
            d = 8
        elif size == CHIP_SIZE_1024:
            d = 16
        _, edges, pos = qubit_lattice(size, d)
        nodes, edges, pos = qubit_lattice(size, d)
        qubits = generate_qubit_data(size, pos, chip_id, username=username)
        couplings = generate_coupling_data(edges, chip_id, username=username)
        chip = ChipDocument(
            username=username,
            chip_id=chip_id,
            size=size,
            qubits=qubits,
            couplings=couplings,
            system_info={},
        )
        chip.save()
        ## Initialize qubit data
        nodes, edges, pos = qubit_lattice(size, d)
        dummy_data = generate_dummy_data(size, pos, username=username, chip_id=chip_id)
        for data in dummy_data:
            data.insert()
        ## Initialize coupling data
        _, edges, _ = qubit_lattice(size, d)
        edges = bi_direction(edges)
        couplings = generate_coupling(edges, username=username, chip_id=chip_id)
        for coupling in couplings:
            coupling.insert()  # type: ignore[attr-defined]
    except Exception:
        print("Error adding new chip:", chip_id)
        raise
