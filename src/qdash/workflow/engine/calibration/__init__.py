"""Calibration engine components.

This module provides calibration workflow management components organized into:
- task/: Task management (TaskManager, TaskExecutor, TaskStateManager, etc.)
- execution/: Execution management (ExecutionManager, ExecutionStateManager, ExecutionService)
- scheduler/: CR scheduling (CRScheduler)
- repository/: Data persistence (MongoDB, filesystem implementations)
"""

# Task components
# Execution components
from qdash.workflow.engine.calibration.execution.manager import ExecutionManager
from qdash.workflow.engine.calibration.execution.service import ExecutionService
from qdash.workflow.engine.calibration.execution.state_manager import ExecutionStateManager

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
from qdash.workflow.engine.calibration.task.executor import TaskExecutionError, TaskExecutor
from qdash.workflow.engine.calibration.task.history_recorder import TaskHistoryRecorder
from qdash.workflow.engine.calibration.task.manager import TaskManager
from qdash.workflow.engine.calibration.task.result_processor import (
    FidelityValidationError,
    R2ValidationError,
    TaskResultProcessor,
)
from qdash.workflow.engine.calibration.task.state_manager import TaskStateManager

# Backward compatibility aliases (deprecated - use new paths)
task_manager = TaskManager
task_executor = TaskExecutor
task_state_manager = TaskStateManager
execution_manager = ExecutionManager
execution_state_manager = ExecutionStateManager
execution_service = ExecutionService
cr_scheduler = CRScheduler

__all__ = [
    # Task
    "TaskManager",
    "TaskExecutor",
    "TaskExecutionError",
    "TaskStateManager",
    "TaskResultProcessor",
    "R2ValidationError",
    "FidelityValidationError",
    "TaskHistoryRecorder",
    # Execution
    "ExecutionManager",
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
