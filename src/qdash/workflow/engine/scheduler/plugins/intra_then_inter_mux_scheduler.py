"""Intra-then-inter MUX scheduler for CR pair scheduling."""

from __future__ import annotations

import logging
from typing import Any

from qdash.workflow.engine.scheduler.plugins.base import CRSchedulingStrategy, ScheduleContext

logger = logging.getLogger(__name__)


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
