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
# Qubits outside every MUX. The wiring only maps MUXes to hardware, so their
# physical resources are unknown and they run one at a time, after the MUX stages.
BOX_STANDALONE = "STANDALONE"


@dataclass
class OneQubitStageInfo:
    """Information about a single execution stage.

    Attributes:
        box_type: Type of box ("A", "B", "MIXED", or "STANDALONE")
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
class OneQubitRound:
    """One round of a ``parallel_by_round`` schedule.

    A round is a set of qubits from different MUXes. Each qubit of the round
    runs the step's full task list, and the next round starts only after every
    qubit of this round has finished. A round is not a per-task barrier and
    does not synchronize pulse timing.

    Attributes:
        round_index: Index of this round in the full schedule
        box_type: Type of box ("A", "B", "MIXED", or "STANDALONE")
        parallel_qids: Qubit IDs that run in parallel in this round
    """

    round_index: int
    box_type: str
    parallel_qids: list[str]

    def __repr__(self) -> str:
        """String representation."""
        return f"Round({self.round_index}, {self.box_type}, qids={len(self.parallel_qids)})"


@dataclass
class OneQubitRoundScheduleResult:
    """Schedule of rounds for the ``parallel_by_round`` execution mode.

    Unlike :class:`OneQubitScheduleResult`, where each MUX advances to its next
    qubit independently, every qubit of a round finishes before the next round
    starts.

    Structure:
        - rounds: the rounds in execution order
        - Grouped by box_type (A, B, MIXED): box stages run one after another
        - Within each box stage, rounds run one after another
        - Within each round, all qubits run in parallel

    Execution Flow:
        For Box A with checkerboard strategy:
        - Round 1: [0, 6, 8, 14, ...] in parallel (16 qubits)
        - Round 2: [1, 7, 9, 15, ...] in parallel (16 qubits)
        - Round 3: [2, 4, 10, 12, ...] in parallel (16 qubits)
        - Round 4: [3, 5, 11, 13, ...] in parallel (16 qubits)

    Attributes:
        rounds: Rounds in execution order, grouped by box type
        metadata: Statistics about the schedule
        mux_box_map: Mapping from MUX ID to box type(s)
        qid_to_mux: Mapping from qubit ID to MUX ID
    """

    rounds: list[OneQubitRound]
    metadata: dict[str, Any]
    mux_box_map: dict[int, set[str]]
    qid_to_mux: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format for serialization."""
        return {
            "rounds": [
                {
                    "round_index": round_.round_index,
                    "box_type": round_.box_type,
                    "parallel_qids": round_.parallel_qids,
                }
                for round_ in self.rounds
            ],
            "metadata": self.metadata,
        }

    def get_rounds_by_box(self, box_type: str) -> list[OneQubitRound]:
        """Get the rounds of a specific box type.

        Args:
            box_type: "A", "B", "MIXED", or "STANDALONE"

        Returns:
            List of rounds for the specified box type
        """
        return [round_ for round_ in self.rounds if round_.box_type == box_type]

    @property
    def total_rounds(self) -> int:
        """Total number of rounds."""
        return len(self.rounds)

    @property
    def box_types(self) -> list[str]:
        """List of unique box types in execution order."""
        seen = []
        for round_ in self.rounds:
            if round_.box_type not in seen:
                seen.append(round_.box_type)
        return seen

    def __repr__(self) -> str:
        """String representation."""
        total_qubits = sum(len(round_.parallel_qids) for round_ in self.rounds)
        return f"OneQubitRoundScheduleResult(qubits={total_qubits}, rounds={len(self.rounds)})"


@dataclass
class MuxBatchStepInfo:
    """Information about one MUX-batch execution step.

    Each batch contains qids from one MUX and should be executed by one
    Experiment/session. Batches within the same step can run in parallel.

    Attributes:
        step_index: Index of this step in the full schedule
        box_type: Type of box ("A", "B", or "MIXED")
        parallel_batches: MUX-based qid batches that can run in parallel
    """

    step_index: int
    box_type: str
    parallel_batches: list[list[str]]

    @property
    def parallel_qids(self) -> list[str]:
        """Flattened qids in this step."""
        return [qid for batch in self.parallel_batches for qid in batch]

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"MuxBatchStep({self.step_index}, {self.box_type}, "
            f"batches={len(self.parallel_batches)})"
        )


@dataclass
class MuxBatchScheduleResult:
    """Result object for MUX-batch scheduling.

    This result format is intended for simultaneous spectroscopy tasks where
    one experiment call handles all selected qids in one MUX.
    """

    steps: list[MuxBatchStepInfo]
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
                    "parallel_batches": step.parallel_batches,
                    "parallel_qids": step.parallel_qids,
                }
                for step in self.steps
            ],
            "metadata": self.metadata,
        }

    @property
    def total_steps(self) -> int:
        """Total number of MUX-batch steps."""
        return len(self.steps)

    @property
    def total_batches(self) -> int:
        """Total number of MUX batches across all steps."""
        return sum(len(step.parallel_batches) for step in self.steps)

    def get_steps_by_box(self, box_type: str) -> list[MuxBatchStepInfo]:
        """Get steps for a specific box type."""
        return [step for step in self.steps if step.box_type == box_type]

    def __repr__(self) -> str:
        """String representation."""
        total_qubits = sum(len(step.parallel_qids) for step in self.steps)
        return (
            f"MuxBatchScheduleResult(qubits={total_qubits}, "
            f"batches={self.total_batches}, steps={len(self.steps)})"
        )
