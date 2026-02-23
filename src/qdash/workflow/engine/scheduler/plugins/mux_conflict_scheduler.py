"""MUX conflict scheduler for CR pair scheduling."""

from __future__ import annotations

import logging
from typing import Any

from qdash.workflow.engine.scheduler.plugins.base import CRSchedulingStrategy, ScheduleContext

logger = logging.getLogger(__name__)


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
