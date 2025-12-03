"""Calibration engine components.

This module provides calibration workflow management components organized into:
- task/: Task management (TaskManager, TaskExecutor, TaskStateManager, etc.)
- execution/: Execution management (ExecutionManager, ExecutionStateManager, ExecutionService)
- scheduler/: CR scheduling (CRScheduler)
- repository/: Data persistence (MongoDB, filesystem implementations)
"""

# Task components
from qdash.workflow.engine.calibration.task.manager import TaskManager
from qdash.workflow.engine.calibration.task.executor import TaskExecutor, TaskExecutionError
from qdash.workflow.engine.calibration.task.state_manager import TaskStateManager
from qdash.workflow.engine.calibration.task.result_processor import (
    TaskResultProcessor,
    R2ValidationError,
    FidelityValidationError,
)
from qdash.workflow.engine.calibration.task.history_recorder import TaskHistoryRecorder

# Execution components
from qdash.workflow.engine.calibration.execution.manager import ExecutionManager
from qdash.workflow.engine.calibration.execution.state_manager import ExecutionStateManager
from qdash.workflow.engine.calibration.execution.service import ExecutionService

# Scheduler components
from qdash.workflow.engine.calibration.scheduler.cr_scheduler import CRScheduler, CRScheduleResult

# Prefect tasks
from qdash.workflow.engine.calibration.prefect_tasks import (
    execute_dynamic_task_by_qid,
    execute_dynamic_task_batch,
    validate_task_name,
)

# Utilities
from qdash.workflow.engine.calibration.util import (
    qid_to_label,
    pydantic_serializer,
    update_active_tasks,
    SystemInfo,
)

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
    # Prefect tasks
    "execute_dynamic_task_by_qid",
    "execute_dynamic_task_batch",
    "validate_task_name",
    # Utilities
    "qid_to_label",
    "pydantic_serializer",
    "update_active_tasks",
    "SystemInfo",
]
