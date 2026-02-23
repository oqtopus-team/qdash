"""Frequency directionality filter for CR pair filtering."""

from __future__ import annotations

import logging
from typing import Any

from qdash.workflow.engine.scheduler.plugins.base import CRPairFilter, FilterContext

logger = logging.getLogger(__name__)


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
