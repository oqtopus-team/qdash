"""Qubit initialization module."""

from qdash.dbmodel.initialize import initialize
from qdash.dbmodel.qubit import QubitDocument


def qubit_lattice(n: int, d: int) -> tuple[range, list, dict]:
    """Generate qubit lattice structure for RQC square lattice."""

    def node(i: int, j: int, k: int) -> int:
        return 4 * (i * d + j) + k

    nodes = range(n)
    edges = []
    for i in range(d):
        for j in range(d):
            # inner - mux
            edges.append((node(i, j, 0), node(i, j, 1)))
            edges.append((node(i, j, 0), node(i, j, 2)))
            edges.append((node(i, j, 1), node(i, j, 3)))
            edges.append((node(i, j, 2), node(i, j, 3)))

            # inter - mux
            if i != d - 1:
                edges.append((node(i, j, 2), node(i + 1, j, 0)))
                edges.append((node(i, j, 3), node(i + 1, j, 1)))
            if j != d - 1:
                edges.append((node(i, j, 1), node(i, j + 1, 0)))
                edges.append((node(i, j, 3), node(i, j + 1, 2)))

    # 均等なグリッド配置
    pos = {}
    scale = 50  # spacing between nodes
    for i in range(d):
        for j in range(d):
            x_base = j * 2 * scale
            y_base = -i * 2 * scale
            pos[node(i, j, 0)] = (x_base, y_base)
            pos[node(i, j, 1)] = (x_base + scale, y_base)
            pos[node(i, j, 2)] = (x_base, y_base - scale)
            pos[node(i, j, 3)] = (x_base + scale, y_base - scale)

    return nodes, edges, pos


def correct(original: tuple, s: float) -> tuple:
    """Correct position coordinates.

    Args:
    ----
        original (tuple): Original coordinates
        s (float): Scale factor

    Returns:
    -------
        tuple: Corrected coordinates

    """
    offset = (1 / 3, 10 / 3)
    offset_applied = tuple(x + y for x, y in zip(original, offset, strict=False))
    return tuple(x * s for x in offset_applied)


def generate_dummy_data(num_qubits: int, pos: dict, username: str, chip_id: str) -> list:
    """Generate dummy qubit data.

    Args:
    ----
        num_qubits (int): Number of qubits
        pos (dict): Position dictionary
        username (str): Username
        chip_id (str): Chip ID

    Returns:
    -------
        list: List of QubitDocument objects

    """
    data = []
    for i in range(num_qubits):
        qubit_data = QubitDocument(
            username=username,
            chip_id=chip_id,
            qid=f"{i}",
            status="pending",
            data={},
            system_info={},
        )
        data.append(qubit_data)
    return data


def init_qubit_document(username: str, chip_id: str) -> None:
    """Initialize qubit documents."""
    initialize()
    num_qubits = 64
    nodes, edges, pos = qubit_lattice(64, 4)
    dummy_data = generate_dummy_data(num_qubits, pos, username=username, chip_id=chip_id)
    for data in dummy_data:
        data.insert()
