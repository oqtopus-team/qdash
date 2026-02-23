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

from qdash.workflow.engine.scheduler.plugins.base import (
    CRPairFilter,
    CRSchedulingStrategy,
    FilterContext,
    ScheduleContext,
)
from qdash.workflow.engine.scheduler.plugins.candidate_qubit_filter import CandidateQubitFilter
from qdash.workflow.engine.scheduler.plugins.fidelity_filter import FidelityFilter
from qdash.workflow.engine.scheduler.plugins.frequency_directionality_filter import (
    FrequencyDirectionalityFilter,
)
from qdash.workflow.engine.scheduler.plugins.intra_then_inter_mux_scheduler import (
    IntraThenInterMuxScheduler,
)
from qdash.workflow.engine.scheduler.plugins.mux_conflict_scheduler import MuxConflictScheduler

__all__ = [
    "CRPairFilter",
    "CRSchedulingStrategy",
    "CandidateQubitFilter",
    "FidelityFilter",
    "FilterContext",
    "FrequencyDirectionalityFilter",
    "IntraThenInterMuxScheduler",
    "MuxConflictScheduler",
    "ScheduleContext",
]
