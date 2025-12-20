"""Repository layer for QDash.

This module provides data access abstractions for both API and workflow components.
"""

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

# MongoDB implementations
from qdash.repository.backend import MongoBackendRepository
from qdash.repository.calibration_note import MongoCalibrationNoteRepository
from qdash.repository.chip import MongoChipRepository
from qdash.repository.chip_history import MongoChipHistoryRepository
from qdash.repository.coupling import MongoCouplingCalibrationRepository
from qdash.repository.execution import MongoExecutionRepository
from qdash.repository.execution_counter import MongoExecutionCounterRepository
from qdash.repository.execution_history import MongoExecutionHistoryRepository
from qdash.repository.execution_lock import MongoExecutionLockRepository
from qdash.repository.flow import MongoFlowRepository
from qdash.repository.project import MongoProjectRepository
from qdash.repository.project_membership import MongoProjectMembershipRepository
from qdash.repository.qubit import MongoQubitCalibrationRepository
from qdash.repository.tag import MongoTagRepository
from qdash.repository.task import MongoTaskRepository
from qdash.repository.task_definition import MongoTaskDefinitionRepository
from qdash.repository.task_result_history import MongoTaskResultHistoryRepository
from qdash.repository.user import MongoUserRepository

# Filesystem implementations
from qdash.repository.filesystem import FilesystemCalibDataSaver

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
    "MongoBackendRepository",
    "MongoCalibrationNoteRepository",
    "MongoChipHistoryRepository",
    "MongoChipRepository",
    "MongoCouplingCalibrationRepository",
    "MongoExecutionCounterRepository",
    "MongoExecutionHistoryRepository",
    "MongoExecutionLockRepository",
    "MongoExecutionRepository",
    "MongoFlowRepository",
    "MongoProjectRepository",
    "MongoProjectMembershipRepository",
    "MongoQubitCalibrationRepository",
    "MongoTagRepository",
    "MongoTaskRepository",
    "MongoTaskDefinitionRepository",
    "MongoTaskResultHistoryRepository",
    "MongoUserRepository",
    # Filesystem implementations
    "FilesystemCalibDataSaver",
]
