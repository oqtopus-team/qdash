"""Topology configuration loader.

A topology template is QDash's own description of a chip: qubit positions,
couplings and MUX membership. The canonical format lists MUXes at top level::

    qubits: {0: {row: 0, col: 0}, ...}
    couplings: [[0, 1], ...]
    muxes:
      0: [0, 1, 2, 3]
      1: [4, 5]
    visualization: {show_mux_boundaries: true, region_size: 4}

``muxes`` maps the hardware MUX ID to its member qubits. The array index of a
member is its local slot in that MUX (the index of its control port in
``wiring.yaml``); the order of the MUX keys carries no meaning. Known qubits
that no MUX lists are standalone (not multiplexed), and ``muxes: {}`` declares
a chip without any MUX. ``muxes`` is required so that an empty declaration
cannot be confused with an accidentally omitted one.

Older templates with a ``mux:`` block are still read and normalized here:

* ``mux: {enabled: false}`` means no MUX (every qubit is standalone).
* ``mux: {enabled: true, groups: {id: {qids: [...]}}}`` lists the MUXes.
* ``mux: {enabled: true}`` without groups keeps the historical convention:
  MUX ``qid // 4`` on local slot ``qid % 4``, bounded to the defined qubits.

A template with both ``mux`` and ``muxes`` is ambiguous and rejected.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

from qdash.common.config.loader import ConfigLoader

if TYPE_CHECKING:
    from pathlib import Path


# Legacy convention for ``mux: {enabled: true}`` templates without groups (and
# for chips without a topology): MUX N owns qubits 4N..4N+3 and qubit q sits
# on local slot q % 4.
LEGACY_QUBITS_PER_MUX = 4

MuxesSource = Literal["muxes", "legacy_groups", "legacy_qid_div_4", "legacy_disabled"]
"""Where a topology's MUX membership came from.

``muxes`` is the canonical format; the ``legacy_*`` values name the old
``mux:`` block variants that were normalized into ``muxes``.
"""


class QubitPosition(BaseModel):
    """Position of a qubit in the grid."""

    row: int
    col: int


class VisualizationConfig(BaseModel):
    """Visualization settings for UI rendering.

    ``show_mux_boundaries`` only controls whether the UI draws MUX outlines;
    MUX membership itself always comes from ``muxes``.
    """

    show_mux_boundaries: bool = False
    region_size: int = Field(default=4, description="Grid region size for zoom")


class _LegacyMuxGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    qids: list[StrictInt]


class _LegacyMuxConfig(BaseModel):
    """The old ``mux:`` block; only read to normalize it into ``muxes``."""

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = False
    size: StrictInt | None = None
    groups: dict[StrictInt, _LegacyMuxGroup] | None = None


def _normalize_mux_input(data: Any) -> Any:
    """Turn the raw template's MUX declaration into canonical ``muxes``."""
    if not isinstance(data, dict):
        return data
    data = dict(data)
    if "muxes_source" in data:
        raise ValueError("muxes_source is derived by QDash and cannot be set in a template")
    has_mux = "mux" in data
    has_muxes = "muxes" in data
    if has_mux and has_muxes:
        raise ValueError("The template declares both 'mux' (legacy) and 'muxes'; keep only 'muxes'")
    if has_muxes:
        if not isinstance(data["muxes"], dict):
            raise ValueError(
                "'muxes' must be a mapping of MUX ID to member qubit IDs; use 'muxes: {}' for a chip without MUX"
            )
        data["muxes_source"] = "muxes"
        return data
    if not has_mux:
        raise ValueError(
            "The template does not declare 'muxes'. List each MUX as "
            "'muxes: {<mux_id>: [<qid>, ...]}', or write 'muxes: {}' when no qubit is multiplexed"
        )
    legacy = _LegacyMuxConfig.model_validate(data.pop("mux") or {})
    if not legacy.enabled:
        if legacy.groups:
            raise ValueError("mux.groups requires mux.enabled: true")
        data["muxes"] = {}
        data["muxes_source"] = "legacy_disabled"
        return data
    if legacy.groups is not None:
        data["muxes"] = {mux_id: list(group.qids) for mux_id, group in legacy.groups.items()}
        data["muxes_source"] = "legacy_groups"
        return data
    qubits = data.get("qubits")
    if not isinstance(qubits, dict):
        # Let the field validation report the malformed qubits.
        data["muxes"] = {}
        data["muxes_source"] = "legacy_qid_div_4"
        return data
    derived: dict[int, list[int]] = {}
    for qid in sorted(q for q in qubits if isinstance(q, int) and q >= 0):
        derived.setdefault(qid // LEGACY_QUBITS_PER_MUX, []).append(qid)
    data["muxes"] = derived
    data["muxes_source"] = "legacy_qid_div_4"
    return data


class TopologyDefinition(BaseModel):
    """A topology definition with explicit qubit positions, couplings and MUXes."""

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
    qubits: dict[StrictInt, QubitPosition]
    couplings: list[list[int]]
    muxes: dict[StrictInt, list[StrictInt]] = Field(
        description=(
            "MUX ID to member qubit IDs. A member's array index is its local slot; "
            "qubits no MUX lists are standalone"
        ),
    )
    muxes_source: MuxesSource = Field(
        default="muxes",
        description="Derived: canonical 'muxes' or the legacy 'mux' variant it was read from",
    )
    visualization: VisualizationConfig = Field(default_factory=VisualizationConfig)

    @model_validator(mode="before")
    @classmethod
    def _normalize_mux(cls, data: Any) -> Any:
        return _normalize_mux_input(data)

    @model_validator(mode="after")
    def _validate_layout(self) -> TopologyDefinition:
        for qid, position in self.qubits.items():
            if qid < 0:
                raise ValueError(f"Qubit IDs must be non-negative: {qid}")
            if not (0 <= position.row < self.grid_size and 0 <= position.col < self.grid_size):
                raise ValueError(
                    f"Qubit {qid} at ({position.row}, {position.col}) is outside "
                    f"grid_size {self.grid_size}"
                )
        owner: dict[int, int] = {}
        for mux_id, members in self.muxes.items():
            if mux_id < 0:
                raise ValueError(f"MUX IDs must be non-negative: {mux_id}")
            if not members:
                raise ValueError(
                    f"MUX {mux_id} has no qubits; remove it, or list its qubits in slot order"
                )
            for qid in members:
                if qid < 0:
                    raise ValueError(f"MUX {mux_id} lists a negative qubit ID: {qid}")
                if qid in owner:
                    where = "twice" if owner[qid] == mux_id else f"in MUX {owner[qid]} too"
                    raise ValueError(f"MUX {mux_id} lists qubit {qid} {where}")
                owner[qid] = mux_id
        unknown = sorted(set(owner) - set(self.qubits))
        if unknown:
            raise ValueError(f"muxes references qubits not in qubits: {unknown}")
        return self

    def mux_slots(self) -> dict[int, int]:
        """Qubit -> local slot for every multiplexed qubit.

        The slot is the member's array index, except for templates normalized
        from the legacy ``qid // 4`` convention, where it stays ``qid % 4``.
        """
        if self.muxes_source == "legacy_qid_div_4":
            return {
                qid: qid % LEGACY_QUBITS_PER_MUX
                for members in self.muxes.values()
                for qid in members
            }
        return {qid: slot for members in self.muxes.values() for slot, qid in enumerate(members)}

    def standalone_qubits(self) -> list[int]:
        """Known qubits that no MUX lists, in ascending order."""
        assigned = {qid for members in self.muxes.values() for qid in members}
        return sorted(qid for qid in self.qubits if qid not in assigned)


TOPOLOGIES_DIR = "domain/topologies"


def _get_config_dir() -> Path:
    """Get the configuration directory path using ConfigLoader."""
    return ConfigLoader.get_config_dir()


def _topologies_dir() -> Path:
    return _get_config_dir() / TOPOLOGIES_DIR


@lru_cache(maxsize=32)
def load_topology(topology_id: str) -> TopologyDefinition:
    """Load a specific topology definition."""
    topology_path = _topologies_dir() / f"{topology_id}.yaml"

    if not topology_path.exists():
        raise FileNotFoundError(f"Topology file not found: {topology_path}")

    with topology_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return TopologyDefinition(**data)


def list_topologies(size: int | None = None) -> list[dict[str, str]]:
    """List all available topology definitions."""
    topologies_dir = _topologies_dir()

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
