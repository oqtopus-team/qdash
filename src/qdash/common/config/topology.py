"""Topology configuration loader."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING

import yaml
from pydantic import BaseModel, Field

from qdash.common.config.loader import ConfigLoader

if TYPE_CHECKING:
    from pathlib import Path


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
    direction_convention: str = Field(
        default="unspecified",
        description="Coupling direction convention: 'checkerboard_cr' means [control, target] order based on (row+col)%2 parity",
    )
    mux: MuxConfig = Field(default_factory=MuxConfig)
    qubits: dict[int, QubitPosition]
    couplings: list[list[int]]
    visualization: VisualizationConfig = Field(default_factory=VisualizationConfig)


TOPOLOGIES_DIR = "topologies"


def _get_config_dir() -> Path:
    """Get the configuration directory path using ConfigLoader."""
    return ConfigLoader.get_config_dir()


@lru_cache(maxsize=32)
def load_topology(topology_id: str) -> TopologyDefinition:
    """Load a specific topology definition."""
    config_dir = _get_config_dir()
    topology_path = config_dir / TOPOLOGIES_DIR / f"{topology_id}.yaml"

    if not topology_path.exists():
        raise FileNotFoundError(f"Topology file not found: {topology_path}")

    with topology_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return TopologyDefinition(**data)


def list_topologies(size: int | None = None) -> list[dict[str, str]]:
    """List all available topology definitions."""
    config_dir = _get_config_dir()
    topologies_dir = config_dir / TOPOLOGIES_DIR

    if not topologies_dir.exists():
        return []

    topologies = []
    for path in topologies_dir.glob("*.yaml"):
        try:
            with path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f)
            num_qubits = data.get("num_qubits", 0)
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
            logging.getLogger(__name__).warning("Skipping invalid topology file: %s", path)
            continue

    return sorted(topologies, key=lambda x: x["id"])
