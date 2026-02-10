"""Plugin interfaces and implementations for CR Scheduler.

This module provides a pluggable architecture for CR gate scheduling, allowing
users to customize filtering and scheduling strategies.

Architecture:
    - CRPairFilter: Base class for filtering CR pairs
    - CRSchedulingStrategy: Base class for scheduling strategies
    - FilterContext/ScheduleContext: Context objects passed to plugins

Example:
    ```python
    from qdash.workflow.engine.scheduler.cr_scheduler import CRScheduler
    from qdash.workflow.engine.scheduler.plugins import (
        CandidateQubitFilter,
        FrequencyDirectionalityFilter,
        FidelityFilter,
        IntraThenInterMuxScheduler,
        MuxConflictScheduler,
    )

    # Custom filter pipeline
    filters = [
        CandidateQubitFilter(["0", "1", "2", "3"]),
        FrequencyDirectionalityFilter(use_design_based=True),
        FidelityFilter(min_fidelity=0.95),
    ]

    # Custom scheduler
    scheduler = IntraThenInterMuxScheduler(
        inner_scheduler=MuxConflictScheduler(
            max_parallel_ops=10,
            coloring_strategy="saturation_largest_first"
        )
    )

    cr_scheduler = CRScheduler(username="alice", chip_id="64Qv3")
    schedule = cr_scheduler.generate(filters=filters, scheduler=scheduler)
    ```
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qdash.datamodel.chip import ChipModel

logger = logging.getLogger(__name__)


@dataclass
class FilterContext:
    """Context object passed to CR pair filters.

    Attributes:
        chip: Current chip data (metadata only, for backwards compatibility)
        grid_size: Grid dimension (8 for 64-qubit, 12 for 144-qubit)
        qubit_frequency: Mapping from qubit ID to frequency (if available)
        qid_to_mux: Mapping from qubit ID to MUX ID
        qubit_models: Qubit data from individual QubitDocument collection (scalable)
        topology_directions: Pre-computed set of valid coupling directions from topology.
            If set, used by FrequencyDirectionalityFilter instead of design/measured methods.
    """

    chip: ChipModel
    grid_size: int
    qubit_frequency: dict[str, float] = field(default_factory=dict)
    qid_to_mux: dict[str, int] = field(default_factory=dict)
    qubit_models: dict[str, Any] = field(default_factory=dict)
    topology_directions: set[str] | None = None


@dataclass
class ScheduleContext:
    """Context object passed to CR scheduling strategies.

    Attributes:
        qid_to_mux: Mapping from qubit ID to MUX ID
        mux_conflict_map: MUX conflict relationships
    """

    qid_to_mux: dict[str, int]
    mux_conflict_map: dict[int, set[int]]


class CRPairFilter(ABC):
    """Base class for CR pair filtering strategies.

    Filters can be chained together to create complex filtering pipelines.
    Each filter receives a list of CR pairs and returns a filtered subset.
    """

    @abstractmethod
    def filter(self, pairs: list[str], context: FilterContext) -> list[str]:
        """Filter CR pairs based on specific criteria.

        Args:
            pairs: List of CR pair strings (e.g., ["0-1", "2-3"])
            context: Context object containing chip data and configuration

        Returns:
            Filtered list of CR pair strings
        """

    @abstractmethod
    def get_stats(self) -> dict[str, Any]:
        """Return filtering statistics.

        Returns:
            Dictionary containing filter-specific statistics
        """

    def __repr__(self) -> str:
        """String representation of the filter."""
        return f"{self.__class__.__name__}()"


class CRSchedulingStrategy(ABC):
    """Base class for CR pair scheduling strategies.

    Scheduling strategies determine how to group CR pairs into parallel
    execution groups while respecting hardware constraints.
    """

    @abstractmethod
    def schedule(self, pairs: list[str], context: ScheduleContext) -> list[list[str]]:
        """Group CR pairs into parallel execution groups.

        Args:
            pairs: List of CR pair strings to schedule
            context: Context object containing MUX configuration and conflicts

        Returns:
            List of groups where each group contains CR pairs that can run in parallel
        """

    @abstractmethod
    def get_metadata(self) -> dict[str, Any]:
        """Return scheduler metadata.

        Returns:
            Dictionary containing scheduler-specific metadata
        """

    def __repr__(self) -> str:
        """String representation of the scheduler."""
        return f"{self.__class__.__name__}()"


# ============================================================================
# Concrete Filter Implementations
# ============================================================================


class CandidateQubitFilter(CRPairFilter):
    """Filter CR pairs by candidate qubits.

    Only keeps pairs where both qubits are in the candidate set.
    Useful for filtering based on Stage 1 calibration results.

    Example:
        ```python
        # Only keep pairs involving high-quality qubits from Stage 1
        filter = CandidateQubitFilter(["0", "1", "2", "3"])
        filtered = filter.filter(["0-1", "2-5", "6-7"], context)
        # Result: ["0-1"] (only 0-1 has both qubits in candidate set)
        ```
    """

    def __init__(self, candidate_qubits: list[str] | None):
        """Initialize candidate qubit filter.

        Args:
            candidate_qubits: List of qubit IDs to include. If None, no filtering is applied.
        """
        self.candidate_qubits = set(candidate_qubits) if candidate_qubits else None
        self._filtered_count = 0
        self._total_count = 0

    def filter(self, pairs: list[str], context: FilterContext) -> list[str]:
        """Filter pairs by candidate qubits."""
        self._total_count = len(pairs)

        if self.candidate_qubits is None:
            self._filtered_count = self._total_count
            return pairs

        filtered = [
            pair
            for pair in pairs
            if (qubits := pair.split("-"))
            and len(qubits) == 2
            and qubits[0] in self.candidate_qubits
            and qubits[1] in self.candidate_qubits
        ]

        self._filtered_count = len(filtered)
        logger.info(f"CandidateQubitFilter: {self._total_count} → {self._filtered_count} pairs")
        return filtered

    def get_stats(self) -> dict[str, Any]:
        """Return filtering statistics."""
        return {
            "filter_name": "candidate_qubit",
            "input_pairs": self._total_count,
            "output_pairs": self._filtered_count,
            "candidate_qubits_count": len(self.candidate_qubits) if self.candidate_qubits else None,
        }

    def __repr__(self) -> str:
        """String representation."""
        count = len(self.candidate_qubits) if self.candidate_qubits else "all"
        return f"CandidateQubitFilter(qubits={count})"


class FrequencyDirectionalityFilter(CRPairFilter):
    """Filter CR pairs by frequency directionality.

    Uses topology-based direction, design-based inference, or measured frequencies
    to determine valid CR gate directions.

    Priority: topology > design-based > measured.

    Example:
        ```python
        # Use design-based inference (no frequency calibration needed)
        filter = FrequencyDirectionalityFilter(use_design_based=True)
        filtered = filter.filter(["0-1", "1-0"], context)

        # Use inverse direction (target→control)
        filter = FrequencyDirectionalityFilter(inverse=True)
        # With topology_directions set in context, selects reverse pairs
        filtered = filter.filter(["0-1", "1-0"], context)
        ```
    """

    def __init__(self, use_design_based: bool = False, inverse: bool = False):
        """Initialize frequency directionality filter.

        Args:
            use_design_based: If True, use design-based inference. If False, use measured frequencies.
            inverse: If True, select reverse-direction pairs. For measured directionality,
                inverts the frequency comparison (control freq > target freq).
        """
        self.use_design_based = use_design_based
        self.inverse = inverse
        self._filtered_count = 0
        self._total_count = 0
        self._method_used = "unknown"

    def filter(self, pairs: list[str], context: FilterContext) -> list[str]:
        """Filter pairs by frequency directionality."""
        self._total_count = len(pairs)

        # Priority: topology > design-based > measured
        if context.topology_directions is not None:
            filtered = self._filter_by_topology(pairs, context)
            self._method_used = "topology"
        elif self.use_design_based or len(context.qubit_frequency) == 0:
            filtered = self._filter_by_design(pairs, context)
            self._method_used = "design_based"
        else:
            filtered = self._filter_by_measurement(pairs, context)
            self._method_used = "measured"

        self._filtered_count = len(filtered)
        logger.info(
            f"FrequencyDirectionalityFilter ({self._method_used}, inverse={self.inverse}): "
            f"{self._total_count} → {self._filtered_count} pairs"
        )
        return filtered

    def _filter_by_topology(self, pairs: list[str], context: FilterContext) -> list[str]:
        """Filter using pre-computed topology direction set."""
        directions = context.topology_directions
        assert directions is not None  # caller guarantees this
        return [p for p in pairs if p in directions]

    def _filter_by_design(self, pairs: list[str], context: FilterContext) -> list[str]:
        """Filter using design-based checkerboard pattern."""
        from qdash.workflow.engine.scheduler.cr_scheduler import CRScheduler

        return [
            pair
            for pair in pairs
            if (qubits := pair.split("-"))
            and len(qubits) == 2
            and CRScheduler._infer_direction_from_design(qubits[0], qubits[1], context.grid_size)
        ]

    def _filter_by_measurement(self, pairs: list[str], context: FilterContext) -> list[str]:
        """Filter using measured qubit frequencies."""
        if self.inverse:
            return [
                pair
                for pair in pairs
                if (qubits := pair.split("-"))
                and len(qubits) == 2
                and qubits[0] in context.qubit_frequency
                and qubits[1] in context.qubit_frequency
                and context.qubit_frequency[qubits[0]] > context.qubit_frequency[qubits[1]]
            ]
        return [
            pair
            for pair in pairs
            if (qubits := pair.split("-"))
            and len(qubits) == 2
            and qubits[0] in context.qubit_frequency
            and qubits[1] in context.qubit_frequency
            and context.qubit_frequency[qubits[0]] < context.qubit_frequency[qubits[1]]
        ]

    def get_stats(self) -> dict[str, Any]:
        """Return filtering statistics."""
        return {
            "filter_name": "frequency_directionality",
            "input_pairs": self._total_count,
            "output_pairs": self._filtered_count,
            "method": self._method_used,
            "inverse": self.inverse,
        }

    def __repr__(self) -> str:
        """String representation."""
        method = "design" if self.use_design_based else "measured"
        return f"FrequencyDirectionalityFilter(method={method}, inverse={self.inverse})"


class FidelityFilter(CRPairFilter):
    """Filter CR pairs by qubit fidelity threshold.

    Only keeps pairs where both qubits meet the minimum fidelity requirement.

    Example:
        ```python
        # Only keep pairs with high-fidelity qubits
        filter = FidelityFilter(min_fidelity=0.95)
        filtered = filter.filter(["0-1", "2-3"], context)
        ```
    """

    def __init__(self, min_fidelity: float, fidelity_key: str = "x90_fidelity"):
        """Initialize fidelity filter.

        Args:
            min_fidelity: Minimum fidelity threshold (0.0 to 1.0)
            fidelity_key: Key to use for fidelity lookup in qubit data
        """
        self.min_fidelity = min_fidelity
        self.fidelity_key = fidelity_key
        self._filtered_count = 0
        self._total_count = 0

    def filter(self, pairs: list[str], context: FilterContext) -> list[str]:
        """Filter pairs by qubit fidelity."""
        self._total_count = len(pairs)

        # Extract fidelity data from individual QubitDocument models (scalable)
        fidelity_map = {}
        for qid, qubit in context.qubit_models.items():
            if qubit.data and self.fidelity_key in qubit.data:
                fidelity_map[qid] = qubit.data[self.fidelity_key].get("value", 0.0)

        # Filter by fidelity
        filtered = [
            pair
            for pair in pairs
            if (qubits := pair.split("-"))
            and len(qubits) == 2
            and qubits[0] in fidelity_map
            and qubits[1] in fidelity_map
            and fidelity_map[qubits[0]] >= self.min_fidelity
            and fidelity_map[qubits[1]] >= self.min_fidelity
        ]

        self._filtered_count = len(filtered)
        logger.info(
            f"FidelityFilter (≥{self.min_fidelity}): {self._total_count} → {self._filtered_count} pairs"
        )
        return filtered

    def get_stats(self) -> dict[str, Any]:
        """Return filtering statistics."""
        return {
            "filter_name": "fidelity",
            "input_pairs": self._total_count,
            "output_pairs": self._filtered_count,
            "min_fidelity": self.min_fidelity,
            "fidelity_key": self.fidelity_key,
        }

    def __repr__(self) -> str:
        """String representation."""
        return f"FidelityFilter(min={self.min_fidelity})"


# ============================================================================
# Concrete Scheduler Implementations
# ============================================================================


class MuxConflictScheduler(CRSchedulingStrategy):
    """Schedule CR pairs based on MUX resource conflicts.

    Uses graph coloring to group pairs that can execute in parallel without
    MUX resource conflicts.

    Example:
        ```python
        scheduler = MuxConflictScheduler(
            max_parallel_ops=10,
            coloring_strategy="saturation_largest_first"
        )
        groups = scheduler.schedule(["0-1", "2-3", "4-5"], context)
        ```
    """

    def __init__(self, max_parallel_ops: int = 10, coloring_strategy: str = "largest_first"):
        """Initialize MUX conflict scheduler.

        Args:
            max_parallel_ops: Maximum parallel operations per group
            coloring_strategy: NetworkX graph coloring strategy
        """
        self.max_parallel_ops = max_parallel_ops
        self.coloring_strategy = coloring_strategy
        self._num_groups = 0

    def schedule(self, pairs: list[str], context: ScheduleContext) -> list[list[str]]:
        """Schedule pairs using graph coloring."""
        from qdash.workflow.engine.scheduler.cr_scheduler import CRScheduler

        groups = CRScheduler._group_cr_pairs_by_conflict(
            pairs,
            context.qid_to_mux,
            context.mux_conflict_map,
            self.max_parallel_ops,
            self.coloring_strategy,
        )

        self._num_groups = len(groups)
        logger.info(
            f"MuxConflictScheduler: {len(pairs)} pairs → {self._num_groups} groups "
            f"(strategy={self.coloring_strategy})"
        )
        return list(groups)

    def get_metadata(self) -> dict[str, Any]:
        """Return scheduler metadata."""
        return {
            "scheduler_name": "mux_conflict",
            "max_parallel_ops": self.max_parallel_ops,
            "coloring_strategy": self.coloring_strategy,
            "num_groups": self._num_groups,
        }

    def __repr__(self) -> str:
        """String representation."""
        return f"MuxConflictScheduler(max_ops={self.max_parallel_ops}, strategy={self.coloring_strategy})"


class IntraThenInterMuxScheduler(CRSchedulingStrategy):
    """Schedule with intra-MUX pairs first, then inter-MUX pairs.

    Delegates to an inner scheduler for grouping within each category.

    Example:
        ```python
        scheduler = IntraThenInterMuxScheduler(
            inner_scheduler=MuxConflictScheduler(max_parallel_ops=10)
        )
        groups = scheduler.schedule(["0-1", "0-4", "4-5"], context)
        ```
    """

    def __init__(self, inner_scheduler: CRSchedulingStrategy):
        """Initialize intra-then-inter MUX scheduler.

        Args:
            inner_scheduler: Scheduler to use for both intra-MUX and inter-MUX pairs
        """
        self.inner_scheduler = inner_scheduler
        self._fast_count = 0
        self._slow_count = 0

    def schedule(self, pairs: list[str], context: ScheduleContext) -> list[list[str]]:
        """Schedule with intra-MUX pairs first, then inter-MUX pairs."""
        from qdash.workflow.engine.scheduler.cr_scheduler import CRScheduler

        # Split into intra-MUX and inter-MUX pairs
        intra_mux, inter_mux = CRScheduler._split_fast_slow_pairs(pairs, context.qid_to_mux)
        self._fast_count = len(intra_mux)
        self._slow_count = len(inter_mux)

        # Schedule each category
        intra_groups = self.inner_scheduler.schedule(intra_mux, context) if intra_mux else []
        inter_groups = self.inner_scheduler.schedule(inter_mux, context) if inter_mux else []

        logger.info(
            f"IntraThenInterMuxScheduler: {self._fast_count} intra-MUX, {self._slow_count} inter-MUX pairs"
        )
        return intra_groups + inter_groups

    def get_metadata(self) -> dict[str, Any]:
        """Return scheduler metadata."""
        return {
            "scheduler_name": "intra_then_inter_mux",
            "intra_mux_pairs": self._fast_count,
            "inter_mux_pairs": self._slow_count,
            "inner_scheduler": repr(self.inner_scheduler),
        }

    def __repr__(self) -> str:
        """String representation."""
        return f"IntraThenInterMuxScheduler(inner={self.inner_scheduler})"
