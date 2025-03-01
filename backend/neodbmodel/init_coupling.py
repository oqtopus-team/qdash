from datamodel.coupling import EdgeInfoModel
from neodbmodel.coupling import CouplingDocument
from neodbmodel.init_qubit import qubit_lattice
from neodbmodel.initialize import initialize


def bi_direction(edges: list) -> list:
    """Bi-directional edges."""
    return edges + [(j, i) for i, j in edges]


def generate_coupling(edges: list) -> list:
    """Generate coupling documents from edges.

    Args:
    ----
        edges (list): List of edges.

    Returns:
    -------
        list: List of CouplingDocument objects.

    """
    return [
        CouplingDocument(
            username="admin",
            qid=f"{edge[0]}-{edge[1]}",
            status="pending",
            chip_id="SAMPLE",
            data={},
            edge_info=EdgeInfoModel(size=4, fill="", source=f"{edge[0]}", target=f"{edge[1]}"),
            system_info={},
        )
        for edge in edges
    ]


def init_coupling() -> None:
    """Initialize coupling documents."""
    _, edges, _ = qubit_lattice(n=64, d=4)
    edges = bi_direction(edges)
    couplings = generate_coupling(edges)
    for c in couplings:
        c.insert()


if __name__ == "__main__":
    initialize()
    init_coupling()
