"""Workflow engine components.

This module provides calibration workflow management components organized into:
- orchestrator.py: CalibOrchestrator - session lifecycle management
- config.py: CalibConfig - session configuration
- task/: Task management (TaskContext, TaskExecutor, TaskStateManager, etc.)
- execution/: Execution management (ExecutionService, ExecutionStateManager)
- scheduler/: CR scheduling (CRScheduler)
- repository/: Data persistence (MongoDB, filesystem implementations)
- backend/: Backend implementations (qubex, fake)
"""

# Orchestration components
from qdash.workflow.engine.config import CalibConfig
from qdash.workflow.engine.orchestrator import CalibOrchestrator

# Execution components
from qdash.workflow.engine.execution.service import ExecutionService
from qdash.workflow.engine.execution.state_manager import ExecutionStateManager

# Scheduler components
from qdash.workflow.engine.scheduler.cr_scheduler import CRScheduler, CRScheduleResult
from qdash.workflow.engine.scheduler.one_qubit_plugins import (
    CheckerboardOrderingStrategy,
    DefaultOrderingStrategy,
    DefaultSynchronizedStrategy,
    MuxOrderingStrategy,
    OrderingContext,
)
from qdash.workflow.engine.scheduler.one_qubit_scheduler import (
    BOX_A,
    BOX_B,
    BOX_MIXED,
    OneQubitScheduler,
    OneQubitScheduleResult,
    OneQubitStageInfo,
    SynchronizedOneQubitScheduleResult,
    SynchronizedStepInfo,
)

# Task components
from qdash.workflow.engine.task.context import TaskContext
from qdash.workflow.engine.task.executor import TaskExecutionError, TaskExecutor
from qdash.workflow.engine.task.history_recorder import TaskHistoryRecorder
from qdash.workflow.engine.task.result_processor import (
    FidelityValidationError,
    R2ValidationError,
    TaskResultProcessor,
)
from qdash.workflow.engine.task.state_manager import TaskStateManager

# Backwards compatibility aliases
SessionManager = CalibOrchestrator
SessionConfig = CalibConfig
TaskSession = TaskContext

__all__ = [
    # Orchestration
    "CalibOrchestrator",
    "CalibConfig",
    # Backwards compatibility
    "SessionManager",
    "SessionConfig",
    # Task
    "TaskContext",
    "TaskSession",  # Backwards compatibility
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
