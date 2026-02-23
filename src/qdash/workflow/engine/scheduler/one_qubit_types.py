"""Type definitions for 1-Qubit Calibration Scheduler.

Contains box type constants and dataclasses used by OneQubitScheduler
and related components.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Box type constants
BOX_A = "A"
BOX_B = "B"
BOX_MIXED = "MIXED"  # Uses both A and B


@dataclass
class OneQubitStageInfo:
    """Information about a single execution stage.

    Attributes:
        box_type: Type of box ("A", "B", or "MIXED")
        qids: List of qubit IDs in this stage (executed sequentially if not using parallel_groups)
        mux_ids: Set of MUX IDs included in this stage
        parallel_groups: MUX-based parallel groups. Each group (list of qids) can run in parallel
                        with other groups, but qubits within the same group run sequentially.
                        Format: [[mux0_qids], [mux1_qids], ...]
    """

    box_type: str
    qids: list[str]
    mux_ids: set[int] = field(default_factory=set)
    parallel_groups: list[list[str]] = field(default_factory=list)

    def __repr__(self) -> str:
        """String representation."""
        return f"Stage(type={self.box_type}, qids={self.qids}, parallel_groups={len(self.parallel_groups)})"


@dataclass
class OneQubitScheduleResult:
    """Result object containing 1-qubit schedule and metadata.

    Attributes:
        stages: List of execution stages (executed sequentially between stages,
                qubits within each stage also executed sequentially due to box constraints)
        metadata: Statistics about the schedule
        mux_box_map: Mapping from MUX ID to box type(s)
        qid_to_mux: Mapping from qubit ID to MUX ID
    """

    stages: list[OneQubitStageInfo]
    metadata: dict[str, Any]
    mux_box_map: dict[int, set[str]]
    qid_to_mux: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format for serialization."""
        return {
            "stages": [
                {
                    "box_type": stage.box_type,
                    "qids": stage.qids,
                    "mux_ids": list(stage.mux_ids),
                    "parallel_groups": stage.parallel_groups,
                }
                for stage in self.stages
            ],
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:
        """String representation."""
        total_qubits = sum(len(stage.qids) for stage in self.stages)
        return f"OneQubitScheduleResult(qubits={total_qubits}, stages={len(self.stages)})"


@dataclass
class SynchronizedStepInfo:
    """Information about a single synchronized execution step.

    Each step contains qubits that can be executed simultaneously across
    all participating MUXes.

    Attributes:
        step_index: Index of this step within the stage (0-3)
        box_type: Type of box ("A", "B", or "MIXED")
        parallel_qids: List of qubit IDs to execute simultaneously in this step
    """

    step_index: int
    box_type: str
    parallel_qids: list[str]

    def __repr__(self) -> str:
        """String representation."""
        return f"Step({self.step_index}, {self.box_type}, qids={len(self.parallel_qids)})"


@dataclass
class SynchronizedOneQubitScheduleResult:
    """Result object for synchronized 1-qubit scheduling.

    This result format provides step-based parallelism where each step contains
    qubits that can be executed simultaneously. Unlike the original format where
    MUXes execute independently, this ensures all MUXes are synchronized at each step.

    Structure:
        - steps: List of synchronized steps, each with qubits to execute in parallel
        - Grouped by box_type (A, B, MIXED) - execute stages sequentially
        - Within each box stage, execute steps sequentially
        - Within each step, execute all qubits in parallel

    Execution Flow:
        For Box A with checkerboard strategy:
        - Step 1: Execute [0, 6, 8, 14, ...] simultaneously (16 qubits)
        - Step 2: Execute [1, 7, 9, 15, ...] simultaneously (16 qubits)
        - Step 3: Execute [2, 4, 10, 12, ...] simultaneously (16 qubits)
        - Step 4: Execute [3, 5, 11, 13, ...] simultaneously (16 qubits)

    Attributes:
        steps: List of synchronized steps grouped by box type
        metadata: Statistics about the schedule
        mux_box_map: Mapping from MUX ID to box type(s)
        qid_to_mux: Mapping from qubit ID to MUX ID
    """

    steps: list[SynchronizedStepInfo]
    metadata: dict[str, Any]
    mux_box_map: dict[int, set[str]]
    qid_to_mux: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format for serialization."""
        return {
            "steps": [
                {
                    "step_index": step.step_index,
                    "box_type": step.box_type,
                    "parallel_qids": step.parallel_qids,
                }
                for step in self.steps
            ],
            "metadata": self.metadata,
        }

    def get_steps_by_box(self, box_type: str) -> list[SynchronizedStepInfo]:
        """Get steps for a specific box type.

        Args:
            box_type: "A", "B", or "MIXED"

        Returns:
            List of steps for the specified box type
        """
        return [step for step in self.steps if step.box_type == box_type]

    @property
    def total_steps(self) -> int:
        """Total number of synchronized steps."""
        return len(self.steps)

    @property
    def box_types(self) -> list[str]:
        """List of unique box types in execution order."""
        seen = []
        for step in self.steps:
            if step.box_type not in seen:
                seen.append(step.box_type)
        return seen

    def __repr__(self) -> str:
        """String representation."""
        total_qubits = sum(len(step.parallel_qids) for step in self.steps)
        return f"SynchronizedOneQubitScheduleResult(qubits={total_qubits}, steps={len(self.steps)})"
