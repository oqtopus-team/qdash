"""Candidate qubit filter for CR pair filtering."""

from __future__ import annotations

import logging
from typing import Any

from qdash.workflow.engine.scheduler.plugins.base import CRPairFilter, FilterContext

logger = logging.getLogger(__name__)


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
