"""Topology configuration loader.

This module loads topology definitions from YAML configuration files.
Each topology file contains explicit qubit positions and coupling definitions.

Uses ConfigLoader for unified configuration directory resolution.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from qdash.api.lib.config_loader import ConfigLoader


class QubitPosition(BaseModel):
    """Position of a qubit in the grid."""

    row: int
    col: int


class MuxConfig(BaseModel):
    """MUX (Multiplexer) configuration."""

    enabled: bool = False
    size: int = Field(default=2, description="MUX grid size (e.g., 2 means 2x2)")


class VisualizationConfig(BaseModel):
    """Visualization settings for UI rendering."""

    show_mux_boundaries: bool = False
    region_size: int = Field(default=4, description="Grid region size for zoom")


class TopologyDefinition(BaseModel):
    """A topology definition with explicit qubit positions and couplings."""

    id: str
    name: str
    description: str = ""
    grid_size: int
    num_qubits: int
    layout_type: str = Field(default="grid", description="Layout type: grid, hex, linear")
    mux: MuxConfig = Field(default_factory=MuxConfig)
    qubits: dict[int, QubitPosition]
    couplings: list[list[int]]
    visualization: VisualizationConfig = Field(default_factory=VisualizationConfig)


# Topologies directory name (relative to config directory)
TOPOLOGIES_DIR = "topologies"


def _get_config_dir() -> Path:
    """Get the configuration directory path using ConfigLoader."""
    return ConfigLoader.get_config_dir()


@lru_cache(maxsize=32)
def load_topology(topology_id: str) -> TopologyDefinition:
    """Load a specific topology definition.

    Args:
    ----
        topology_id: Topology identifier (e.g., "square-lattice-mux-64")

    Returns:
    -------
        TopologyDefinition with explicit qubit positions and couplings

    Raises:
    ------
        FileNotFoundError: If topology file doesn't exist

    """
    config_dir = _get_config_dir()
    topology_path = config_dir / TOPOLOGIES_DIR / f"{topology_id}.yaml"

    if not topology_path.exists():
        raise FileNotFoundError(f"Topology file not found: {topology_path}")

    with open(topology_path) as f:
        data = yaml.safe_load(f)

    return TopologyDefinition(**data)


def list_topologies(size: int | None = None) -> list[dict[str, str]]:
    """List all available topology definitions.

    Args:
    ----
        size: Optional filter by number of qubits

    Returns:
    -------
        List of dicts with topology id, name, and num_qubits

    """
    config_dir = _get_config_dir()
    topologies_dir = config_dir / TOPOLOGIES_DIR

    if not topologies_dir.exists():
        return []

    topologies = []
    for path in topologies_dir.glob("*.yaml"):
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
            num_qubits = data.get("num_qubits", 0)
            # Filter by size if specified
            if size is not None and num_qubits != size:
                continue
            topologies.append(
                {
                    "id": data.get("id", path.stem),
                    "name": data.get("name", path.stem),
                    "num_qubits": num_qubits,
                }
            )
        except Exception:
            # Skip invalid files
            continue

    return sorted(topologies, key=lambda x: x["id"])
