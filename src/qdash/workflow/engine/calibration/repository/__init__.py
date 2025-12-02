"""Repository layer for TaskManager.

This module provides repository abstractions and implementations for
decoupling TaskManager from specific data access implementations.
"""

from qdash.workflow.engine.calibration.repository.filesystem_impl import (
    FilesystemCalibDataSaver,
)
from qdash.workflow.engine.calibration.repository.mongo_impl import (
    MongoChipHistoryRepository,
    MongoChipRepository,
    MongoTaskResultHistoryRepository,
    create_default_repositories,
)
from qdash.workflow.engine.calibration.repository.protocols import (
    CalibDataSaver,
    ChipHistoryRepository,
    ChipRepository,
    TaskResultHistoryRepository,
)

__all__ = [
    # Protocols
    "TaskResultHistoryRepository",
    "ChipRepository",
    "ChipHistoryRepository",
    "CalibDataSaver",
    # MongoDB implementations
    "MongoTaskResultHistoryRepository",
    "MongoChipRepository",
    "MongoChipHistoryRepository",
    "create_default_repositories",
    # Filesystem implementations
    "FilesystemCalibDataSaver",
]
