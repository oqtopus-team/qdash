"""Workflow Engine - Core infrastructure for calibration workflow execution.

This module provides the internal engine components for calibration workflows.
Most users should use the high-level `CalibService` API instead of these components directly.

Architecture Overview
---------------------
The engine is organized into layers:

1. **Orchestration** (CalibOrchestrator, CalibConfig)
   - Session lifecycle management
   - Component initialization and coordination

2. **Task Execution** (task/)
   - TaskContext: Execution context and state container
   - TaskExecutor: Task lifecycle (preprocess → run → postprocess)
   - TaskStateManager: State transitions and parameter storage
   - TaskResultProcessor: R² and fidelity validation
   - TaskHistoryRecorder: History recording to MongoDB

3. **Execution Management** (execution/)
   - ExecutionService: Workflow session tracking
   - ExecutionStateManager: Execution state transitions

4. **Scheduling** (scheduler/)
   - CRScheduler: 2-qubit (Cross-Resonance) scheduling with graph coloring
   - OneQubitScheduler: 1-qubit scheduling with Box-aware grouping

5. **Data Persistence** (repository/)
   - Protocol-based repository abstractions
   - MongoDB and filesystem implementations

6. **Backend Abstraction** (backend/)
   - BaseBackend: Abstract interface for hardware
   - QubexBackend: Real hardware via qubex library
   - FakeBackend: Simulation for testing

Component Relationships
-----------------------
::

    CalibService (high-level API)
           │
           ▼
    CalibOrchestrator
           │
    ┌──────┼──────┐
    ▼      ▼      ▼
  Task   Exec   Backend
  Context Service
           │
           ▼
    TaskExecutor
           │
    ┌──────┼──────┬──────┐
    ▼      ▼      ▼      ▼
  State  Result History Data
  Manager Processor Recorder Saver

Usage Example
-------------
Most users should use CalibService. Direct engine usage:

>>> from qdash.workflow.engine import CalibOrchestrator, CalibConfig
>>> config = CalibConfig(
...     username="alice",
...     chip_id="64Qv3",
...     qids=["0", "1"],
...     execution_id="20240101-001",
... )
>>> orchestrator = CalibOrchestrator(config)
>>> orchestrator.initialize()
>>> result = orchestrator.run_task("CheckRabi", qid="0")
>>> orchestrator.complete()

See Also
--------
- docs/development/workflow/engine-architecture.md for detailed architecture
- qdash.workflow.CalibService for high-level API
"""

# Orchestration components
from qdash.workflow.engine.config import CalibConfig

# Execution components
from qdash.workflow.engine.execution.service import ExecutionService
from qdash.workflow.engine.execution.state_manager import ExecutionStateManager
from qdash.workflow.engine.orchestrator import CalibOrchestrator

# Scheduler components
from qdash.workflow.engine.scheduler.cr_scheduler import CRScheduler, CRScheduleResult
from qdash.workflow.engine.scheduler.one_qubit_plugins import (
    CheckerboardOrderingStrategy,
    DefaultOrderingStrategy,
    DefaultSynchronizedStrategy,
    MuxOrderingStrategy,
    OrderingContext,
)
from qdash.workflow.engine.scheduler.one_qubit_scheduler import OneQubitScheduler
from qdash.workflow.engine.scheduler.one_qubit_types import (
    BOX_A,
    BOX_B,
    BOX_MIXED,
    OneQubitScheduleResult,
    OneQubitStageInfo,
    SynchronizedOneQubitScheduleResult,
    SynchronizedStepInfo,
)

# Task components
from qdash.workflow.engine.task.context import TaskContext
from qdash.workflow.engine.task.executor import TaskExecutor
from qdash.workflow.engine.task.history_recorder import TaskHistoryRecorder
from qdash.workflow.engine.task.result_processor import (
    FidelityValidationError,
    R2ValidationError,
    TaskResultProcessor,
)
from qdash.workflow.engine.task.state_manager import TaskStateManager
from qdash.workflow.engine.task.types import TaskExecutionError

__all__ = [
    # Orchestration
    "CalibOrchestrator",
    "CalibConfig",
    # Task
    "TaskContext",
    "TaskExecutor",
    "TaskExecutionError",
    "TaskStateManager",
    "TaskResultProcessor",
    "R2ValidationError",
    "FidelityValidationError",
    "TaskHistoryRecorder",
    # Execution
    "ExecutionStateManager",
    "ExecutionService",
    # Scheduler
    "CRScheduler",
    "CRScheduleResult",
    "OneQubitScheduler",
    "OneQubitScheduleResult",
    "OneQubitStageInfo",
    "BOX_A",
    "BOX_B",
    "BOX_MIXED",
    # 1-Qubit Ordering Plugins
    "MuxOrderingStrategy",
    "OrderingContext",
    "DefaultOrderingStrategy",
    "DefaultSynchronizedStrategy",
    "CheckerboardOrderingStrategy",
    # Synchronized Scheduling
    "SynchronizedOneQubitScheduleResult",
    "SynchronizedStepInfo",
]
