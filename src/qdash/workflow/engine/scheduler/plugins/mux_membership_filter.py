"""MUX membership filter for CR pair filtering."""

from __future__ import annotations

import logging
from typing import Any

from qdash.workflow.engine.scheduler.plugins.base import CRPairFilter, FilterContext

logger = logging.getLogger(__name__)


class MuxMembershipFilter(CRPairFilter):
    """Filter CR pairs to only those with qubits present in MUX configuration.

    Removes pairs where either qubit is not found in the qid_to_mux mapping,
    which indicates the qubit is not part of the active MUX configuration.

    This filter is useful as a preparatory step before MUX-based scheduling,
    ensuring all remaining pairs can be properly assigned to MUX groups.

    Example:
        ```python
        filter = MuxMembershipFilter()
        # If qid_to_mux = {"0": 0, "1": 0, "2": 0, "3": 0}
        filtered = filter.filter(["0-1", "0-5", "2-3"], context)
        # Result: ["0-1", "2-3"] (pair "0-5" removed because qubit 5 is not in MUX config)
        ```
    """

    def __init__(self) -> None:
        """Initialize MUX membership filter."""
        self._input = 0
        self._output = 0

    def filter(self, pairs: list[str], context: FilterContext) -> list[str]:
        """Filter pairs to those with both qubits in MUX configuration."""
        self._input = len(pairs)

        filtered = [
            pair for pair in pairs if all(qid in context.qid_to_mux for qid in pair.split("-"))
        ]

        self._output = len(filtered)
        if self._input != self._output:
            logger.warning(
                f"MuxMembershipFilter: filtered {self._input - self._output} pairs "
                f"with qubits missing from MUX config ({self._input} → {self._output})"
            )
        return filtered

    def get_stats(self) -> dict[str, Any]:
        """Return filtering statistics."""
        return {
            "filter_name": "mux_membership",
            "input_pairs": self._input,
            "output_pairs": self._output,
            "filtered_count": self._input - self._output,
        }

    def __repr__(self) -> str:
        """String representation."""
        return "MuxMembershipFilter()"
