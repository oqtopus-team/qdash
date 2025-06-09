"""CR Pair Scheduler
=================

This script schedules and visualizes cross-resonance (CR) gate operations on a 64-qubit superconducting quantum processor.
The processor is arranged in a structured 2D lattice (4x4 unit cells), where each cell contains 4 qubits.

Features:
---------
- Extracts CR pairs with directionality constraints (based on bare frequency).
- Avoids scheduling conflicts arising from:
  - Shared qubits between CR pairs
  - Shared MUX readout or control resources
- Greedily colors the conflict graph to group CR pairs into parallelizable steps.
- Visualizes each step separately and as a combined figure with step-labeled edges.
- Uses real MUX wiring configuration from `wiring.yaml` and qubit lattice positions.

Modules:
--------
- `networkx` for graph modeling
- `matplotlib` for lattice visualization
- `qdash` (domain-specific) for chip layout and qubit metadata

Outputs:
--------
- Per-step CR connection plots (e.g., `schedule_step_1.png`, ...)
- Final combined plot (`combined_schedule.png`) where edge color and label indicate the execution step

Usage:
------
Run as a standalone script to generate scheduling info and visualization:
```bash
python cr_pair_scheduler.py
```
"""

import itertools
import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import yaml
from qdash.datamodel.qubit import QubitModel
from qdash.db.init import initialize
from qdash.dbmodel.chip import ChipDocument


def correct(original: tuple, s: float) -> tuple:
    offset = (1 / 3, 10 / 3)
    offset_applied = tuple(x + y for x, y in zip(original, offset, strict=False))
    return tuple(x * s for x in offset_applied)


def qubit_lattice(n: int, d: int) -> dict[str, tuple[float, float]]:
    def node(i: int, j: int, k: int) -> int:
        return 4 * (i * d + j) + k

    pos = {}
    for i in range(d):
        for j in range(d):
            pos[str(node(i, j, 0))] = correct((j - 1 / 3, -i + 1 / 3), 100)
            pos[str(node(i, j, 1))] = correct((j + 1 / 3, -i + 1 / 3), 100)
            pos[str(node(i, j, 2))] = correct((j - 1 / 3, -i - 1 / 3), 100)
            pos[str(node(i, j, 3))] = correct((j + 1 / 3, -i - 1 / 3), 100)
    return pos


def get_two_qubit_pair_list(chip_doc: ChipDocument) -> list[str]:
    return [
        coupling_id
        for coupling_id in chip_doc.couplings.keys()
        if "-" in coupling_id and len(coupling_id.split("-")) == 2
    ]


def cr_pair_list(two_qubit_list: list[str], bare_freq: dict[str, float]) -> list[str]:
    return [
        coupling_id
        for coupling_id in two_qubit_list
        if (q := coupling_id.split("-"))
        and q[0] in bare_freq
        and q[1] in bare_freq
        and bare_freq[q[0]] < bare_freq[q[1]]
    ]


def extract_bare_frequency(qubits: dict[str, QubitModel]) -> dict[str, float]:
    return {
        qid: qubit.data["bare_frequency"]["value"]
        for qid, qubit in qubits.items()
        if qubit.data and "bare_frequency" in qubit.data
    }


def build_mux_conflict_map(yaml_mux_list: list[dict]) -> dict[int, set[int]]:
    module_to_muxes_readout = defaultdict(set)
    module_to_muxes_ctrl = defaultdict(set)

    for mux_entry in yaml_mux_list:
        mux_id = mux_entry["mux"]
        read_out = mux_entry.get("read_out")
        if read_out:
            readout_module = read_out.split("-")[0]
            module_to_muxes_readout[readout_module].add(mux_id)
        for ctrl in mux_entry.get("ctrl", []):
            ctrl_module = ctrl.split("-")[0]
            module_to_muxes_ctrl[ctrl_module].add(mux_id)

    def to_conflict_map(module_to_muxes: dict[str, set[int]]) -> dict[int, set[int]]:
        mux_conflict = defaultdict(set)
        for muxes in module_to_muxes.values():
            for a, b in itertools.combinations(muxes, 2):
                mux_conflict[a].add(b)
                mux_conflict[b].add(a)
        return mux_conflict

    conflict_map = to_conflict_map(module_to_muxes_readout)
    ctrl_conflict_map = to_conflict_map(module_to_muxes_ctrl)

    for k, v in ctrl_conflict_map.items():
        conflict_map[k].update(v)
    return dict(conflict_map)


def build_qubit_to_mux_map(yaml_mux_list: list[dict]) -> dict[str, int]:
    qid_to_mux = {}
    for entry in yaml_mux_list:
        mux_id = entry["mux"]
        for i in range(4):
            qid_to_mux[str(mux_id * 4 + i)] = mux_id
    return qid_to_mux


def group_cr_pairs_by_conflict(
    cr_pairs: list[str], qid_to_mux: dict[str, int], mux_conflict_map: dict[int, set[int]]
) -> list[list[str]]:
    G = nx.Graph()
    G.add_nodes_from(cr_pairs)

    for a, b in itertools.combinations(cr_pairs, 2):
        q1a, q2a = a.split("-")
        q1b, q2b = b.split("-")

        if set([q1a, q2a]) & set([q1b, q2b]):
            G.add_edge(a, b)
            continue

        mux_a1, mux_a2 = qid_to_mux[q1a], qid_to_mux[q2a]
        mux_b1, mux_b2 = qid_to_mux[q1b], qid_to_mux[q2b]

        if mux_a1 in (mux_b1, mux_b2) or mux_a2 in (mux_b1, mux_b2):
            G.add_edge(a, b)
            continue

        conflict_muxes = mux_conflict_map.get(mux_a1, set()) | mux_conflict_map.get(mux_a2, set())
        if mux_b1 in conflict_muxes or mux_b2 in conflict_muxes:
            G.add_edge(a, b)

    coloring = nx.coloring.greedy_color(G, strategy="DSATUR")
    ## Save Graph image

    color_groups = defaultdict(list)
    for pair, color in coloring.items():
        color_groups[color].append(pair)
    return [color_groups[c] for c in sorted(color_groups)]


def convert_to_serial_parallel(grouped: list[list[str]]) -> dict:
    return {"serial": [{"parallel": group} for group in grouped]}


def visualize_combined_schedule(
    schedule: dict, qid_to_mux: dict[str, int], lattice_pos: dict[str, tuple[float, float]]
) -> None:
    G = nx.Graph()
    edge_colors = []
    edge_labels = {}
    cmap = plt.get_cmap("tab10")

    for idx, step in enumerate(schedule["serial"]):
        for pair in step["parallel"]:
            q1, q2 = pair.split("-")
            G.add_edge(q1, q2)
            edge_colors.append(cmap(idx % 10))
            edge_labels[(q1, q2)] = f"S{idx+1}"

    for qid in lattice_pos:
        G.add_node(qid)

    plt.figure(figsize=(10, 8))
    node_colors = [
        plt.cm.tab20(qid_to_mux[qid] % 20) if qid in qid_to_mux else "gray" for qid in G.nodes
    ]

    nx.draw(
        G,
        pos=lattice_pos,
        node_color=node_colors,
        edge_color=edge_colors,
        node_size=500,
        with_labels=True,
    )
    nx.draw_networkx_edge_labels(G, pos=lattice_pos, edge_labels=edge_labels, font_size=8)

    step_handles = [
        plt.Line2D([0], [0], color=cmap(i % 10), lw=2, label=f"Step {i+1}")
        for i in range(len(schedule["serial"]))
    ]
    plt.legend(handles=step_handles, bbox_to_anchor=(1.05, 1), loc="upper left")
    plt.title("Combined CR Schedule with Step Labels")
    plt.axis("off")
    plt.savefig("combined_schedule.png", dpi=300, bbox_inches="tight")


def visualize_each_step(
    schedule: dict, qid_to_mux: dict[str, int], lattice_pos: dict[str, tuple[float, float]]
) -> None:
    for i, step in enumerate(schedule["serial"]):
        G = nx.Graph()
        for pair in step["parallel"]:
            q1, q2 = pair.split("-")
            G.add_edge(q1, q2)

        for qid in lattice_pos:
            G.add_node(qid)

        node_colors = [
            plt.cm.tab20(qid_to_mux[qid] % 20) if qid in qid_to_mux else "gray" for qid in G.nodes
        ]

        plt.figure(figsize=(8, 6))
        nx.draw(G, pos=lattice_pos, node_color=node_colors, node_size=500, with_labels=True)
        plt.title(f"Internal Schedule Step {i + 1}")
        plt.axis("off")
        plt.savefig(f"schedule_step_{i + 1}.png", dpi=300, bbox_inches="tight")


if __name__ == "__main__":
    initialize()
    chip_doc = ChipDocument.get_current_chip("admin")
    two_qubit_list = get_two_qubit_pair_list(chip_doc)
    bare_freq = extract_bare_frequency(chip_doc.qubits)
    cr_pairs = cr_pair_list(two_qubit_list, bare_freq)

    wiring_path = Path("/workspace/qdash/config/wiring.yaml")
    yaml_data = yaml.safe_load(wiring_path.read_text())
    mux_conflict_map = build_mux_conflict_map(yaml_data["64Q"])
    qid_to_mux = build_qubit_to_mux_map(yaml_data["64Q"])

    grouped = group_cr_pairs_by_conflict(cr_pairs, qid_to_mux, mux_conflict_map)

    internal_pairs = set(itertools.chain.from_iterable(grouped))
    external_pairs = [pair for pair in cr_pairs if pair not in internal_pairs]

    internal_schedule = convert_to_serial_parallel(grouped)
    print("\n\U0001f4e6 Schedule")
    print(json.dumps(internal_schedule, indent=2))

    lattice_pos = qubit_lattice(64, 4)
    visualize_each_step(internal_schedule, qid_to_mux=qid_to_mux, lattice_pos=lattice_pos)
    visualize_combined_schedule(internal_schedule, qid_to_mux=qid_to_mux, lattice_pos=lattice_pos)
