"""CR Gate Schedule Generator
===========================

Generates optimized scheduling for cross-resonance (CR) gate operations on a 64-qubit
superconducting quantum processor arranged in a 2D lattice (4x4 unit cells).

This tool analyzes hardware constraints (shared qubits, MUX resources) and produces
parallel execution groups that maximize throughput while avoiding conflicts.

Key Features:
-------------
- Filters qubits by X90 gate fidelity (≥95% for both control and target)
- Extracts CR pairs with frequency-based directionality constraints
- Detects conflicts from shared qubits and MUX resource contention
- Uses greedy graph coloring to group CR pairs into parallel execution steps
- Separates fast (intra-MUX) and slow (inter-MUX) pairs for optimal scheduling
- Generates output compatible with two_qubit_parallel_calibration.py template

Output Format:
--------------
Parallel groups format: [[(control, target), ...], ...] for two_qubit_parallel_calibration.py

Usage:
------
    python src/tools/cr_schedule_generator.py

Outputs:
--------
- Console: Formatted parallel_groups ready for copy-paste into template
- Files: Visualization plots in schedule/ directory
  - schedule_group_N.png: Individual group visualizations
  - combined_schedule.png: All groups with color-coded edges
"""

import itertools
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import networkx as nx
import yaml
from qdash.datamodel.qubit import QubitModel
from qdash.dbmodel.initialize import initialize
from qdash.dbmodel.chip import ChipDocument


# ============================================================================
# Configuration Constants
# ============================================================================

MAX_PARALLEL_OPS = 10  # Maximum parallel operations per step
SCHEDULE_OUTPUT_DIR = Path("schedule")
LATTICE_DIMENSION = 4  # 4x4 unit cells
TOTAL_QUBITS = 64
EXCLUDE_QUBITS: set[str] = set()  # No qubits excluded by default
MIN_X90_FIDELITY = 0.95  # Minimum X90 gate fidelity (95%)
DEFAULT_CHIP_ID = "64Qv3"  # Default chip ID
DEFAULT_USERNAME = "orangekame3"  # Default username


# ============================================================================
# Data Extraction Functions
# ============================================================================


def extract_qubit_frequency(qubits: dict[str, QubitModel]) -> dict[str, float]:
    """Extract qubit frequencies from chip data.

    Args:
        qubits: Dictionary mapping qubit ID to QubitModel

    Returns:
        Dictionary mapping qubit ID to frequency value
    """
    return {
        qid: qubit.data["qubit_frequency"]["value"]
        for qid, qubit in qubits.items()
        if qubit.data and "qubit_frequency" in qubit.data
    }


def get_two_qubit_pair_list(chip_doc: ChipDocument) -> list[str]:
    """Extract all two-qubit coupling IDs from chip document.

    Args:
        chip_doc: Chip document containing coupling information

    Returns:
        List of coupling IDs in "qid1-qid2" format
    """
    return [
        coupling_id
        for coupling_id in chip_doc.couplings.keys()
        if "-" in coupling_id and len(coupling_id.split("-")) == 2
    ]


def extract_x90_fidelity(qubits: dict[str, QubitModel]) -> dict[str, float]:
    """Extract X90 gate fidelity from chip data.

    Args:
        qubits: Dictionary mapping qubit ID to QubitModel

    Returns:
        Dictionary mapping qubit ID to X90 gate fidelity value
    """
    return {
        qid: qubit.data["x90_gate_fidelity"]["value"]
        for qid, qubit in qubits.items()
        if qubit.data and "x90_gate_fidelity" in qubit.data
    }


def filter_cr_pairs(
    two_qubit_list: list[str],
    qubit_frequency: dict[str, float],
    x90_fidelity: dict[str, float],
    min_fidelity: float = 0.95
) -> list[str]:
    """Filter CR pairs based on frequency directionality and X90 gate fidelity.

    Args:
        two_qubit_list: All two-qubit coupling IDs
        qubit_frequency: Qubit frequencies
        x90_fidelity: X90 gate fidelity values
        min_fidelity: Minimum required fidelity (default: 0.95)

    Returns:
        Filtered list of valid CR pair IDs
    """
    return [
        pair for pair in two_qubit_list
        if (qubits := pair.split("-")) and len(qubits) == 2
        and qubits[0] in qubit_frequency and qubits[1] in qubit_frequency
        and qubit_frequency[qubits[0]] < qubit_frequency[qubits[1]]
        and qubits[0] in x90_fidelity and qubits[1] in x90_fidelity
        and x90_fidelity[qubits[0]] >= min_fidelity
        and x90_fidelity[qubits[1]] >= min_fidelity
    ]


# ============================================================================
# MUX Conflict Analysis
# ============================================================================


def build_mux_conflict_map(yaml_mux_list: list[dict[str, Any]]) -> dict[int, set[int]]:
    """Build conflict map for MUX resources from wiring configuration.

    MUXes conflict if they share the same readout or control module.

    Args:
        yaml_mux_list: List of MUX configurations from wiring.yaml

    Returns:
        Dictionary mapping MUX ID to set of conflicting MUX IDs
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
            # All MUXes sharing a module conflict with each other
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

    Args:
        yaml_mux_list: List of MUX configurations

    Returns:
        Dictionary mapping qubit ID string to MUX ID
    """
    qid_to_mux = {}
    for entry in yaml_mux_list:
        mux_id = entry["mux"]
        # Each MUX handles 4 consecutive qubits
        for offset in range(4):
            qid_to_mux[str(mux_id * 4 + offset)] = mux_id
    return qid_to_mux


# ============================================================================
# Conflict Graph and Scheduling
# ============================================================================


def group_cr_pairs_by_conflict(
    cr_pairs: list[str],
    qid_to_mux: dict[str, int],
    mux_conflict_map: dict[int, set[int]],
    max_parallel_ops: int | None = None,
) -> list[list[str]]:
    """Group CR pairs into parallel execution steps using greedy graph coloring.

    Builds a conflict graph where edges represent pairs that cannot execute simultaneously
    due to:
    1. Shared qubits
    2. Same MUX usage
    3. Conflicting MUX resources

    Args:
        cr_pairs: List of CR pair IDs
        qid_to_mux: Mapping from qubit ID to MUX ID
        mux_conflict_map: MUX conflict relationships
        max_parallel_ops: Optional limit on parallel operations per step

    Returns:
        List of parallel groups, where each group can execute simultaneously
    """
    # Build conflict graph
    conflict_graph = nx.Graph()
    conflict_graph.add_nodes_from(cr_pairs)

    for pair_a, pair_b in itertools.combinations(cr_pairs, 2):
        q1a, q2a = pair_a.split("-")
        q1b, q2b = pair_b.split("-")

        # Conflict 1: Shared qubits
        if set([q1a, q2a]) & set([q1b, q2b]):
            conflict_graph.add_edge(pair_a, pair_b)
            continue

        # Conflict 2: Same MUX usage
        mux_a1, mux_a2 = qid_to_mux[q1a], qid_to_mux[q2a]
        mux_b1, mux_b2 = qid_to_mux[q1b], qid_to_mux[q2b]

        if mux_a1 in (mux_b1, mux_b2) or mux_a2 in (mux_b1, mux_b2):
            conflict_graph.add_edge(pair_a, pair_b)
            continue

        # Conflict 3: MUX resource conflicts
        conflict_muxes = (
            mux_conflict_map.get(mux_a1, set()) |
            mux_conflict_map.get(mux_a2, set())
        )
        if mux_b1 in conflict_muxes or mux_b2 in conflict_muxes:
            conflict_graph.add_edge(pair_a, pair_b)

    # Greedy graph coloring (largest degree first heuristic)
    coloring = nx.coloring.greedy_color(conflict_graph, strategy="largest_first")

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
            # Split oversized groups into chunks
            for i in range(0, len(group), max_parallel_ops):
                chunk = group[i : i + max_parallel_ops]
                split_groups.append(chunk)
        return split_groups

    return groups


def split_fast_slow_pairs(
    cr_pairs: list[str],
    qid_to_mux: dict[str, int]
) -> tuple[list[str], list[str]]:
    """Separate CR pairs into fast (intra-MUX) and slow (inter-MUX) categories."""
    fast_pairs = [p for p in cr_pairs if qid_to_mux.get(p.split("-")[0]) == qid_to_mux.get(p.split("-")[1])]
    slow_pairs = [p for p in cr_pairs if qid_to_mux.get(p.split("-")[0]) != qid_to_mux.get(p.split("-")[1])]
    return fast_pairs, slow_pairs


# ============================================================================
# Output Format Conversion
# ============================================================================


def convert_to_parallel_groups(grouped: list[list[str]]) -> list[list[tuple[str, str]]]:
    """Convert grouped CR pairs to parallel_groups format for two_qubit_parallel_calibration.py.

    Args:
        grouped: List of groups, where each group contains CR pair strings like "0-1"

    Returns:
        List of parallel groups, where each group contains tuples like ("0", "1")
    """
    return [[tuple(pair.split("-")) for pair in group] for group in grouped]


# ============================================================================
# Visualization Functions
# ============================================================================


def correct_position(original: tuple[float, float], scale: float) -> tuple[float, float]:
    """Apply offset and scaling to lattice position coordinates."""
    return ((original[0] + 1/3) * scale, (original[1] + 10/3) * scale)


def qubit_lattice(n_qubits: int, dimension: int) -> dict[str, tuple[float, float]]:
    """Generate 2D lattice positions for qubits.

    Creates a 4x4 grid of unit cells, each containing 4 qubits.

    Args:
        n_qubits: Total number of qubits (typically 64)
        dimension: Lattice dimension (4 for 4x4 grid)

    Returns:
        Dictionary mapping qubit ID to (x, y) position
    """
    def node_id(i: int, j: int, k: int) -> int:
        """Calculate global qubit ID from cell indices and local position."""
        return 4 * (i * dimension + j) + k

    positions = {}
    for i in range(dimension):
        for j in range(dimension):
            # 4 qubits per unit cell arranged in a square
            positions[str(node_id(i, j, 0))] = correct_position((j - 1/3, -i + 1/3), 100)
            positions[str(node_id(i, j, 1))] = correct_position((j + 1/3, -i + 1/3), 100)
            positions[str(node_id(i, j, 2))] = correct_position((j - 1/3, -i - 1/3), 100)
            positions[str(node_id(i, j, 3))] = correct_position((j + 1/3, -i - 1/3), 100)

    return positions


def get_node_colors(graph: nx.Graph, qid_to_mux: dict[str, int]) -> list[tuple[float, ...]]:
    """Get node colors based on MUX assignment."""
    tab20 = plt.colormaps.get_cmap("tab20")
    return [tab20(qid_to_mux[qid] % 20) if qid in qid_to_mux else "gray" for qid in graph.nodes]


def visualize_combined_schedule(
    grouped: list[list[str]],
    qid_to_mux: dict[str, int],
    lattice_pos: dict[str, tuple[float, float]],
    output_path: Path = SCHEDULE_OUTPUT_DIR / "combined_schedule.png"
) -> None:
    """Create combined visualization showing all schedule steps with color-coded edges."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build graph with color-coded edges
    graph = nx.Graph()
    edge_colors = []
    edge_labels = {}
    cmap = plt.colormaps.get_cmap("tab10")

    for group_idx, group in enumerate(grouped):
        for pair in group:
            q1, q2 = pair.split("-")
            graph.add_edge(q1, q2)
            edge_colors.append(cmap(group_idx % 10))
            edge_labels[(q1, q2)] = f"G{group_idx + 1}"

    graph.add_nodes_from(lattice_pos.keys())

    # Draw graph
    plt.figure(figsize=(10, 8))
    nx.draw(graph, pos=lattice_pos, node_color=get_node_colors(graph, qid_to_mux),
            edge_color=edge_colors, node_size=500, with_labels=True)
    nx.draw_networkx_edge_labels(graph, pos=lattice_pos, edge_labels=edge_labels, font_size=8)

    # Add legend
    group_handles = [plt.Line2D([0], [0], color=cmap(i % 10), lw=2, label=f"Group {i + 1}")
                     for i in range(len(grouped))]
    plt.legend(handles=group_handles, bbox_to_anchor=(1.05, 1), loc="upper left")
    plt.title("Combined CR Schedule with Group Labels")
    plt.axis("off")
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()


def visualize_each_step(
    grouped: list[list[str]],
    qid_to_mux: dict[str, int],
    lattice_pos: dict[str, tuple[float, float]],
    output_dir: Path = SCHEDULE_OUTPUT_DIR
) -> None:
    """Create individual visualization for each parallel group."""
    output_dir.mkdir(parents=True, exist_ok=True)

    for group_idx, group in enumerate(grouped):
        graph = nx.Graph()

        # Add edges for this group
        for pair in group:
            q1, q2 = pair.split("-")
            graph.add_edge(q1, q2)

        graph.add_nodes_from(lattice_pos.keys())

        plt.figure(figsize=(8, 6))
        nx.draw(graph, pos=lattice_pos, node_color=get_node_colors(graph, qid_to_mux),
                node_size=500, with_labels=True)
        plt.title(f"Parallel Group {group_idx + 1}")
        plt.axis("off")
        plt.savefig(output_dir / f"schedule_group_{group_idx + 1}.png", dpi=300, bbox_inches="tight")
        plt.close()


# ============================================================================
# Main Execution
# ============================================================================


def print_schedule_summary(parallel_groups: list[list[tuple[str, str]]]) -> None:
    """Print formatted schedule output for two_qubit_parallel_calibration.py."""
    print("Parallel Groups (copy-paste into two_qubit_parallel_calibration.py)")
    print("parallel_groups = [")
    for idx, group in enumerate(parallel_groups, 1):
        pairs_str = ", ".join([f'("{c}", "{t}")' for c, t in group])
        print(f"    [{pairs_str}],  # Group {idx}: {len(group)} pairs")
    print("]")

    # Summary
    total_pairs = sum(len(g) for g in parallel_groups)
    print(f"Total: {total_pairs} coupling pairs in {len(parallel_groups)} parallel groups")


def main(chip_id: str = DEFAULT_CHIP_ID, username: str = DEFAULT_USERNAME) -> None:
    """Main execution function for CR schedule generation.

    Args:
        chip_id: Chip ID to use (default: 64Qv3)
        username: Username for chip data access (default: orangekame3)
    """
    initialize()

    print(f"Configuration:")
    print(f"  Chip ID: {chip_id}")
    print(f"  Username: {username}")
    print(f"  Min X90 fidelity: {MIN_X90_FIDELITY * 100:.0f}%")
    print(f"  Max parallel ops: {MAX_PARALLEL_OPS}")

    # Load chip data and extract CR pairs
    chip_doc = ChipDocument.get_current_chip(username)
    qubit_frequency = extract_qubit_frequency(chip_doc.qubits)
    x90_fidelity = extract_x90_fidelity(chip_doc.qubits)

    print(f"\nDebug info:")
    print(f"  Total qubits in chip: {len(chip_doc.qubits)}")
    print(f"  Qubits with frequency data: {len(qubit_frequency)}")
    print(f"  Qubits with X90 fidelity data: {len(x90_fidelity)}")
    if len(qubit_frequency) > 0:
        sample_qids = list(qubit_frequency.keys())[:3]
        print(f"  Sample qubit frequencies: {[(qid, qubit_frequency[qid]) for qid in sample_qids]}")

    all_pairs = get_two_qubit_pair_list(chip_doc)

    # Check if we have required data
    if len(qubit_frequency) == 0:
        print("\nError: No qubit frequency data found in chip document.")
        print("  Cannot apply frequency directionality filter.")
        print("  Please run qubit frequency calibration first.")
        return

    # Filter by frequency directionality only
    freq_filtered = [
        pair for pair in all_pairs
        if (qubits := pair.split("-")) and len(qubits) == 2
        and qubits[0] in qubit_frequency and qubits[1] in qubit_frequency
        and qubit_frequency[qubits[0]] < qubit_frequency[qubits[1]]
    ]

    # Filter CR pairs by frequency directionality and X90 fidelity
    cr_pairs = filter_cr_pairs(
        all_pairs,
        qubit_frequency,
        x90_fidelity,
        MIN_X90_FIDELITY
    )

    if EXCLUDE_QUBITS:
        cr_pairs = [p for p in cr_pairs if not set(p.split("-")) & EXCLUDE_QUBITS]

    print(f"\nFiltering results:")
    print(f"  Total coupling pairs: {len(all_pairs)}")
    print(f"  After frequency filter: {len(freq_filtered)}")
    print(f"  Qubits with X90 data: {len(x90_fidelity)}")
    print(f"  After X90 fidelity >= {MIN_X90_FIDELITY * 100:.0f}%: {len(cr_pairs)}")
    print(f"  Final CR pairs: {len(cr_pairs)}")

    if len(cr_pairs) == 0 and len(freq_filtered) > 0:
        print("\nWarning: No pairs passed X90 fidelity filter.")
        print("  Using frequency-filtered pairs instead (ignoring X90 filter)...")
        cr_pairs = freq_filtered

    if len(cr_pairs) == 0:
        print("\nError: No valid CR pairs after filtering.")
        print("  Cannot generate schedule.")
        return

    # Load MUX configuration
    wiring_path = Path(f"/workspace/qdash/config/qubex/{chip_id}/config/wiring.yaml")
    if not wiring_path.exists():
        raise FileNotFoundError(f"Wiring config not found: {wiring_path}")

    yaml_data = yaml.safe_load(wiring_path.read_text())[chip_id]
    mux_conflict_map = build_mux_conflict_map(yaml_data)
    qid_to_mux = build_qubit_to_mux_map(yaml_data)

    # Group pairs: fast first, then slow
    fast, slow = split_fast_slow_pairs(cr_pairs, qid_to_mux)
    grouped = (
        group_cr_pairs_by_conflict(fast, qid_to_mux, mux_conflict_map, MAX_PARALLEL_OPS) +
        group_cr_pairs_by_conflict(slow, qid_to_mux, mux_conflict_map, MAX_PARALLEL_OPS)
    )

    # Print parallel_groups format
    print_schedule_summary(convert_to_parallel_groups(grouped))

    # Generate visualizations
    lattice_pos = qubit_lattice(TOTAL_QUBITS, LATTICE_DIMENSION)
    visualize_each_step(grouped, qid_to_mux, lattice_pos)
    visualize_combined_schedule(grouped, qid_to_mux, lattice_pos)

    print(f"Visualizations saved to {SCHEDULE_OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
