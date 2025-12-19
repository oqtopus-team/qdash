"""Calibration engine components.

This module provides calibration workflow management components organized into:
- task/: Task management (TaskSession, TaskExecutor, TaskStateManager, etc.)
- execution/: Execution management (ExecutionService, ExecutionStateManager)
- session/: Session management (SessionManager, SessionConfig)
- scheduler/: CR scheduling (CRScheduler)
- repository/: Data persistence (MongoDB, filesystem implementations)
"""

# Execution components
from qdash.workflow.engine.calibration.execution.service import ExecutionService
from qdash.workflow.engine.calibration.execution.state_manager import ExecutionStateManager

# Session components
from qdash.workflow.engine.calibration.session import SessionConfig, SessionManager

# Scheduler components
from qdash.workflow.engine.calibration.scheduler.cr_scheduler import CRScheduler, CRScheduleResult
from qdash.workflow.engine.calibration.scheduler.one_qubit_plugins import (
    CheckerboardOrderingStrategy,
    DefaultOrderingStrategy,
    DefaultSynchronizedStrategy,
    MuxOrderingStrategy,
    OrderingContext,
)
from qdash.workflow.engine.calibration.scheduler.one_qubit_scheduler import (
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
from qdash.workflow.engine.calibration.task.executor import TaskExecutionError, TaskExecutor
from qdash.workflow.engine.calibration.task.history_recorder import TaskHistoryRecorder
from qdash.workflow.engine.calibration.task.result_processor import (
    FidelityValidationError,
    R2ValidationError,
    TaskResultProcessor,
)
from qdash.workflow.engine.calibration.task.session import TaskSession
from qdash.workflow.engine.calibration.task.state_manager import TaskStateManager

__all__ = [
    # Session
    "SessionManager",
    "SessionConfig",
    # Task
    "TaskSession",
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
