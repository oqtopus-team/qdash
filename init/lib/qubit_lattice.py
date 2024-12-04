def qubit_lattice(n, d):
    """generate qubit lattice structure for RQC square lattice
    Args:
        n (int): number of qubits
        d (int): number of mux in a line
    Returns:
        nodes (list): list of the node labels
        edges (list): list of the edge labels
        pos (dict): dictionary of the positions of the nodes for the visualization
    """

    def node(i, j, k):
        q = 4 * (i * d + j) + k
        return q

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

    pos = {}
    for i in range(d):
        for j in range(d):
            pos[node(i, j, 0)] = correct((j - 1 / 3, -i + 1 / 3), 100)
            pos[node(i, j, 1)] = correct((j + 1 / 3, -i + 1 / 3), 100)
            pos[node(i, j, 2)] = correct((j - 1 / 3, -i - 1 / 3), 100)
            pos[node(i, j, 3)] = correct((j + 1 / 3, -i - 1 / 3), 100)

    return nodes, edges, pos


def correct(original: tuple, s: float):
    offset = (1 / 3, 10 / 3)
    offset_applied = tuple(x + y for x, y in zip(original, offset))
    return tuple(x * s for x in offset_applied)
