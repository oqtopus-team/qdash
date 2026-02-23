"""Utility functions for CR gate scheduling.

Pure functions extracted from CRScheduler for reuse by plugins and other modules.
These handle coordinate conversion, frequency extraction, MUX mapping, conflict
detection, and parallel grouping.
"""

from __future__ import annotations

import itertools
import logging
from collections import defaultdict
from typing import Any

import networkx as nx

logger = logging.getLogger(__name__)


def extract_qubit_frequency(qubits: dict[str, Any]) -> dict[str, float]:
    """Extract qubit frequencies from qubit models.

    Works with both QubitModel (embedded) and QubitDocument (individual collection).
    Both have .data attribute with calibration data.
    """
    return {
        qid: qubit.data["qubit_frequency"]["value"]
        for qid, qubit in qubits.items()
        if qubit.data and "qubit_frequency" in qubit.data
    }


def qid_to_coords(qid: int, grid_size: int) -> tuple[int, int]:
    """Convert qubit ID to (row, col) coordinates in the square lattice.

    Args:
        qid: Qubit ID (0-indexed)
        grid_size: Grid dimension (8 for 64-qubit, 12 for 144-qubit)

    Returns:
        (row, col) tuple representing position in the grid

    Example:
        For 64-qubit chip (8x8 grid):
        - qid=0 -> (0, 0) [MUX 0, position TL]
        - qid=1 -> (0, 1) [MUX 0, position TR]
        - qid=2 -> (1, 0) [MUX 0, position BL]
        - qid=16 -> (2, 0) [MUX 4, position TL]
    """
    # Which MUX does this qubit belong to?
    mux_id = qid // 4

    # Position within the MUX (0=TL, 1=TR, 2=BL, 3=BR)
    pos_in_mux = qid % 4

    # MUX grid dimension (N/2 x N/2)
    mux_grid_size = grid_size // 2

    # MUX position in MUX grid
    mux_row = mux_id // mux_grid_size
    mux_col = mux_id % mux_grid_size

    # Position within MUX (2x2 sub-grid)
    local_row = pos_in_mux // 2  # 0 (top) or 1 (bottom)
    local_col = pos_in_mux % 2  # 0 (left) or 1 (right)

    # Combine to get global position
    row = mux_row * 2 + local_row
    col = mux_col * 2 + local_col

    return (row, col)


def infer_direction_from_design(qid1: str, qid2: str, grid_size: int = 8) -> bool:
    """Infer CR gate direction from design-based frequency pattern.

    The chip follows a checkerboard frequency pattern where frequency is determined by
    coordinate parity. This allows inferring CR direction without actual frequency measurements.

    Design pattern (from docs/architecture/square-lattice-topology.md):
    - Low frequency (~8000 MHz): (row + col) % 2 == 0
    - High frequency (~9000 MHz): (row + col) % 2 == 1

    CR gate constraint: f_control < f_target

    Args:
        qid1: First qubit ID
        qid2: Second qubit ID
        grid_size: Grid dimension (8 for 64-qubit, 12 for 144-qubit, default: 8)

    Returns:
        True if qid1 should be control (qid1 has lower frequency by design),
        False otherwise

    Example:
        For 64-qubit chip:
        - qid1=0 -> (0,0) -> sum=0 (even) -> low freq
        - qid2=1 -> (0,1) -> sum=1 (odd) -> high freq
        - Result: True (0 is control, 1 is target)
    """
    r1, c1 = qid_to_coords(int(qid1), grid_size)
    r2, c2 = qid_to_coords(int(qid2), grid_size)

    # Checkerboard pattern: (row + col) % 2 determines frequency group
    # Even sum -> low frequency, Odd sum -> high frequency
    parity1 = (r1 + c1) % 2
    parity2 = (r2 + c2) % 2

    # CR constraint: control has lower frequency
    # parity=0 -> low freq, parity=1 -> high freq
    return parity1 < parity2


def build_mux_conflict_map(yaml_mux_list: list[dict[str, Any]]) -> dict[int, set[int]]:
    """Build conflict map for MUX resources.

    MUXes conflict if they share the same readout or control module.
    """
    module_to_muxes_readout: dict[str, set[int]] = defaultdict(set)
    module_to_muxes_ctrl: dict[str, set[int]] = defaultdict(set)

    # Group MUXes by readout and control modules
    for mux_entry in yaml_mux_list:
        mux_id = mux_entry["mux"]

        # Readout module conflicts
        read_out = mux_entry.get("read_out")
        if read_out:
            readout_module = read_out.split("-")[0]
            module_to_muxes_readout[readout_module].add(mux_id)

        # Control module conflicts
        for ctrl in mux_entry.get("ctrl", []):
            ctrl_module = ctrl.split("-")[0]
            module_to_muxes_ctrl[ctrl_module].add(mux_id)

    def create_conflict_map(module_to_muxes: dict[str, set[int]]) -> dict[int, set[int]]:
        """Create bidirectional conflict map from module groupings."""
        mux_conflict: dict[int, set[int]] = defaultdict(set)
        for muxes in module_to_muxes.values():
            for mux_a, mux_b in itertools.combinations(muxes, 2):
                mux_conflict[mux_a].add(mux_b)
                mux_conflict[mux_b].add(mux_a)
        return mux_conflict

    # Merge readout and control conflicts
    conflict_map = create_conflict_map(module_to_muxes_readout)
    ctrl_conflict_map = create_conflict_map(module_to_muxes_ctrl)

    for mux_id, conflicts in ctrl_conflict_map.items():
        conflict_map[mux_id].update(conflicts)

    return dict(conflict_map)


def build_qubit_to_mux_map(yaml_mux_list: list[dict[str, Any]]) -> dict[str, int]:
    """Build mapping from qubit ID to MUX ID.

    Each MUX controls 4 qubits: MUX_N controls qubits [4N, 4N+1, 4N+2, 4N+3].
    """
    qid_to_mux = {}
    for entry in yaml_mux_list:
        mux_id = entry["mux"]
        for offset in range(4):
            qid_to_mux[str(mux_id * 4 + offset)] = mux_id
    return qid_to_mux


def group_cr_pairs_by_conflict(
    cr_pairs: list[str],
    qid_to_mux: dict[str, int],
    mux_conflict_map: dict[int, set[int]],
    max_parallel_ops: int | None = None,
    coloring_strategy: str = "largest_first",
) -> list[list[str]]:
    """Group CR pairs into parallel execution steps using greedy graph coloring.

    Args:
        cr_pairs: List of CR pair strings (e.g., ["0-1", "2-3"])
        qid_to_mux: Mapping from qubit ID to MUX ID
        mux_conflict_map: MUX conflict relationships
        max_parallel_ops: Maximum parallel operations per group
        coloring_strategy: NetworkX graph coloring strategy. Options:
            - "largest_first": Largest degree first (default, good general performance)
            - "smallest_last": Smallest degree last (often better quality)
            - "random_sequential": Random order (non-deterministic)
            - "connected_sequential_bfs": BFS ordering
            - "connected_sequential_dfs": DFS ordering
            - "saturation_largest_first": DSATUR algorithm (often optimal)

    Returns:
        List of groups where each group contains CR pairs that can run in parallel
    """
    # Build conflict graph
    conflict_graph = nx.Graph()
    conflict_graph.add_nodes_from(cr_pairs)

    for pair_a, pair_b in itertools.combinations(cr_pairs, 2):
        q1a, q2a = pair_a.split("-")
        q1b, q2b = pair_b.split("-")

        # Conflict 1: Shared qubits
        if {q1a, q2a} & {q1b, q2b}:
            conflict_graph.add_edge(pair_a, pair_b)
            continue

        # Conflict 2: Same MUX usage
        mux_a1, mux_a2 = qid_to_mux[q1a], qid_to_mux[q2a]
        mux_b1, mux_b2 = qid_to_mux[q1b], qid_to_mux[q2b]

        if mux_a1 in (mux_b1, mux_b2) or mux_a2 in (mux_b1, mux_b2):
            conflict_graph.add_edge(pair_a, pair_b)
            continue

        # Conflict 3: MUX resource conflicts
        conflict_muxes = mux_conflict_map.get(mux_a1, set()) | mux_conflict_map.get(mux_a2, set())
        if mux_b1 in conflict_muxes or mux_b2 in conflict_muxes:
            conflict_graph.add_edge(pair_a, pair_b)

    # Greedy graph coloring
    coloring = nx.coloring.greedy_color(conflict_graph, strategy=coloring_strategy)

    # Group pairs by color
    color_groups: dict[int, list[str]] = defaultdict(list)
    for pair, color in coloring.items():
        color_groups[color].append(pair)

    # Convert to sorted list of groups
    groups = [color_groups[c] for c in sorted(color_groups)]

    # Optionally split groups that exceed max parallel operations limit
    if max_parallel_ops is not None:
        split_groups = []
        for group in groups:
            for i in range(0, len(group), max_parallel_ops):
                chunk = group[i : i + max_parallel_ops]
                split_groups.append(chunk)
        return split_groups

    return groups


def split_fast_slow_pairs(
    cr_pairs: list[str], qid_to_mux: dict[str, int]
) -> tuple[list[str], list[str]]:
    """Separate CR pairs into fast (intra-MUX) and slow (inter-MUX) categories."""
    fast_pairs = [
        p for p in cr_pairs if qid_to_mux.get(p.split("-")[0]) == qid_to_mux.get(p.split("-")[1])
    ]
    slow_pairs = [
        p for p in cr_pairs if qid_to_mux.get(p.split("-")[0]) != qid_to_mux.get(p.split("-")[1])
    ]
    return fast_pairs, slow_pairs


def convert_to_parallel_groups(grouped: list[list[str]]) -> list[list[tuple[str, str]]]:
    """Convert grouped CR pairs to parallel_groups format."""
    return [[(pair.split("-")[0], pair.split("-")[1]) for pair in group] for group in grouped]
