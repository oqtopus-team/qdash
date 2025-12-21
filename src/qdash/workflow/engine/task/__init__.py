"""Task Execution Layer - Individual task lifecycle management.

This module provides components for executing individual calibration tasks
with proper state management, validation, and persistence.

Components
----------
TaskContext
    Container for task execution state and results.
    Holds task_result (qubit/coupling/global tasks), calib_data,
    for an execution session.

TaskExecutor
    Executes tasks with full lifecycle management:
    1. ensure_task_exists() - Register task in state
    2. start_task() - Set status to RUNNING
    3. preprocess() - Extract input parameters from backend
    4. run() - Execute hardware measurement
    5. postprocess() - Extract output parameters, generate figures
    6. validate_r2() - Check R² threshold
    7. save_artifacts() - Save figures and raw data
    8. end_task() - Record end time

TaskStateManager
    Manages task state transitions (SCHEDULED → RUNNING → COMPLETED/FAILED)
    and stores input/output parameters.

TaskResultProcessor
    Validates task results:
    - R² threshold validation (rejects fitting failures)
    - Fidelity validation (rejects values > 100%)

TaskHistoryRecorder
    Records task results to MongoDB for history tracking
    and creates chip history snapshots.

State Transitions
-----------------
::

    SCHEDULED ──► RUNNING ──► COMPLETED
                     │
                     └──────► FAILED

Usage Example
-------------
>>> from qdash.workflow.engine.task import TaskContext, TaskExecutor, TaskStateManager
>>> state_manager = TaskStateManager(task_result, calib_data)
>>> executor = TaskExecutor(
...     state_manager=state_manager,
...     calib_dir="/path/to/calib",
...     execution_id="exec-001",
...     task_manager_id="tm-001",
... )
>>> result = executor.execute_task(task, backend, qid="0")

Exceptions
----------
TaskExecutionError
    Raised when task execution fails unexpectedly.

R2ValidationError
    Raised when R² value is below threshold.

FidelityValidationError
    Raised when fidelity value exceeds 100%.
"""

from qdash.datamodel.task import TaskType, TaskTypes
from qdash.workflow.engine.task.context import TaskContext
from qdash.workflow.engine.task.executor import TaskExecutionError, TaskExecutor
from qdash.workflow.engine.task.history_recorder import TaskHistoryRecorder
from qdash.workflow.engine.task.result_processor import (
    FidelityValidationError,
    R2ValidationError,
    TaskResultProcessor,
)
from qdash.workflow.engine.task.state_manager import TaskStateManager

__all__ = [
    "TaskContext",
    "TaskExecutor",
    "TaskExecutionError",
    "TaskStateManager",
    "TaskResultProcessor",
    "R2ValidationError",
    "FidelityValidationError",
    "TaskHistoryRecorder",
    "TaskType",
    "TaskTypes",
]
