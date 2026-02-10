#!/usr/bin/env python3
"""
Generate topology YAML files with explicit qubit positions and couplings.

This script generates topology configuration files that explicitly define:
- Qubit positions (row, col) for each qubit ID
- Coupling connections between adjacent qubits

Usage:
    python generate_topology.py --template square-lattice-mux --size 64 --output topology.yaml
    python generate_topology.py --template linear --size 16 --output linear.yaml
"""

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml


def generate_square_lattice_mux(
    num_qubits: int, mux_size: int = 2
) -> dict[str, Any]:
    """
    Generate square lattice topology with MUX grouping.

    MUX layout example (2x2 MUX, 64 qubits = 8x8 grid):
    - MUX0: 0-3, MUX1: 4-7, ...
    - Each MUX is a 2x2 block of qubits
    - Qubits within a MUX are arranged in row-major order
    """
    grid_size = int(num_qubits**0.5)
    qubits_per_mux = mux_size * mux_size
    muxes_per_row = grid_size // mux_size

    qubits: dict[int, dict[str, int]] = {}
    couplings: list[list[int]] = []

    # Generate qubit positions
    for qid in range(num_qubits):
        mux_index = qid // qubits_per_mux
        local_index = qid % qubits_per_mux

        mux_row = mux_index // muxes_per_row
        mux_col = mux_index % muxes_per_row

        local_row = local_index // mux_size
        local_col = local_index % mux_size

        row = mux_row * mux_size + local_row
        col = mux_col * mux_size + local_col

        qubits[qid] = {"row": row, "col": col}

    # Generate couplings (adjacent qubits in the grid)
    # Ordered as [control, target] based on checkerboard parity
    position_to_qid: dict[tuple[int, int], int] = {}
    for qid, pos in qubits.items():
        position_to_qid[(pos["row"], pos["col"])] = qid

    added_couplings: set[tuple[int, int]] = set()
    for qid, pos in qubits.items():
        row, col = pos["row"], pos["col"]

        # Check right neighbor
        right_pos = (row, col + 1)
        if right_pos in position_to_qid:
            neighbor = position_to_qid[right_pos]
            coupling = tuple(sorted([qid, neighbor]))
            if coupling not in added_couplings:
                added_couplings.add(coupling)
                couplings.append(
                    _order_coupling_by_checkerboard(qid, neighbor, qubits)
                )

        # Check bottom neighbor
        bottom_pos = (row + 1, col)
        if bottom_pos in position_to_qid:
            neighbor = position_to_qid[bottom_pos]
            coupling = tuple(sorted([qid, neighbor]))
            if coupling not in added_couplings:
                added_couplings.add(coupling)
                couplings.append(
                    _order_coupling_by_checkerboard(qid, neighbor, qubits)
                )

    return {
        "name": "Square Lattice with MUX",
        "description": f"Square lattice topology with {mux_size}x{mux_size} MUX groups",
        "grid_size": grid_size,
        "num_qubits": num_qubits,
        "direction_convention": "checkerboard_cr",
        "mux": {"enabled": True, "size": mux_size},
        "qubits": qubits,
        "couplings": couplings,
        "visualization": {
            "show_mux_boundaries": True,
            "region_size": 4,
        },
    }


def generate_square_lattice(num_qubits: int) -> dict[str, Any]:
    """
    Generate simple square lattice topology without MUX.

    Row-major ordering: 0 at (0,0), 1 at (0,1), etc.
    """
    grid_size = int(num_qubits**0.5)

    qubits: dict[int, dict[str, int]] = {}
    couplings: list[list[int]] = []

    # Generate qubit positions (simple row-major)
    for qid in range(num_qubits):
        row = qid // grid_size
        col = qid % grid_size
        qubits[qid] = {"row": row, "col": col}

    # Generate couplings (adjacent qubits)
    # Ordered as [control, target] based on checkerboard parity
    for qid in range(num_qubits):
        row = qid // grid_size
        col = qid % grid_size

        # Right neighbor
        if col + 1 < grid_size:
            neighbor_qid = row * grid_size + (col + 1)
            couplings.append(
                _order_coupling_by_checkerboard(qid, neighbor_qid, qubits)
            )

        # Bottom neighbor
        if row + 1 < grid_size:
            neighbor_qid = (row + 1) * grid_size + col
            couplings.append(
                _order_coupling_by_checkerboard(qid, neighbor_qid, qubits)
            )

    return {
        "name": "Square Lattice",
        "description": "Simple square lattice topology",
        "grid_size": grid_size,
        "num_qubits": num_qubits,
        "direction_convention": "checkerboard_cr",
        "mux": {"enabled": False},
        "qubits": qubits,
        "couplings": couplings,
        "visualization": {
            "show_mux_boundaries": False,
            "region_size": 4,
        },
    }


def generate_linear(num_qubits: int) -> dict[str, Any]:
    """
    Generate linear chain topology.

    All qubits in a single row, connected sequentially.
    """
    qubits: dict[int, dict[str, int]] = {}
    couplings: list[list[int]] = []

    # Generate qubit positions (single row)
    for qid in range(num_qubits):
        qubits[qid] = {"row": 0, "col": qid}

    # Generate couplings (sequential)
    for qid in range(num_qubits - 1):
        couplings.append([qid, qid + 1])

    return {
        "name": "Linear Chain",
        "description": "Linear qubit chain topology",
        "grid_size": num_qubits,
        "num_qubits": num_qubits,
        "mux": {"enabled": False},
        "qubits": qubits,
        "couplings": couplings,
        "visualization": {
            "show_mux_boundaries": False,
            "region_size": num_qubits,
        },
    }


def generate_heavy_hex(num_qubits: int) -> dict[str, Any]:
    """
    Generate heavy-hex topology (IBM-style).

    This is a simplified version - real heavy-hex has specific connectivity patterns.
    For now, generates a hex-like grid structure.
    """
    # Heavy-hex is complex; this is a placeholder that creates a grid
    # with hex-like staggered rows
    grid_size = int(num_qubits**0.5)

    qubits: dict[int, dict[str, int]] = {}
    couplings: list[list[int]] = []

    # Generate qubit positions with staggered rows
    qid = 0
    for row in range(grid_size):
        for col in range(grid_size):
            if qid >= num_qubits:
                break
            qubits[qid] = {"row": row, "col": col}
            qid += 1

    # Generate couplings (nearest neighbors in hex pattern)
    position_to_qid: dict[tuple[int, int], int] = {}
    for qid, pos in qubits.items():
        position_to_qid[(pos["row"], pos["col"])] = qid

    added_couplings: set[tuple[int, int]] = set()
    for qid, pos in qubits.items():
        row, col = pos["row"], pos["col"]

        # Neighbors for hex-like pattern
        neighbors = [
            (row, col + 1),  # right
            (row + 1, col),  # bottom
        ]
        # Add diagonal for odd rows (hex offset)
        if row % 2 == 1:
            neighbors.append((row + 1, col + 1))
        else:
            neighbors.append((row + 1, col - 1))

        for neighbor_pos in neighbors:
            if neighbor_pos in position_to_qid:
                neighbor = position_to_qid[neighbor_pos]
                coupling = tuple(sorted([qid, neighbor]))
                if coupling not in added_couplings:
                    added_couplings.add(coupling)
                    couplings.append([qid, neighbor])

    return {
        "name": "Heavy Hex",
        "description": "Heavy hexagonal topology (IBM-style)",
        "grid_size": grid_size,
        "num_qubits": num_qubits,
        "mux": {"enabled": False},
        "qubits": qubits,
        "couplings": couplings,
        "visualization": {
            "show_mux_boundaries": False,
            "region_size": 6,
        },
    }


def _order_coupling_by_checkerboard(
    qid_a: int,
    qid_b: int,
    qubits: dict[int, dict[str, int]],
) -> list[int]:
    """Order a coupling pair as [control, target] based on checkerboard parity.

    Convention: (row+col)%2==0 → control (low-frequency), (row+col)%2==1 → target (high-frequency).
    If both qubits have the same parity, fall back to ascending ID order.
    """
    pos_a = qubits[qid_a]
    pos_b = qubits[qid_b]
    parity_a = (pos_a["row"] + pos_a["col"]) % 2
    parity_b = (pos_b["row"] + pos_b["col"]) % 2

    if parity_a != parity_b:
        # Low parity (even) = control, high parity (odd) = target
        if parity_a < parity_b:
            return [qid_a, qid_b]
        else:
            return [qid_b, qid_a]
    else:
        # Same parity: fall back to ascending ID order
        return sorted([qid_a, qid_b])


GENERATORS = {
    "square-lattice-mux": generate_square_lattice_mux,
    "square-lattice": generate_square_lattice,
    "linear": generate_linear,
    "heavy-hex": generate_heavy_hex,
}


def generate_topology_id(template: str, size: int) -> str:
    """Generate a topology ID from template and size."""
    return f"{template}-{size}"


def main():
    parser = argparse.ArgumentParser(
        description="Generate topology YAML with explicit qubit positions and couplings"
    )
    parser.add_argument(
        "--template",
        choices=list(GENERATORS.keys()),
        default="square-lattice-mux",
        help="Topology template to generate",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=64,
        help="Number of qubits (default: 64)",
    )
    parser.add_argument(
        "--mux-size",
        type=int,
        default=2,
        help="MUX size for square-lattice-mux template (default: 2)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="config/topologies",
        help="Output directory for topology files (default: config/topologies)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path (overrides --output-dir, outputs to stdout if not specified)",
    )

    args = parser.parse_args()

    # Generate topology
    generator = GENERATORS[args.template]
    if args.template == "square-lattice-mux":
        topology = generator(args.size, args.mux_size)
    else:
        topology = generator(args.size)

    # Add topology ID
    topology_id = generate_topology_id(args.template, args.size)
    topology["id"] = topology_id

    # Custom YAML representer for cleaner output
    def represent_list(dumper, data):
        # Use flow style for short lists (couplings - pairs of integers)
        if len(data) == 2 and all(isinstance(x, int) for x in data):
            return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=True)
        return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=False)

    yaml.add_representer(list, represent_list)

    yaml_output = yaml.dump(topology, default_flow_style=False, allow_unicode=True, sort_keys=False)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(yaml_output)
        print(f"Generated topology written to: {args.output}", file=sys.stderr)
    elif args.output_dir:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{topology_id}.yaml"
        output_path.write_text(yaml_output)
        print(f"Generated topology written to: {output_path}", file=sys.stderr)
    else:
        print(yaml_output)


if __name__ == "__main__":
    main()
