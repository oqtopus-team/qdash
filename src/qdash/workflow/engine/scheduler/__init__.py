"""Scheduling Layer - Parallel task coordination.

This module provides schedulers for coordinating parallel calibration tasks,
avoiding hardware conflicts (MUX sharing, qubit reuse).

Components
----------
CRScheduler (2-Qubit)
    Schedules Cross-Resonance (2-qubit) calibration tasks.
    Uses graph coloring to find conflict-free parallel groups.

    Features:
    - MUX-aware conflict detection (qubits sharing a MUX cannot run together)
    - Qubit reuse detection (qubit in multiple pairs cannot run together)
    - Multiple coloring strategies (largest_first, smallest_last, saturation)
    - Design-based direction inference from chip topology

CRScheduleResult
    Result of CR scheduling containing grouped pairs and metadata.

OneQubitScheduler (1-Qubit)
    Schedules 1-qubit calibration tasks with Box-aware grouping.

    Features:
    - Box classification (BOX_A, BOX_B, BOX_MIXED)
    - Synchronized execution mode
    - Pluggable ordering strategies

OneQubitScheduleResult
    Result of 1-qubit scheduling with stage information.

Conflict Types
--------------
1. **MUX Conflict**: Two qubits share the same MUX (multiplexer)
2. **Qubit Conflict**: Same qubit appears in multiple CR pairs
3. **Box Conflict**: Tasks from different boxes cannot be synchronized

Scheduling Example
------------------
>>> from qdash.workflow.engine.scheduler import CRScheduler
>>> scheduler = CRScheduler(
...     username="alice",
...     chip_id="64Qv3",
... )
>>> result = scheduler.generate(
...     candidate_qubits=["0", "1", "2", "3"],
... )
>>> for group in result.groups:
...     print(f"Parallel group: {group}")

Box Constants
-------------
BOX_A : str
    Identifier for Box A hardware group.
BOX_B : str
    Identifier for Box B hardware group.
BOX_MIXED : str
    Identifier for mixed Box A/B configuration.
"""

from qdash.workflow.engine.scheduler.cr_scheduler import CRScheduler, CRScheduleResult
from qdash.workflow.engine.scheduler.one_qubit_scheduler import OneQubitScheduler
from qdash.workflow.engine.scheduler.one_qubit_types import (
    BOX_A,
    BOX_B,
    BOX_MIXED,
    OneQubitScheduleResult,
    OneQubitStageInfo,
)

__all__ = [
    # CR Scheduler (2-qubit)
    "CRScheduler",
    "CRScheduleResult",
    # 1-Qubit Scheduler
    "OneQubitScheduler",
    "OneQubitScheduleResult",
    "OneQubitStageInfo",
    "BOX_A",
    "BOX_B",
    "BOX_MIXED",
]
