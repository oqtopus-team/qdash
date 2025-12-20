"""Target classes for calibration workflows.

This module defines the target abstraction for specifying which qubits,
MUXes, or coupling pairs to calibrate.

Example:
    from qdash.workflow.service import CalibService
    from qdash.workflow.service.targets import MuxTargets, QubitTargets

    # Target by MUX IDs
    targets = MuxTargets([0, 1, 2, 3])

    # Target specific qubits
    targets = QubitTargets(["0", "1", "4", "5"])

    # Use in calibration
    service = CalibService(username, chip_id)
    service.run(targets, steps=[...])
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from qdash.workflow.engine.backend.qubex_paths import get_qubex_paths


@dataclass
class Target(ABC):
    """Abstract base class for calibration targets.

    Targets define which qubits or coupling pairs to calibrate.
    They can be specified in various ways (MUX IDs, qubit IDs, etc.)
    and are resolved to concrete qubit lists when needed.
    """

    @abstractmethod
    def to_qids(self, chip_id: str) -> list[str]:
        """Convert target to a list of qubit IDs.

        Args:
            chip_id: Chip ID for resolving MUX-based targets

        Returns:
            List of qubit IDs
        """

    @abstractmethod
    def to_coupling_ids(self, chip_id: str) -> list[str]:
        """Convert target to a list of coupling IDs.

        Args:
            chip_id: Chip ID for resolving topology

        Returns:
            List of coupling IDs (e.g., ["0-1", "2-3"])
        """


@dataclass
class MuxTargets(Target):
    """Target qubits by MUX IDs.

    This is the most common way to specify targets for chip-wide calibration.
    MUX IDs are resolved to qubit IDs using the chip's wiring configuration.

    Attributes:
        mux_ids: List of MUX IDs to calibrate (0-15 for 64Q chip)
        exclude_qids: Qubit IDs to exclude from calibration

    Example:
        # Calibrate MUXes 0-3, excluding qubit 5
        targets = MuxTargets([0, 1, 2, 3], exclude_qids=["5"])
    """

    mux_ids: list[int]
    exclude_qids: list[str] = field(default_factory=list)

    def to_qids(self, chip_id: str) -> list[str]:
        """Resolve MUX IDs to qubit IDs using wiring configuration."""
        from qdash.workflow.engine import OneQubitScheduler

        wiring_config_path = str(get_qubex_paths().wiring_yaml(chip_id))
        scheduler = OneQubitScheduler(chip_id=chip_id, wiring_config_path=wiring_config_path)
        schedule = scheduler.generate_from_mux(
            mux_ids=self.mux_ids,
            exclude_qids=self.exclude_qids,
        )

        # Collect all qids from all stages
        all_qids = []
        for stage in schedule.stages:
            all_qids.extend(stage.qids)
        return sorted(set(all_qids))

    def to_coupling_ids(self, chip_id: str) -> list[str]:
        """Get coupling IDs for qubits in targeted MUXes."""
        from qdash.workflow.engine import CRScheduler

        qids = self.to_qids(chip_id)
        wiring_config_path = str(get_qubex_paths().wiring_yaml(chip_id))

        # Use CRScheduler to get valid coupling pairs
        # Note: This returns all possible pairs, filtering happens in steps
        scheduler = CRScheduler(
            username="",  # Not needed for pair generation
            chip_id=chip_id,
            wiring_config_path=wiring_config_path,
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

    def to_qids(self, chip_id: str) -> list[str]:
        """Return the qubit IDs directly."""
        return list(self.qids)

    def to_coupling_ids(self, chip_id: str) -> list[str]:
        """Get coupling IDs for the specified qubits."""
        from qdash.workflow.engine import CRScheduler

        wiring_config_path = str(get_qubex_paths().wiring_yaml(chip_id))
        scheduler = CRScheduler(
            username="",
            chip_id=chip_id,
            wiring_config_path=wiring_config_path,
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

    def to_qids(self, chip_id: str) -> list[str]:
        """Extract unique qubit IDs from coupling pairs."""
        qids = set()
        for control, target in self.pairs:
            qids.add(control)
            qids.add(target)
        return sorted(qids)

    def to_coupling_ids(self, chip_id: str) -> list[str]:
        """Return coupling IDs directly."""
        return [f"{c}-{t}" for c, t in self.pairs]


@dataclass
class AllMuxTargets(Target):
    """Target all MUXes (0-15) for full chip calibration.

    Convenience class for full chip calibration.

    Attributes:
        exclude_qids: Qubit IDs to exclude from calibration

    Example:
        targets = AllMuxTargets(exclude_qids=["5", "12"])
    """

    exclude_qids: list[str] = field(default_factory=list)

    def to_qids(self, chip_id: str) -> list[str]:
        """Resolve all MUXes to qubit IDs."""
        return MuxTargets(
            mux_ids=list(range(16)),
            exclude_qids=self.exclude_qids,
        ).to_qids(chip_id)

    def to_coupling_ids(self, chip_id: str) -> list[str]:
        """Get all coupling IDs for the chip."""
        return MuxTargets(
            mux_ids=list(range(16)),
            exclude_qids=self.exclude_qids,
        ).to_coupling_ids(chip_id)
