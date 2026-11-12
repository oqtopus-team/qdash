"""Target classes for calibration workflows.

This module defines the target abstraction for specifying which qubits,
MUXes, or coupling pairs to calibrate.

Example:
    from qdash.workflow.service import CalibService
    from qdash.workflow.service.targets import MuxTargets, QubitTargets

    # Target by MUX IDs
    targets = MuxTargets([0, 1, 2, 3])

    # Target every qubit of the chip, multiplexed or standalone
    targets = AllQubitTargets()

    # Target specific qubits
    targets = QubitTargets(["0", "1", "4", "5"])

    # Use in calibration
    service = CalibService(username, chip_id)
    service.run(targets, steps=[...])
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from qdash.common.mux_mapping import resolve_chip_mux_mapping
from qdash.workflow.engine.backend.qubex_paths import get_qubex_paths

if TYPE_CHECKING:
    from qdash.common.mux_mapping import MuxMapping

# MUX count assumed by AllMuxTargets when the chip has no topology (legacy 64Q).
LEGACY_ALL_MUX_COUNT = 16


@dataclass
class Target(ABC):
    """Abstract base class for calibration targets.

    Targets define which qubits or coupling pairs to calibrate.
    They can be specified in various ways (MUX IDs, qubit IDs, etc.)
    and are resolved to concrete qubit lists when needed.
    """

    @abstractmethod
    def to_qids(self, chip_id: str, *, mux_mapping: MuxMapping | None = None) -> list[str]:
        """Convert target to a list of qubit IDs.

        Args:
            chip_id: Chip ID for resolving MUX-based targets
            mux_mapping: MUX membership from the chip topology. If None, MUX
                targets use the legacy convention (MUX N = qubits 4N..4N+3).

        Returns:
            List of qubit IDs
        """

    @abstractmethod
    def to_coupling_ids(
        self,
        chip_id: str,
        *,
        project_id: str | None = None,
        mux_mapping: MuxMapping | None = None,
    ) -> list[str]:
        """Convert target to a list of coupling IDs.

        Args:
            chip_id: Chip ID for resolving topology
            project_id: Project of the chip
            mux_mapping: MUX membership; resolved from the chip topology if None

        Returns:
            List of coupling IDs (e.g., ["0-1", "2-3"])
        """


@dataclass
class MuxTargets(Target):
    """Target qubits by MUX IDs.

    This is the most common way to specify targets for chip-wide calibration.
    MUX IDs are resolved to qubit IDs through the chip topology's MUX
    mapping, restricted to MUXes present in the wiring configuration.

    Attributes:
        mux_ids: MUX IDs to calibrate, as defined by the chip topology
        exclude_qids: Qubit IDs to exclude from calibration

    Example:
        # Calibrate MUXes 0-3, excluding qubit 5
        targets = MuxTargets([0, 1, 2, 3], exclude_qids=["5"])
    """

    mux_ids: list[int]
    exclude_qids: list[str] = field(default_factory=list)

    def to_qids(self, chip_id: str, *, mux_mapping: MuxMapping | None = None) -> list[str]:
        """Resolve MUX IDs to qubit IDs using the MUX mapping and wiring."""
        from qdash.workflow.engine import OneQubitScheduler

        wiring_config_path = str(get_qubex_paths().wiring_yaml(chip_id))
        scheduler = OneQubitScheduler(
            chip_id=chip_id, wiring_config_path=wiring_config_path, mux_mapping=mux_mapping
        )
        schedule = scheduler.generate_from_mux(
            mux_ids=self.mux_ids,
            exclude_qids=self.exclude_qids,
        )

        # Collect all qids from all stages
        all_qids = []
        for stage in schedule.stages:
            all_qids.extend(stage.qids)
        return sorted(set(all_qids))

    def to_coupling_ids(
        self,
        chip_id: str,
        *,
        project_id: str | None = None,
        mux_mapping: MuxMapping | None = None,
    ) -> list[str]:
        """Get coupling IDs for qubits in targeted MUXes."""
        from qdash.workflow.engine import CRScheduler

        if not project_id:
            raise ValueError("project_id is required to resolve coupling targets")

        if mux_mapping is None:
            mux_mapping = resolve_chip_mux_mapping(project_id, chip_id)
        qids = self.to_qids(chip_id, mux_mapping=mux_mapping)
        wiring_config_path = str(get_qubex_paths().wiring_yaml(chip_id))

        # Use CRScheduler to get valid coupling pairs
        # Note: This returns all possible pairs, filtering happens in steps
        scheduler = CRScheduler(
            username="",  # Not needed for pair generation
            chip_id=chip_id,
            wiring_config_path=wiring_config_path,
            project_id=project_id,
            mux_mapping=mux_mapping,
        )
        schedule = scheduler.generate(candidate_qubits=qids, max_parallel_ops=100)

        coupling_ids = []
        for group in schedule.parallel_groups:
            for control, target in group:
                coupling_ids.append(f"{control}-{target}")
        return coupling_ids


@dataclass
class QubitTargets(Target):
    """Target specific qubits by ID.

    Use this when you want to calibrate specific qubits rather than
    entire MUXes.

    Attributes:
        qids: List of qubit IDs to calibrate

    Example:
        targets = QubitTargets(["0", "1", "4", "5", "8", "9"])
    """

    qids: list[str]

    def to_qids(self, chip_id: str, *, mux_mapping: MuxMapping | None = None) -> list[str]:
        """Return the qubit IDs directly."""
        return list(self.qids)

    def to_coupling_ids(
        self,
        chip_id: str,
        *,
        project_id: str | None = None,
        mux_mapping: MuxMapping | None = None,
    ) -> list[str]:
        """Get coupling IDs for the specified qubits."""
        from qdash.workflow.engine import CRScheduler

        if not project_id:
            raise ValueError("project_id is required to resolve coupling targets")

        wiring_config_path = str(get_qubex_paths().wiring_yaml(chip_id))
        scheduler = CRScheduler(
            username="",
            chip_id=chip_id,
            wiring_config_path=wiring_config_path,
            project_id=project_id,
            mux_mapping=mux_mapping,
        )
        schedule = scheduler.generate(candidate_qubits=self.qids, max_parallel_ops=100)

        coupling_ids = []
        for group in schedule.parallel_groups:
            for control, target in group:
                coupling_ids.append(f"{control}-{target}")
        return coupling_ids


@dataclass
class CouplingTargets(Target):
    """Target specific coupling pairs.

    Use this when you want to calibrate specific qubit pairs for
    2-qubit gate calibration.

    Attributes:
        pairs: List of (control, target) qubit ID tuples

    Example:
        targets = CouplingTargets([("0", "1"), ("4", "5"), ("8", "9")])
    """

    pairs: list[tuple[str, str]]

    def to_qids(self, chip_id: str, *, mux_mapping: MuxMapping | None = None) -> list[str]:
        """Extract unique qubit IDs from coupling pairs."""
        qids = set()
        for control, target in self.pairs:
            qids.add(control)
            qids.add(target)
        return sorted(qids)

    def to_coupling_ids(
        self,
        chip_id: str,
        *,
        project_id: str | None = None,
        mux_mapping: MuxMapping | None = None,
    ) -> list[str]:
        """Return coupling IDs directly."""
        return [f"{c}-{t}" for c, t in self.pairs]


@dataclass
class AllMuxTargets(Target):
    """Target every MUX of the chip for full chip calibration.

    The MUX list comes from the chip topology's MUX mapping: only declared
    MUXes, never the topology's standalone qubits. Chips without a topology
    keep the legacy MUXes 0-15. Use ``AllQubitTargets`` to include standalone
    qubits.

    Attributes:
        exclude_qids: Qubit IDs to exclude from calibration

    Example:
        targets = AllMuxTargets(exclude_qids=["5", "12"])
    """

    exclude_qids: list[str] = field(default_factory=list)

    @staticmethod
    def _mux_ids(mux_mapping: MuxMapping | None) -> list[int]:
        if mux_mapping is None or mux_mapping.unbounded:
            return list(range(LEGACY_ALL_MUX_COUNT))
        if not mux_mapping.mux_ids:
            msg = (
                "The chip topology declares no MUX, so AllMuxTargets selects nothing; "
                "use AllQubitTargets or QubitTargets for standalone qubits"
            )
            raise ValueError(msg)
        return mux_mapping.mux_ids

    def to_qids(self, chip_id: str, *, mux_mapping: MuxMapping | None = None) -> list[str]:
        """Resolve all MUXes to qubit IDs."""
        return MuxTargets(
            mux_ids=self._mux_ids(mux_mapping),
            exclude_qids=self.exclude_qids,
        ).to_qids(chip_id, mux_mapping=mux_mapping)

    def to_coupling_ids(
        self,
        chip_id: str,
        *,
        project_id: str | None = None,
        mux_mapping: MuxMapping | None = None,
    ) -> list[str]:
        """Get all coupling IDs for the chip."""
        if mux_mapping is None and project_id:
            mux_mapping = resolve_chip_mux_mapping(project_id, chip_id)
        return MuxTargets(
            mux_ids=self._mux_ids(mux_mapping),
            exclude_qids=self.exclude_qids,
        ).to_coupling_ids(chip_id, project_id=project_id, mux_mapping=mux_mapping)


@dataclass
class AllQubitTargets(Target):
    """Target every known qubit of the chip, multiplexed or standalone.

    Multiplexed qubits resolve like ``AllMuxTargets`` (members of the wired
    MUXes). Standalone qubits, which the topology lists in no MUX, are added
    as they are. The schedulers run them after the MUX stages, one at a time,
    because the wiring maps no hardware for them. Chips without a topology
    keep the legacy MUXes 0-15.

    Attributes:
        exclude_qids: Qubit IDs to exclude from calibration

    Example:
        targets = AllQubitTargets(exclude_qids=["5"])
    """

    exclude_qids: list[str] = field(default_factory=list)

    def to_qids(self, chip_id: str, *, mux_mapping: MuxMapping | None = None) -> list[str]:
        """Resolve the chip's MUX members and standalone qubits to qubit IDs."""
        if mux_mapping is None or mux_mapping.unbounded:
            return AllMuxTargets(exclude_qids=self.exclude_qids).to_qids(
                chip_id, mux_mapping=mux_mapping
            )
        excluded = set(self.exclude_qids)
        qids: list[str] = []
        if mux_mapping.mux_ids:
            qids = MuxTargets(mux_ids=mux_mapping.mux_ids, exclude_qids=self.exclude_qids).to_qids(
                chip_id, mux_mapping=mux_mapping
            )
        qids += [qid for qid in mux_mapping.standalone_qids if qid not in excluded]
        if not qids:
            msg = "All qubits were excluded"
            raise ValueError(msg)
        return sorted(set(qids), key=int)

    def to_coupling_ids(
        self,
        chip_id: str,
        *,
        project_id: str | None = None,
        mux_mapping: MuxMapping | None = None,
    ) -> list[str]:
        """Get coupling IDs among every known qubit of the chip."""
        if mux_mapping is None and project_id:
            mux_mapping = resolve_chip_mux_mapping(project_id, chip_id)
        return QubitTargets(qids=self.to_qids(chip_id, mux_mapping=mux_mapping)).to_coupling_ids(
            chip_id, project_id=project_id, mux_mapping=mux_mapping
        )
