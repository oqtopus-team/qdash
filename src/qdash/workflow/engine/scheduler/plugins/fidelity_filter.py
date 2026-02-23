"""Fidelity filter for CR pair filtering."""

from __future__ import annotations

import logging
from typing import Any

from qdash.workflow.engine.scheduler.plugins.base import CRPairFilter, FilterContext

logger = logging.getLogger(__name__)


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
