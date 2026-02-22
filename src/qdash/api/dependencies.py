"""Dependency injection configuration for QDash API.

This module provides FastAPI dependency functions for injecting
repositories and services into route handlers.
"""

from functools import lru_cache

from qdash.api.services.admin_service import AdminService
from qdash.api.services.calibration_service import CalibrationService
from qdash.api.services.chip_service import ChipService
from qdash.api.services.copilot_data_service import CopilotDataService
from qdash.api.services.device_topology_service import DeviceTopologyService
from qdash.api.services.execution_service import ExecutionService
from qdash.api.services.issue_service import IssueService
from qdash.api.services.metrics_service import MetricsService
from qdash.api.services.provenance_service import ProvenanceService
from qdash.api.services.seed_import_service import SeedImportService
from qdash.api.services.task_result_service import TaskResultService
from qdash.repository import (
    MongoChipRepository,
    MongoExecutionCounterRepository,
    MongoTaskResultHistoryRepository,
)
from qdash.repository.backend import MongoBackendRepository
from qdash.repository.calibration_note import MongoCalibrationNoteRepository
from qdash.repository.execution_history import MongoExecutionHistoryRepository
from qdash.repository.execution_lock import MongoExecutionLockRepository
from qdash.repository.provenance import (
    MongoActivityRepository,
    MongoParameterVersionRepository,
    MongoProvenanceRelationRepository,
)
from qdash.repository.tag import MongoTagRepository
from qdash.repository.task_definition import MongoTaskDefinitionRepository


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


@lru_cache(maxsize=1)
def get_device_topology_service() -> DeviceTopologyService:
    """Get the device topology service instance.

    Returns
    -------
    DeviceTopologyService
        The device topology service

    """
    return DeviceTopologyService(
        chip_repository=get_chip_repository(),
        calibration_note_repository=get_calibration_note_repository(),
    )


@lru_cache(maxsize=1)
def get_metrics_service() -> MetricsService:
    """Get the metrics service instance.

    Returns
    -------
    MetricsService
        The metrics service

    """
    return MetricsService(
        task_result_repository=get_task_result_repository(),
        chip_repository=get_chip_repository(),
    )


@lru_cache(maxsize=1)
def get_task_result_service() -> TaskResultService:
    """Get the task result service instance.

    Returns
    -------
    TaskResultService
        The task result service

    """
    return TaskResultService(
        chip_repository=get_chip_repository(),
        task_result_repository=get_task_result_repository(),
    )


@lru_cache(maxsize=1)
def get_tag_repository() -> MongoTagRepository:
    """Get the tag repository instance."""
    return MongoTagRepository()


@lru_cache(maxsize=1)
def get_backend_repository() -> MongoBackendRepository:
    """Get the backend repository instance."""
    return MongoBackendRepository()


@lru_cache(maxsize=1)
def get_task_definition_repository() -> MongoTaskDefinitionRepository:
    """Get the task definition repository instance."""
    return MongoTaskDefinitionRepository()


@lru_cache(maxsize=1)
def get_seed_import_service() -> SeedImportService:
    """Get the seed import service instance."""
    return SeedImportService()


@lru_cache(maxsize=1)
def get_provenance_service() -> ProvenanceService:
    """Get the provenance service instance."""
    return ProvenanceService(
        parameter_version_repo=MongoParameterVersionRepository(),
        provenance_relation_repo=MongoProvenanceRelationRepository(),
        activity_repo=MongoActivityRepository(),
    )


@lru_cache(maxsize=1)
def get_issue_service() -> IssueService:
    """Get the issue service instance."""
    return IssueService()


@lru_cache(maxsize=1)
def get_copilot_data_service() -> CopilotDataService:
    """Get the copilot data service instance."""
    return CopilotDataService()


@lru_cache(maxsize=1)
def get_admin_service() -> AdminService:
    """Get the admin service instance."""
    return AdminService()
