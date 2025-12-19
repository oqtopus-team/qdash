"""Repository Layer - Data persistence abstraction.

This module provides protocol-based repository abstractions and implementations
for data access in calibration workflows. Using protocols allows for easy
testing with mock implementations.

Design Pattern
--------------
The repository pattern separates data access logic from business logic:
::

    TaskExecutor
         │
         ▼
    Repository Protocol  ◄── Interface
         │
    ┌────┴────┐
    ▼         ▼
  MongoDB   Filesystem
   Impl       Impl

Protocols (Interfaces)
----------------------
TaskResultHistoryRepository
    Interface for task result history storage.
    Records individual task executions for audit/debugging.

ChipRepository
    Interface for chip configuration access.
    Reads chip topology, qubit configurations.

ChipHistoryRepository
    Interface for chip history snapshots.
    Creates point-in-time snapshots after calibrations.

CalibDataSaver
    Interface for saving figures and raw data.
    Saves PNG/JSON figures and numpy arrays.

ExecutionRepository
    Interface for execution record storage.
    Tracks workflow execution sessions.

CalibrationNoteRepository
    Interface for calibration note storage.
    Stores and retrieves calibration notes for chips.

MongoDB Implementations
-----------------------
MongoTaskResultHistoryRepository
    Persists to ``task_result_history`` collection.

MongoChipRepository
    Reads from ``chips`` collection.

MongoChipHistoryRepository
    Persists to ``chip_history`` collection.

MongoExecutionRepository
    Persists to ``executions`` collection.

MongoCalibrationNoteRepository
    Persists to ``calibration_note`` collection.

Filesystem Implementations
--------------------------
FilesystemCalibDataSaver
    Saves figures to ``fig/`` and raw data to ``raw_data/`` directories.
    Generates unique filenames with timestamps.

Usage Example
-------------
>>> from qdash.workflow.engine.repository import (
...     create_default_repositories,
...     FilesystemCalibDataSaver,
... )
>>> repos = create_default_repositories()
>>> repos["task_result_history"].save(task_model)
>>> saver = FilesystemCalibDataSaver("/path/to/calib")
>>> png_paths, json_paths = saver.save_figures(figures, "CheckRabi", "qubit", "0")

Testing with Mocks
------------------
>>> from unittest.mock import MagicMock
>>> mock_repo = MagicMock(spec=TaskResultHistoryRepository)
>>> executor = TaskExecutor(history_recorder=mock_repo, ...)
"""

from qdash.workflow.engine.repository.filesystem_impl import (
    FilesystemCalibDataSaver,
)
from qdash.workflow.engine.repository.inmemory_calibration_note import (
    InMemoryCalibrationNoteRepository,
)
from qdash.workflow.engine.repository.inmemory_impl import (
    InMemoryChipRepository,
    InMemoryExecutionCounterRepository,
    InMemoryExecutionLockRepository,
    InMemoryExecutionRepository,
    InMemoryTaskRepository,
    InMemoryUserRepository,
)
from qdash.workflow.engine.repository.mongo_calibration_note import (
    MongoCalibrationNoteRepository,
)
from qdash.workflow.engine.repository.mongo_coupling import (
    MongoCouplingCalibrationRepository,
)
from qdash.workflow.engine.repository.mongo_calib_service import (
    MongoExecutionCounterRepository,
    MongoExecutionLockRepository,
    MongoTaskRepository,
    MongoUserRepository,
)
from qdash.workflow.engine.repository.mongo_execution import (
    MongoExecutionRepository,
)
from qdash.workflow.engine.repository.mongo_impl import (
    MongoChipHistoryRepository,
    MongoChipRepository,
    MongoTaskResultHistoryRepository,
    create_default_repositories,
)
from qdash.workflow.engine.repository.mongo_qubit import (
    MongoQubitCalibrationRepository,
)
from qdash.workflow.engine.repository.protocols import (
    CalibDataSaver,
    CalibrationNoteRepository,
    ChipHistoryRepository,
    ChipRepository,
    CouplingCalibrationRepository,
    ExecutionCounterRepository,
    ExecutionLockRepository,
    ExecutionRepository,
    QubitCalibrationRepository,
    TaskRepository,
    TaskResultHistoryRepository,
    UserRepository,
)

__all__ = [
    # Protocols
    "TaskResultHistoryRepository",
    "ChipRepository",
    "ChipHistoryRepository",
    "CalibDataSaver",
    "ExecutionRepository",
    "CalibrationNoteRepository",
    "QubitCalibrationRepository",
    "CouplingCalibrationRepository",
    "ExecutionCounterRepository",
    "ExecutionLockRepository",
    "UserRepository",
    "TaskRepository",
    # MongoDB implementations
    "MongoTaskResultHistoryRepository",
    "MongoChipRepository",
    "MongoChipHistoryRepository",
    "MongoExecutionRepository",
    "MongoCalibrationNoteRepository",
    "MongoQubitCalibrationRepository",
    "MongoCouplingCalibrationRepository",
    "MongoExecutionCounterRepository",
    "MongoExecutionLockRepository",
    "MongoUserRepository",
    "MongoTaskRepository",
    "create_default_repositories",
    # Filesystem implementations
    "FilesystemCalibDataSaver",
    # In-memory implementations (for testing)
    "InMemoryCalibrationNoteRepository",
    "InMemoryExecutionRepository",
    "InMemoryExecutionCounterRepository",
    "InMemoryExecutionLockRepository",
    "InMemoryUserRepository",
    "InMemoryTaskRepository",
    "InMemoryChipRepository",
]
