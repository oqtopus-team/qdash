"""Coupling initialization module."""

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
            best_data={},
            system_info={},
        )
        for edge in edges
    ]


def init_coupling_document() -> None:
    """Initialize coupling documents."""
    # init_chip_document initializes the chip document which includes couplings
