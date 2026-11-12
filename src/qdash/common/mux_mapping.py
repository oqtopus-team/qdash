"""Resolve which qubits share a MUX, on which local slot, and which stand alone.

The chip's topology template is the single source of MUX membership for the
UI, the schedulers, execution locks and MUX result fan-out. ``wiring.yaml``
stays the MUX -> hardware map and is joined by MUX ID; a qubit's local slot
is the index of its control port in that MUX's ``ctrl`` list.

Resolution policy:

* A topology uses its ``muxes`` exactly (legacy ``mux:`` blocks are normalized
  by ``qdash.common.config.topology``). A known qubit that no MUX lists is
  *standalone*: a valid calibration target that is not multiplexed. A qubit
  the topology does not define is *unknown*. Nothing falls back to arithmetic.
* A chip without ``topology_id``, or an unknown chip, keeps the historical
  unbounded convention (MUX ``qid // 4`` on slot ``qid % 4``) so existing
  chips continue to schedule as before.
* A chip whose ``topology_id`` cannot be loaded or validated raises
  ``MuxMappingError``. Callers must not schedule hardware from a guess; the
  execution lock claims the whole chip instead.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from pydantic import ValidationError

from qdash.common.config.topology import LEGACY_QUBITS_PER_MUX, load_topology

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from qdash.common.config.topology import TopologyDefinition

logger = logging.getLogger(__name__)

MuxMappingSource = Literal["explicit", "legacy_topology", "legacy"]


class MuxMappingError(ValueError):
    """MUX membership cannot be resolved, or a target is outside it."""


def _qid_number(qid: str | int) -> int:
    """Return the integer qubit index of ``qid`` (``"7"``, ``"Q07"`` or ``7``)."""
    if isinstance(qid, int):
        if qid < 0:
            raise MuxMappingError(f"Invalid qubit ID: {qid}")
        return qid
    match = re.fullmatch(r"[A-Za-z]*0*(\d+)", str(qid).strip())
    if match is None:
        raise MuxMappingError(f"Invalid qubit ID: {qid!r}")
    return int(match.group(1))


@dataclass(frozen=True)
class MuxMapping:
    """Resolved MUX membership with local slots and the known qubits.

    ``groups`` maps MUX ID to member qubits (string IDs) in local slot order.
    ``known_qids`` holds every qubit the topology defines, multiplexed or
    standalone. With ``unbounded=True`` (legacy chips without a topology) any
    non-negative qubit or MUX resolves by the legacy arithmetic; ``groups`` is
    then empty and ``known_qids`` is ``None``.
    """

    groups: Mapping[int, tuple[str, ...]]
    source: MuxMappingSource
    topology_id: str | None = None
    unbounded: bool = False
    known_qids: frozenset[str] | None = None
    _slots: Mapping[str, int] = field(default_factory=dict, repr=False, compare=False)
    _owner: Mapping[str, int] = field(default_factory=dict, repr=False, compare=False)

    # ------------------------------------------------------------------ build

    @classmethod
    def from_groups(
        cls,
        groups: Mapping[int, Iterable[str | int]],
        *,
        source: MuxMappingSource = "explicit",
        topology_id: str | None = None,
        slots: Mapping[str, int] | None = None,
        known_qids: Iterable[str | int] | None = None,
    ) -> MuxMapping:
        """Build a bounded mapping; each member list is in local slot order.

        ``known_qids`` adds standalone qubits: known qubits outside every MUX.
        It defaults to the MUX members (no standalone qubit).
        """
        normalized: dict[int, tuple[str, ...]] = {}
        owner: dict[str, int] = {}
        slot_of: dict[str, int] = {}
        for mux_id in sorted(groups):
            if type(mux_id) is not int or mux_id < 0:
                raise MuxMappingError(f"Invalid MUX ID: {mux_id!r}")
            members = tuple(str(_qid_number(qid)) for qid in groups[mux_id])
            if not members:
                raise MuxMappingError(f"MUX {mux_id} has no qubits")
            for index, qid in enumerate(members):
                if qid in owner:
                    raise MuxMappingError(
                        f"Qubit {qid} is assigned to both MUX {owner[qid]} and MUX {mux_id}"
                    )
                owner[qid] = mux_id
                slot_of[qid] = slots[qid] if slots is not None else index
            normalized[mux_id] = members
        known = set(owner)
        if known_qids is not None:
            declared = {str(_qid_number(qid)) for qid in known_qids}
            unknown_members = sorted(known - declared, key=int)
            if unknown_members:
                raise MuxMappingError(f"MUX members are not known qubits: {unknown_members}")
            known = declared
        return cls(
            groups=normalized,
            source=source,
            topology_id=topology_id,
            known_qids=frozenset(known),
            _slots=slot_of,
            _owner=owner,
        )

    @classmethod
    def legacy(cls) -> MuxMapping:
        """Historical convention for chips without a topology: MUX N = 4N..4N+3."""
        return cls(groups={}, source="legacy", unbounded=True)

    @classmethod
    def from_topology(cls, topology: TopologyDefinition) -> MuxMapping:
        """Mapping for a validated topology, including its standalone qubits."""
        legacy_layout = topology.muxes_source == "legacy_qid_div_4"
        return cls.from_groups(
            topology.muxes,
            source="legacy_topology" if legacy_layout else "explicit",
            topology_id=topology.id,
            slots={str(qid): slot for qid, slot in topology.mux_slots().items()},
            known_qids=topology.qubits,
        )

    # ----------------------------------------------------------------- lookup

    @property
    def is_explicit(self) -> bool:
        """Whether membership comes from the template's declared MUXes."""
        return self.source == "explicit"

    @property
    def mux_ids(self) -> list[int]:
        """Known MUX IDs in ascending order (empty for the unbounded legacy mapping)."""
        return sorted(self.groups)

    @property
    def standalone_qids(self) -> list[str]:
        """Known qubits outside every MUX, in ascending numeric order."""
        if self.unbounded or self.known_qids is None:
            return []
        return sorted((qid for qid in self.known_qids if qid not in self._owner), key=int)

    @property
    def all_qids(self) -> list[str]:
        """Every known qubit in ascending numeric order (empty when unbounded)."""
        if self.unbounded or self.known_qids is None:
            return []
        return sorted(self.known_qids, key=int)

    def is_known(self, qid: str | int) -> bool:
        """Whether ``qid`` is a qubit of this chip (multiplexed or standalone)."""
        try:
            number = _qid_number(qid)
        except MuxMappingError:
            return False
        if self.unbounded:
            return True
        return self.known_qids is not None and str(number) in self.known_qids

    def is_standalone(self, qid: str | int) -> bool:
        """Whether ``qid`` is a known qubit that no MUX lists."""
        return self.is_known(qid) and self.find_mux(qid) is None

    def find_mux(self, qid: str | int) -> int | None:
        """MUX ID of ``qid``, or ``None`` when it is standalone or unknown."""
        try:
            number = _qid_number(qid)
        except MuxMappingError:
            return None
        if self.unbounded:
            return number // LEGACY_QUBITS_PER_MUX
        return self._owner.get(str(number))

    def mux_of(self, qid: str | int) -> int:
        """MUX ID of ``qid``; raises ``MuxMappingError`` when standalone or unknown."""
        mux_id = self.find_mux(qid)
        if mux_id is None:
            raise MuxMappingError(self._not_in_mux_message(qid))
        return mux_id

    def slot_of(self, qid: str | int) -> int:
        """Local slot of ``qid`` in its MUX; raises when standalone or unknown."""
        number = _qid_number(qid)
        if self.unbounded:
            return number % LEGACY_QUBITS_PER_MUX
        slot = self._slots.get(str(number))
        if slot is None:
            raise MuxMappingError(self._not_in_mux_message(qid))
        return slot

    def has_mux(self, mux_id: int) -> bool:
        """Whether ``mux_id`` is a known MUX."""
        return (self.unbounded and mux_id >= 0) or mux_id in self.groups

    def qids_of(self, mux_id: int) -> tuple[str, ...]:
        """Members of ``mux_id`` in local slot order; raises when the MUX is unknown."""
        if self.unbounded:
            if mux_id < 0:
                raise MuxMappingError(f"Invalid MUX ID: {mux_id}")
            base = mux_id * LEGACY_QUBITS_PER_MUX
            return tuple(str(base + offset) for offset in range(LEGACY_QUBITS_PER_MUX))
        members = self.groups.get(mux_id)
        if members is None:
            raise MuxMappingError(f"MUX {mux_id} is not defined in {self._label()}")
        return members

    def slots_of(self, mux_id: int) -> dict[int, str]:
        """Local slot -> qubit for ``mux_id``."""
        return {self.slot_of(qid): qid for qid in self.qids_of(mux_id)}

    def qids_for_muxes(
        self, mux_ids: Iterable[int], exclude_qids: Iterable[str] | None = None
    ) -> list[str]:
        """Members of ``mux_ids`` in MUX-then-slot order, minus ``exclude_qids``."""
        excluded = {str(qid) for qid in exclude_qids or ()}
        return [qid for mux_id in mux_ids for qid in self.qids_of(mux_id) if qid not in excluded]

    def mux_ids_for_qids(self, qids: Iterable[str | int]) -> list[int]:
        """Sorted MUX IDs that own ``qids``; raises when any qubit is standalone or unknown."""
        return sorted({self.mux_of(qid) for qid in qids})

    def partition_qids(self, qids: Iterable[str | int]) -> tuple[list[int], list[str]]:
        """Split ``qids`` into the MUX IDs that own them and the standalone qubits.

        Returns sorted MUX IDs and standalone qubit IDs in ascending order.
        Raises ``MuxMappingError`` when a qubit is not defined.
        """
        mux_ids: set[int] = set()
        standalone: set[str] = set()
        for qid in qids:
            if not self.is_known(qid):
                raise MuxMappingError(f"Qubit {qid} is not defined in {self._label()}")
            mux_id = self.find_mux(qid)
            if mux_id is None:
                standalone.add(str(_qid_number(qid)))
            else:
                mux_ids.add(mux_id)
        return sorted(mux_ids), sorted(standalone, key=int)

    def qid_to_mux(self, mux_ids: Iterable[int] | None = None) -> dict[str, int]:
        """Qubit -> MUX for ``mux_ids`` (default: every known MUX)."""
        selected = self.mux_ids if mux_ids is None else list(mux_ids)
        return {qid: mux_id for mux_id in selected for qid in self.qids_of(mux_id)}

    def groups_for_qubit_count(self, num_qubits: int) -> dict[int, tuple[str, ...]]:
        """Every MUX for a chip of ``num_qubits`` (bounded mappings ignore the count)."""
        if not self.unbounded:
            return dict(self.groups)
        mux_count = -(-num_qubits // LEGACY_QUBITS_PER_MUX)
        return {
            mux_id: tuple(qid for qid in self.qids_of(mux_id) if int(qid) < num_qubits)
            for mux_id in range(mux_count)
        }

    def qids_for_qubit_count(self, num_qubits: int) -> list[str]:
        """Every known qubit (bounded) or ``0..num_qubits-1`` (unbounded legacy)."""
        if self.unbounded:
            return [str(qid) for qid in range(num_qubits)]
        return self.all_qids

    def _not_in_mux_message(self, qid: str | int) -> str:
        if self.is_known(qid):
            return f"Qubit {qid} is standalone (not multiplexed) in {self._label()}"
        return f"Qubit {qid} is not defined in {self._label()}"

    # ----------------------------------------------------------------- wiring

    def wiring_errors(self, wiring_entries: Iterable[Mapping[str, Any]]) -> list[str]:
        """Inconsistencies between this mapping and ``wiring.yaml`` MUX rows.

        A MUX row may have fewer qubits than control ports, but every member
        slot needs a control port. MUXes missing from the wiring are not
        reported here: callers decide whether a targeted MUX needs wiring.
        """
        errors: list[str] = []
        for entry in wiring_entries:
            mux_id = entry.get("mux")
            if type(mux_id) is not int or not self.has_mux(mux_id) or self.unbounded:
                continue
            ctrl = entry.get("ctrl")
            ports = len(ctrl) if isinstance(ctrl, list) else 0
            for qid in self.groups[mux_id]:
                if self.slot_of(qid) >= ports:
                    errors.append(
                        f"MUX {mux_id} qubit {qid} uses slot {self.slot_of(qid)} but "
                        f"wiring lists {ports} control port(s)"
                    )
        return errors

    def check_wiring(self, wiring_entries: Iterable[Mapping[str, Any]]) -> None:
        """Raise ``MuxMappingError`` when the mapping contradicts ``wiring.yaml``."""
        errors = self.wiring_errors(wiring_entries)
        if errors:
            raise MuxMappingError("; ".join(errors))

    def _label(self) -> str:
        return f"topology {self.topology_id}" if self.topology_id else "the MUX mapping"


def resolve_topology_mux_mapping(topology_id: str | None) -> MuxMapping:
    """Mapping for ``topology_id``; ``None`` keeps the unbounded legacy mapping.

    Raises ``MuxMappingError`` when the template is missing or invalid.
    """
    if not topology_id:
        return MuxMapping.legacy()
    try:
        topology = load_topology(topology_id)
    except FileNotFoundError as exc:
        raise MuxMappingError(f"Topology {topology_id!r} not found") from exc
    except (ValidationError, ValueError, TypeError) as exc:
        raise MuxMappingError(f"Topology {topology_id!r} is invalid: {exc}") from exc
    return MuxMapping.from_topology(topology)


def resolve_chip_mux_mapping(project_id: str | None, chip_id: str) -> MuxMapping:
    """Mapping for a chip via its ``topology_id``, scoped to ``project_id``.

    Chips without a topology (or without project context) keep the legacy
    convention; a configured but unusable topology raises ``MuxMappingError``.
    """
    if not project_id or not chip_id:
        logger.warning(
            "No project context for chip %r; using the legacy qid // 4 MUX mapping", chip_id
        )
        return MuxMapping.legacy()
    from qdash.dbmodel.chip import ChipDocument

    try:
        chip = ChipDocument.find_one({"project_id": project_id, "chip_id": chip_id}).run()
    except Exception as exc:
        raise MuxMappingError(f"Could not load chip {chip_id!r}: {exc}") from exc
    if chip is None:
        logger.warning(
            "Chip %r not found in project %r; using the legacy qid // 4 MUX mapping",
            chip_id,
            project_id,
        )
        return MuxMapping.legacy()
    return resolve_topology_mux_mapping(chip.topology_id)


# ---------------------------------------------------------------------- Qubex

QUBEX_MUX_SIZE = LEGACY_QUBITS_PER_MUX
"""Qubits per MUX that Qubex assumes (``qubex.constants.MUX_SIZE``)."""


def qubex_mux_mapping_errors(mapping: MuxMapping) -> list[str]:
    """Ways ``mapping`` disagrees with the MUX layout Qubex derives on its own.

    Qubex does not read QDash topologies. It places qubit index ``i`` in MUX
    ``i // 4`` on control slot ``i % 4`` (``LatticeGraph.get_mux_of_qubit``,
    ``get_indices_in_mux``), and binds each ``wiring.yaml`` ``ctrl`` port to
    that qubit. A mapping is compatible only when no known qubit is standalone
    and every MUX ``N`` lists a prefix of ``[4N, 4N+1, 4N+2, 4N+3]`` in that
    order, so that QDash's MUX and slot for each qubit are the ones Qubex
    drives. Qubex has no notion of a non-multiplexed qubit, so a standalone
    qubit is never treated as if it were in MUX ``i // 4``.
    """
    if mapping.unbounded or mapping.source == "legacy_topology":
        # The legacy conventions are Qubex's own layout by construction.
        return []
    errors: list[str] = []
    standalone = mapping.standalone_qids
    if standalone:
        errors.append(
            f"qubits [{', '.join(standalone)}] are standalone (in no MUX), which Qubex cannot drive"
        )
    for mux_id in mapping.mux_ids:
        members = mapping.qids_of(mux_id)
        expected = tuple(str(QUBEX_MUX_SIZE * mux_id + slot) for slot in range(QUBEX_MUX_SIZE))
        if len(members) > QUBEX_MUX_SIZE or members != expected[: len(members)]:
            errors.append(
                f"MUX {mux_id} lists qubits [{', '.join(members)}] but Qubex drives "
                f"[{', '.join(expected[: len(members)])}] in that slot order"
            )
    return errors


def check_qubex_mux_mapping(mapping: MuxMapping) -> None:
    """Raise ``MuxMappingError`` when Qubex would drive different MUXes or slots.

    Call this before a Qubex ``Experiment`` is built or connected. Other
    backends accept any valid mapping and must not call it.
    """
    errors = qubex_mux_mapping_errors(mapping)
    if errors:
        raise MuxMappingError(
            f"The MUX layout of {mapping._label()} is not supported by the Qubex backend: "
            + "; ".join(errors)
            + ". Qubex assigns qubit i to MUX i // 4 on slot i % 4, so each MUX N must list "
            "qubits 4N, 4N+1, 4N+2, 4N+3 in this order (trailing qubits may be omitted) and "
            "every qubit must belong to a MUX. Edit muxes in the topology template, or run "
            "the chip on a non-Qubex backend."
        )
