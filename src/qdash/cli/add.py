import logging

from qdash.db.init.chip import generate_coupling_data, generate_qubit_data
from qdash.db.init.coupling import bi_direction, generate_coupling
from qdash.db.init.qubit import generate_dummy_data  # qubit_lattice
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.initialize import initialize

logging.basicConfig(level=logging.INFO)


CHIP_SIZE_64 = 64
CHIP_SIZE_144 = 144
CHIP_SIZE_256 = 256
CHIP_SIZE_1024 = 1024


def add_new_chip(
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
        qubits = generate_qubit_data(size, pos, chip_id)
        couplings = generate_coupling_data(edges, chip_id)
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
        for c in couplings:
            c.insert()
        logging.info(f"New chip added: {chip_id} for user: {username}")
    except Exception as e:
        logging.error(f"Error adding new chip: {e}")
        raise


def update_qubit_positions(
    username: str = "admin",
    chip_id: str = "64Q",
) -> None:
    """Update the qubit position in the database.

    This function updates the qubit position in the database for the given chip ID.

    Args:
    ----
        username (str): The username for the initialization.
        chip_id (str): The chip ID for the initialization.

    """
    try:
        # Initialize qubit data
        initialize()
        chip = ChipDocument.get_current_chip(username=username)
        if not chip:
            raise ValueError(f"Chip with ID {chip_id} not found for user {username}.")
        _, _, pos = qubit_lattice(chip.size, 4)
        for qubit in chip.qubits.values():
            i = int(qubit.qid)
            print(f"Updating position for qubit {qubit.qid} at index {i}")
            qubit.node_info.position.x = pos[i][0]
            qubit.node_info.position.y = pos[i][1]
        chip.save()
        logging.info(f"Qubit positions updated for chip ID: {chip_id} and user: {username}")
    except Exception as e:
        logging.error(f"Error updating qubit positions: {e}")
        raise


def qubit_lattice(
    n: int, d: int
) -> tuple[range, list[tuple[int, int]], dict[int, tuple[int, int]]]:
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


def correct(original: tuple[float, ...], s: float) -> tuple[float, ...]:
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
