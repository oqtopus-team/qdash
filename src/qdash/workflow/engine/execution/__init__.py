"""Execution Management Layer - Workflow session tracking.

This module manages workflow execution sessions, tracking their status,
associated tasks, and results in MongoDB.

Components
----------
ExecutionService
    High-level service for managing execution lifecycle:
    - Create new executions with metadata (tags, notes, project_id)
    - Track execution status (RUNNING -> COMPLETED/FAILED)
    - Update task results during execution
    - Persist to MongoDB (ExecutionDocument)

ExecutionStateManager
    Low-level state transitions for executions:
    - start() - Mark as RUNNING with timestamp
    - complete() - Mark as COMPLETED
    - fail() - Mark as FAILED

ExecutionNote
    Data model for execution notes (stage results, metadata).

StageResult
    Data model for individual stage results within an execution.

Execution Lifecycle
-------------------
::

    create() --> save() --> start()
                              |
                    +---------+---------+
                    v                   v
               complete()           fail()

Usage Example
-------------
>>> from qdash.workflow.engine.execution import ExecutionService
>>> service = ExecutionService.create(
...     username="alice",
...     execution_id="20240101-001",
...     chip_id="64Qv3",
...     calib_data_path="/path/to/data",
...     name="1Q Calibration",
... )
>>> service.save()
>>> service.start()
>>> # ... run tasks ...
>>> service.complete()

MongoDB Integration
-------------------
Executions are persisted to the `executions` collection with:
- execution_id: Unique identifier
- status: RUNNING, COMPLETED, FAILED
- task_results: Nested task data by qubit/coupling
- timestamps: start_at, end_at
- metadata: tags, notes, project_id
"""

from qdash.workflow.engine.execution.models import ExecutionNote, StageResult
from qdash.workflow.engine.execution.service import ExecutionService
from qdash.workflow.engine.execution.state_manager import ExecutionStateManager

__all__ = [
    "ExecutionNote",
    "ExecutionService",
    "ExecutionStateManager",
    "StageResult",
]
