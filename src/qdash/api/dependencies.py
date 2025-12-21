"""Dependency injection configuration for QDash API.

This module provides FastAPI dependency functions for injecting
repositories and services into route handlers.
"""

from functools import lru_cache

from qdash.api.services.calibration_service import CalibrationService
from qdash.api.services.chip_service import ChipService
from qdash.api.services.execution_service import ExecutionService
from qdash.repository import (
    MongoChipRepository,
    MongoExecutionCounterRepository,
    MongoTaskResultHistoryRepository,
)
from qdash.repository.calibration_note import MongoCalibrationNoteRepository
from qdash.repository.execution_history import MongoExecutionHistoryRepository
from qdash.repository.execution_lock import MongoExecutionLockRepository


@lru_cache(maxsize=1)
def get_chip_repository() -> MongoChipRepository:
    """Get the chip repository instance.

    Returns
    -------
    MongoChipRepository
        The chip repository

    """
    return MongoChipRepository()


@lru_cache(maxsize=1)
def get_execution_counter_repository() -> MongoExecutionCounterRepository:
    """Get the execution counter repository instance.

    Returns
    -------
    MongoExecutionCounterRepository
        The execution counter repository

    """
    return MongoExecutionCounterRepository()


@lru_cache(maxsize=1)
def get_task_result_repository() -> MongoTaskResultHistoryRepository:
    """Get the task result history repository instance.

    Returns
    -------
    MongoTaskResultHistoryRepository
        The task result history repository

    """
    return MongoTaskResultHistoryRepository()


@lru_cache(maxsize=1)
def get_chip_service() -> ChipService:
    """Get the chip service instance.

    Returns
    -------
    ChipService
        The chip service

    """
    return ChipService(
        chip_repository=get_chip_repository(),
        execution_counter_repository=get_execution_counter_repository(),
        task_result_repository=get_task_result_repository(),
    )


@lru_cache(maxsize=1)
def get_execution_history_repository() -> MongoExecutionHistoryRepository:
    """Get the execution history repository instance.

    Returns
    -------
    MongoExecutionHistoryRepository
        The execution history repository

    """
    return MongoExecutionHistoryRepository()


@lru_cache(maxsize=1)
def get_execution_lock_repository() -> MongoExecutionLockRepository:
    """Get the execution lock repository instance.

    Returns
    -------
    MongoExecutionLockRepository
        The execution lock repository

    """
    return MongoExecutionLockRepository()


@lru_cache(maxsize=1)
def get_execution_service() -> ExecutionService:
    """Get the execution service instance.

    Returns
    -------
    ExecutionService
        The execution service

    """
    return ExecutionService(
        execution_history_repository=get_execution_history_repository(),
        execution_lock_repository=get_execution_lock_repository(),
    )


@lru_cache(maxsize=1)
def get_calibration_note_repository() -> MongoCalibrationNoteRepository:
    """Get the calibration note repository instance.

    Returns
    -------
    MongoCalibrationNoteRepository
        The calibration note repository

    """
    return MongoCalibrationNoteRepository()


@lru_cache(maxsize=1)
def get_calibration_service() -> CalibrationService:
    """Get the calibration service instance.

    Returns
    -------
    CalibrationService
        The calibration service

    """
    return CalibrationService(
        calibration_note_repository=get_calibration_note_repository(),
    )
