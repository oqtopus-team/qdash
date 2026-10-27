"""Map a QDash chip to the Qubex Systems that drive it.

Qubex 1.5 selects hardware by ``system_id``; a chip may be driven by several
Systems (for example a QuEL-1 and a QuEL-3 System on disjoint MUXes). QDash keeps
``chip_id`` as its primary key and derives the System at run time from the
targeted qubits: qubit -> MUX (``wiring.yaml``) -> System (``system.yaml``).

This module is the single reader of ``chip.yaml`` / ``system.yaml`` /
``wiring.yaml`` for QDash. It understands both directory layouts of
:class:`~qdash.common.config.qubex_layout.QubexLayout` and the following shapes:

- no ``system.yaml``, or the legacy single-entry shape (``chip_id:``/``backend:``
  at the top level): one implicit System with ``system_id == chip_id``;
- a catalog ``{<system_id>: {chip_id, backend, ...}}``: the Systems whose
  ``chip_id`` is this chip, or the System named exactly like the QDash chip
  (used while a chip is split across two QDash instances);
- ``wiring.yaml`` keyed by ``system_id`` (preferred), by ``chip_id``, or, for an
  implicit System only, by arbitrary group names that are flattened together.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from qdash.common.wiring_resources import mux_module_resources

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from qdash.common.config.qubex_layout import QubexLayout

DRIVER_QUBEX = "qubex"
"""QDash backend driver name for Systems described by qubex configuration files."""

DEFAULT_BACKEND = "quel1"
"""Qubex backend kind assumed when ``system.yaml`` does not name one."""

DEFAULT_MUX_SIZE = 4
"""Qubits per MUX when ``chip.yaml`` has no ``topology.mux_size``."""

_LEGACY_SYSTEM_KEYS = frozenset({"schema_version", "chip_id", "backend", "quel1", "quel3"})
_TRAILING_DIGITS = re.compile(r"(\d+)$")


class SystemSplitRequired(ValueError):
    """The targeted qubits belong to more than one System.

    One Qubex ``Experiment`` drives one System, so the caller must run the
    targets as separate sessions, one per System.
    """

    def __init__(self, chip_id: str, assignment: Mapping[str, list[str]]) -> None:
        self.chip_id = chip_id
        self.assignment = {system_id: list(qids) for system_id, qids in assignment.items()}
        summary = "; ".join(
            f"{system_id}: {', '.join(qids)}" for system_id, qids in self.assignment.items()
        )
        super().__init__(
            f"Targets on chip {chip_id} span {len(self.assignment)} Systems ({summary}); "
            "run one session per System"
        )


class CrossSystemCoupling(SystemSplitRequired):
    """A coupling's two qubits are driven by different Systems and cannot be calibrated."""

    def __init__(self, chip_id: str, coupling: str, systems: tuple[str, str]) -> None:
        self.coupling = coupling
        self.systems = systems
        ValueError.__init__(
            self,
            f"Coupling {coupling} on chip {chip_id} spans Systems {systems[0]} and {systems[1]}; "
            "both qubits must be driven by the same System",
        )
        self.chip_id = chip_id
        control, target = coupling.split("-", maxsplit=1)
        self.assignment = {systems[0]: [control], systems[1]: [target]}


@dataclass(frozen=True)
class SystemEntry:
    """One System of a chip as described by ``system.yaml`` and ``wiring.yaml``."""

    system_id: str
    chip_id: str
    """Chip ID as Qubex knows it (the ``chip.yaml`` key)."""
    driver: str
    """QDash backend driver that runs this System (``qubex``)."""
    backend: str
    """Hardware kind inside the driver (``quel1`` or ``quel3`` for qubex)."""
    mux_ids: frozenset[int]
    settings: Mapping[str, Any]
    """The ``system.yaml`` entry, including the backend section."""


class SystemCatalog:
    """Chip -> Systems -> MUX -> wiring rows, read once per instance.

    Args:
        layout: Configuration tree to read.
        chip_id: QDash chip ID. Also selects the per-chip directory in the legacy layout.
        wiring_path: Optional ``wiring.yaml`` override (tests and explicit paths).

    """

    def __init__(
        self,
        layout: QubexLayout,
        chip_id: str,
        *,
        wiring_path: Path | str | None = None,
    ) -> None:
        if not chip_id or not chip_id.strip():
            raise ValueError("chip_id must not be empty")
        self.layout = layout
        self.chip_id = chip_id.strip()
        self._wiring_path = Path(wiring_path) if wiring_path is not None else None
        self._chip_dict: dict[str, Any] | None = None
        self._system_payload: dict[str, Any] | None = None
        self._wiring_dict: dict[str, Any] | None = None
        self._systems: list[SystemEntry] | None = None
        self._rows: list[dict[str, Any]] | None = None
        self._system_of_mux: dict[int, str] | None = None

    # ------------------------------------------------------------------ #
    # Files
    # ------------------------------------------------------------------ #

    @property
    def wiring_path(self) -> Path:
        """The ``wiring.yaml`` this catalog reads."""
        if self._wiring_path is not None:
            return self._wiring_path
        return self.layout.wiring_yaml(self.chip_id)

    def _load_optional(self, path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}
        return _load_mapping(path)

    def _chip_catalog(self) -> dict[str, Any]:
        if self._chip_dict is None:
            self._chip_dict = self._load_optional(self.layout.chip_yaml(self.chip_id))
        return self._chip_dict

    def _system_catalog(self) -> dict[str, Any]:
        if self._system_payload is None:
            self._system_payload = self._load_optional(self.layout.system_yaml(self.chip_id))
        return self._system_payload

    def _wiring(self) -> dict[str, Any]:
        if self._wiring_dict is None:
            path = self.wiring_path
            if not path.is_file():
                raise FileNotFoundError(f"Wiring config not found: {path}")
            self._wiring_dict = _load_mapping(path)
        return self._wiring_dict

    # ------------------------------------------------------------------ #
    # Systems
    # ------------------------------------------------------------------ #

    def systems(self) -> list[SystemEntry]:
        """The Systems that drive this chip, in ``system.yaml`` order."""
        if self._systems is None:
            self._systems = self._resolve_systems()
        return list(self._systems)

    def system_ids(self) -> list[str]:
        """IDs of :meth:`systems`."""
        return [entry.system_id for entry in self.systems()]

    def entry(self, system_id: str) -> SystemEntry:
        """The System with ``system_id``."""
        for item in self.systems():
            if item.system_id == system_id:
                return item
        raise KeyError(f"System {system_id!r} does not drive chip {self.chip_id}")

    def default_system_id(self) -> str:
        """The System named like the chip, else the only System."""
        systems = self.systems()
        for item in systems:
            if item.system_id == self.chip_id:
                return item.system_id
        if len(systems) == 1:
            return systems[0].system_id
        raise ValueError(
            f"Chip {self.chip_id} is driven by {len(systems)} Systems "
            f"({', '.join(s.system_id for s in systems)}); choose one explicitly"
        )

    @property
    def qubex_chip_id(self) -> str:
        """The chip ID Qubex uses for ``chip.yaml`` lookups."""
        return self.systems()[0].chip_id

    @property
    def is_implicit(self) -> bool:
        """Whether the System was synthesized because ``system.yaml`` has no catalog entry."""
        payload = self._system_catalog()
        return not payload or _looks_like_legacy_payload(payload)

    def _resolve_systems(self) -> list[SystemEntry]:
        payload = self._system_catalog()
        if not payload or _looks_like_legacy_payload(payload):
            configured_chip = payload.get("chip_id") if payload else None
            chip_id = str(configured_chip) if configured_chip else self.chip_id
            return [self._make_entry(self.chip_id, chip_id, payload)]

        same_name = payload.get(self.chip_id)
        if isinstance(same_name, dict):
            chip_id = str(same_name.get("chip_id") or self.chip_id)
            if chip_id != self.chip_id:
                # Alias: this QDash instance owns one System of a chip whose other
                # Systems belong to another instance (e.g. chip "144Qv3-quel3").
                return [self._make_entry(self.chip_id, chip_id, same_name)]

        matches = [
            (system_id, entry)
            for system_id, entry in payload.items()
            if isinstance(entry, dict) and str(entry.get("chip_id")) == self.chip_id
        ]
        if matches:
            return [
                self._make_entry(str(system_id), self.chip_id, entry)
                for system_id, entry in matches
            ]

        chips = self._chip_catalog()
        if chips and self.chip_id not in chips:
            raise LookupError(
                f"Chip {self.chip_id} is in neither system.yaml nor chip.yaml "
                f"under {self.layout.config_dir(self.chip_id)}"
            )
        return [self._make_entry(self.chip_id, self.chip_id, {})]

    def _make_entry(self, system_id: str, chip_id: str, settings: Mapping[str, Any]) -> SystemEntry:
        backend = settings.get("backend") if settings else None
        return SystemEntry(
            system_id=system_id,
            chip_id=chip_id,
            driver=DRIVER_QUBEX,
            backend=str(backend) if backend else DEFAULT_BACKEND,
            mux_ids=frozenset(self._mux_ids_for(system_id, chip_id)),
            settings=dict(settings) if settings else {},
        )

    # ------------------------------------------------------------------ #
    # Wiring
    # ------------------------------------------------------------------ #

    def _rows_for(self, system_id: str, chip_id: str) -> list[dict[str, Any]]:
        """Rows of one System: keyed by system_id, else chip_id, else legacy groups."""
        wiring = self._wiring()
        for key in dict.fromkeys((system_id, chip_id, self.chip_id)):
            if key not in wiring:
                continue
            rows = wiring[key]
            if rows is None:
                return []
            if not isinstance(rows, list):
                raise ValueError(f"{self.wiring_path}: {key!r} must map to a list of MUX rows")
            if any(not isinstance(row, dict) for row in rows):
                raise ValueError(
                    f"{self.wiring_path}: every MUX row under {key!r} must be a mapping"
                )
            return [dict(row) for row in rows]
        if self.is_implicit:
            # Legacy group-keyed wiring (for example "A2": [...]) of a single chip.
            groups = list(wiring.values())
            if any(not isinstance(group, list) for group in groups):
                raise ValueError(f"{self.wiring_path}: every top-level key must map to a list")
            rows = [row for group in groups for row in group]
            if any(not isinstance(row, dict) for row in rows):
                raise ValueError(f"{self.wiring_path}: every MUX row must be a mapping")
            return [dict(row) for row in rows]
        raise ValueError(f"{self.wiring_path}: no rows for System {system_id!r} (chip {chip_id!r})")

    def _mux_ids_for(self, system_id: str, chip_id: str) -> set[int]:
        seen: set[int] = set()
        for row in self._rows_for(system_id, chip_id):
            mux_id = row.get("mux")
            if type(mux_id) is not int or mux_id < 0:
                raise ValueError(
                    f"{self.wiring_path}: System {system_id!r} has a MUX row without a valid 'mux'"
                )
            if mux_id in seen:
                raise ValueError(
                    f"{self.wiring_path}: MUX {mux_id} appears twice in System {system_id!r}"
                )
            seen.add(mux_id)
        return seen

    def wiring_rows(self) -> list[dict[str, Any]]:
        """Wiring rows of every System of the chip, in file order.

        Raises:
            FileNotFoundError: If ``wiring.yaml`` is missing.
            ValueError: If the file is malformed or a MUX appears in two Systems.

        """
        if self._rows is None:
            rows: list[dict[str, Any]] = []
            owners: dict[int, str] = {}
            for item in self.systems():
                for row in self._rows_for(item.system_id, item.chip_id):
                    mux_id = row["mux"]
                    if mux_id in owners:
                        raise ValueError(
                            f"{self.wiring_path}: MUX {mux_id} is wired in Systems "
                            f"{owners[mux_id]!r} and {item.system_id!r}"
                        )
                    owners[mux_id] = item.system_id
                    rows.append(row)
            self._rows = rows
            self._system_of_mux = owners
        return [dict(row) for row in self._rows]

    def mux_ids(self) -> list[int]:
        """Every MUX wired for the chip, sorted."""
        self.wiring_rows()
        assert self._system_of_mux is not None
        return sorted(self._system_of_mux)

    def mux_size(self) -> int:
        """Qubits per MUX from ``chip.yaml`` ``topology.mux_size``, else 4."""
        chips = self._chip_catalog()
        entry = chips.get(self.qubex_chip_id) if chips else None
        topology = entry.get("topology") if isinstance(entry, dict) else None
        size = topology.get("mux_size") if isinstance(topology, dict) else None
        if type(size) is int and size > 0:
            return size
        return DEFAULT_MUX_SIZE

    def mux_of(self, qid: str) -> int:
        """MUX index of a qubit ID (its trailing digits divided by the MUX size)."""
        match = _TRAILING_DIGITS.search(str(qid).strip())
        if match is None:
            raise ValueError(f"Cannot derive a MUX from qubit ID {qid!r}")
        return int(match.group(1)) // self.mux_size()

    def qid_to_mux(self) -> dict[str, int]:
        """Qubit ID -> MUX for every wired MUX (``MUX n`` holds ``n*size .. n*size+size-1``)."""
        size = self.mux_size()
        return {
            str(mux_id * size + offset): mux_id
            for mux_id in self.mux_ids()
            for offset in range(size)
        }

    def system_of_mux(self, mux_id: int) -> str:
        """The System that wires ``mux_id``."""
        self.wiring_rows()
        assert self._system_of_mux is not None
        try:
            return self._system_of_mux[mux_id]
        except KeyError:
            raise KeyError(f"MUX {mux_id} is not wired for chip {self.chip_id}") from None

    def system_of_qid(self, qid: str) -> str:
        """The System that drives a single qubit."""
        return self.system_of_mux(self.mux_of(qid))

    def coupling_feasible(self, control: str, target: str) -> bool:
        """Whether both qubits of a coupling are driven by the same System."""
        if len(self.systems()) == 1:
            return True
        return self.system_of_qid(control) == self.system_of_qid(target)

    # ------------------------------------------------------------------ #
    # Target resolution
    # ------------------------------------------------------------------ #

    def resolve(self, qids: Iterable[str]) -> dict[str, list[str]]:
        """Group targets (``"0"`` or ``"0-1"``) by the System that drives them.

        Raises:
            CrossSystemCoupling: If a coupling's qubits belong to different Systems.
            KeyError: If a qubit's MUX is not wired for the chip.

        """
        assignment: dict[str, list[str]] = {}
        for target in qids:
            text = str(target).strip()
            parts = text.split("-") if "-" in text else [text]
            systems = [self.system_of_qid(part) for part in parts]
            if len(set(systems)) > 1:
                raise CrossSystemCoupling(self.chip_id, text, (systems[0], systems[1]))
            assignment.setdefault(systems[0], []).append(text)
        return assignment

    def resolve_muxes(self, mux_ids: Iterable[int]) -> dict[str, list[int]]:
        """Group MUX indexes by System."""
        assignment: dict[str, list[int]] = {}
        for mux_id in mux_ids:
            assignment.setdefault(self.system_of_mux(int(mux_id)), []).append(int(mux_id))
        return assignment

    def resolve_single(self, qids: Iterable[str], *, mux_ids: Iterable[int] | None = None) -> str:
        """The one System that drives every target.

        With no targets at all, the chip's :meth:`default_system_id` is returned.

        Raises:
            SystemSplitRequired: If the targets span several Systems.

        """
        assignment: dict[str, list[str]] = self.resolve(qids)
        if mux_ids is not None:
            for system_id, muxes in self.resolve_muxes(mux_ids).items():
                assignment.setdefault(system_id, []).extend(f"mux:{mux}" for mux in muxes)
        if not assignment:
            return self.default_system_id()
        if len(assignment) > 1:
            raise SystemSplitRequired(self.chip_id, assignment)
        return next(iter(assignment))

    # ------------------------------------------------------------------ #
    # Resources for execution locking
    # ------------------------------------------------------------------ #

    def mux_resources(self) -> dict[int, tuple[str, ...]]:
        """MUX -> module and channel resource names used for execution locking.

        Raises:
            ValueError: If a row lacks a usable ``ctrl`` list or ``read_out`` channel.

        """
        result: dict[int, tuple[str, ...]] = {}
        for entry in self.wiring_rows():
            mux_id = entry["mux"]
            ctrl = entry.get("ctrl")
            read_out = entry.get("read_out")
            if (
                not isinstance(ctrl, list)
                or not ctrl
                or any(not isinstance(channel, str) or not channel.strip() for channel in ctrl)
                or not isinstance(read_out, str)
                or not read_out.strip()
            ):
                raise ValueError(
                    f"{self.wiring_path}: MUX {mux_id} needs 'ctrl' channels and 'read_out'"
                )
            resources = mux_module_resources(entry)
            for key in ("ctrl", "read_out", "read_in", "pump"):
                value = entry.get(key)
                values = value if isinstance(value, list) else [value]
                for channel in values:
                    if channel in (None, ""):
                        continue
                    if not isinstance(channel, str):
                        raise ValueError(f"{self.wiring_path}: MUX {mux_id} {key} must be a string")
                    resources.add(f"channel:{channel}")
            result[mux_id] = tuple(sorted(resources))
        return result

    def resources_of(self, system_id: str) -> tuple[str, ...]:
        """Every lockable resource of one System (``mux:<id>`` plus modules and channels)."""
        item = self.entry(system_id)
        per_mux = self.mux_resources()
        resources = {f"mux:{mux_id}" for mux_id in item.mux_ids}
        for mux_id in item.mux_ids:
            resources.update(per_mux.get(mux_id, ()))
        return tuple(sorted(resources))


def _load_mapping(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: invalid YAML ({exc})") from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: top level must be a mapping")
    return raw


def _looks_like_legacy_payload(payload: Mapping[str, Any]) -> bool:
    """Whether ``system.yaml`` is the single-entry shape instead of a catalog."""
    return any(key in payload for key in _LEGACY_SYSTEM_KEYS)


def default_system_id(layout: QubexLayout, chip_id: str) -> str:
    """The System that owns a chip's parameter directory, or the chip ID itself.

    Falls back to ``chip_id`` when the configuration tree cannot be read (for
    example before the chip's files exist), which keeps the legacy
    ``<root>/<chip_id>/params`` location.
    """
    try:
        return SystemCatalog(layout, chip_id).default_system_id()
    except (OSError, ValueError, LookupError):
        return chip_id
