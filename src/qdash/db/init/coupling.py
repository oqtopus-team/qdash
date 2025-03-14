"""Coupling initialization module."""

from qdash.datamodel.coupling import EdgeInfoModel
from qdash.db.init.initialize import initialize
from qdash.db.init.qubit import qubit_lattice
from qdash.dbmodel.coupling import CouplingDocument


def bi_direction(edges: list) -> list:
    """Bi-directional edges."""
    return edges + [(j, i) for i, j in edges]


def generate_coupling(edges: list, username: str, chip_id: str) -> list:
    """Generate coupling documents from edges.

    Args:
    ----
        edges (list): List of edges.
        username (str): Username.
        chip_id (str): Chip ID.

    Returns:
    -------
        list: List of CouplingDocument objects.

    """
    return [
        CouplingDocument(
            username=username,
            qid=f"{edge[0]}-{edge[1]}",
            status="pending",
            chip_id=chip_id,
            data={},
            edge_info=EdgeInfoModel(size=4, fill="", source=f"{edge[0]}", target=f"{edge[1]}"),
            system_info={},
        )
        for edge in edges
    ]


def init_coupling_document(username: str, chip_id: str) -> None:
    """Initialize coupling documents."""
    initialize()
    _, edges, _ = qubit_lattice(n=64, d=4)
    edges = bi_direction(edges)
    couplings = generate_coupling(edges, username=username, chip_id=chip_id)
    for c in couplings:
        c.insert()
