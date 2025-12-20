"""Repository Layer - Data persistence abstraction.

NOTE: All repository implementations have been moved to src/qdash/repository/.
This module re-exports from the common layer for backward compatibility.

For new code, import directly from qdash.repository:
    from qdash.repository import MongoChipRepository
"""

# Re-export for backward compatibility
from qdash.repository import (
    FilesystemCalibDataSaver,
    MongoCalibrationNoteRepository,
    MongoChipHistoryRepository,
    MongoChipRepository,
    MongoCouplingCalibrationRepository,
    MongoExecutionCounterRepository,
    MongoExecutionLockRepository,
    MongoExecutionRepository,
    MongoQubitCalibrationRepository,
    MongoTaskRepository,
    MongoTaskResultHistoryRepository,
    MongoUserRepository,
)
from qdash.repository.inmemory import (
    InMemoryCalibrationNoteRepository,
    InMemoryChipHistoryRepository,
    InMemoryChipRepository,
    InMemoryCouplingCalibrationRepository,
    InMemoryExecutionCounterRepository,
    InMemoryExecutionLockRepository,
    InMemoryExecutionRepository,
    InMemoryQubitCalibrationRepository,
    InMemoryTaskRepository,
    InMemoryTaskResultHistoryRepository,
    InMemoryUserRepository,
)
from qdash.repository.protocols import (
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
    "CalibDataSaver",
    "CalibrationNoteRepository",
    "ChipHistoryRepository",
    "ChipRepository",
    "CouplingCalibrationRepository",
    "ExecutionCounterRepository",
    "ExecutionLockRepository",
    "ExecutionRepository",
    "QubitCalibrationRepository",
    "TaskRepository",
    "TaskResultHistoryRepository",
    "UserRepository",
    # MongoDB implementations
    "MongoCalibrationNoteRepository",
    "MongoChipHistoryRepository",
    "MongoChipRepository",
    "MongoCouplingCalibrationRepository",
    "MongoExecutionCounterRepository",
    "MongoExecutionLockRepository",
    "MongoExecutionRepository",
    "MongoQubitCalibrationRepository",
    "MongoTaskRepository",
    "MongoTaskResultHistoryRepository",
    "MongoUserRepository",
    # Filesystem implementations
    "FilesystemCalibDataSaver",
    # In-memory implementations (for testing)
    "InMemoryCalibrationNoteRepository",
    "InMemoryChipHistoryRepository",
    "InMemoryChipRepository",
    "InMemoryCouplingCalibrationRepository",
    "InMemoryExecutionCounterRepository",
    "InMemoryExecutionLockRepository",
    "InMemoryExecutionRepository",
    "InMemoryQubitCalibrationRepository",
    "InMemoryTaskRepository",
    "InMemoryTaskResultHistoryRepository",
    "InMemoryUserRepository",
]
