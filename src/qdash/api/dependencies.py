"""Dependency injection configuration for QDash API.

This module provides FastAPI dependency functions for injecting
repositories and services into route handlers.
"""

from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qdash.api.services.flow_schedule_service import FlowScheduleService
    from qdash.api.services.flow_service import FlowService

from qdash.api.services.admin_service import AdminService
from qdash.api.services.auth_service import AuthService
from qdash.api.services.calibration_service import CalibrationService
from qdash.api.services.chip_service import ChipService
from qdash.api.services.config_service import ConfigService
from qdash.api.services.copilot_data_service import CopilotDataService
from qdash.api.services.device_topology_service import DeviceTopologyService
from qdash.api.services.execution_service import ExecutionService
from qdash.api.services.file_service import FileService
from qdash.api.services.issue_service import IssueService
from qdash.api.services.metrics_service import MetricsService
from qdash.api.services.project_service import ProjectService
from qdash.api.services.provenance_service import ProvenanceService
from qdash.api.services.seed_import_service import SeedImportService
from qdash.api.services.task_file_service import TaskFileService
from qdash.api.services.task_result_service import TaskResultService
from qdash.api.services.task_service import TaskService
from qdash.repository import (
    MongoChipRepository,
    MongoExecutionCounterRepository,
    MongoFlowRepository,
    MongoProjectMembershipRepository,
    MongoProjectRepository,
    MongoTaskResultHistoryRepository,
    MongoUserRepository,
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


@lru_cache(maxsize=1)
def get_config_service() -> ConfigService:
    """Get the config service instance."""
    return ConfigService()


@lru_cache(maxsize=1)
def get_task_service() -> TaskService:
    """Get the task service instance."""
    return TaskService(
        task_definition_repository=get_task_definition_repository(),
    )


@lru_cache(maxsize=1)
def get_user_repository() -> MongoUserRepository:
    """Get the user repository instance."""
    return MongoUserRepository()


@lru_cache(maxsize=1)
def get_auth_service() -> AuthService:
    """Get the auth service instance."""
    return AuthService(
        user_repository=get_user_repository(),
    )


@lru_cache(maxsize=1)
def get_project_repository() -> MongoProjectRepository:
    """Get the project repository instance."""
    return MongoProjectRepository()


@lru_cache(maxsize=1)
def get_membership_repository() -> MongoProjectMembershipRepository:
    """Get the project membership repository instance."""
    return MongoProjectMembershipRepository()


@lru_cache(maxsize=1)
def get_project_service() -> ProjectService:
    """Get the project service instance."""
    return ProjectService(
        project_repo=get_project_repository(),
        membership_repo=get_membership_repository(),
        user_repo=get_user_repository(),
    )


@lru_cache(maxsize=1)
def get_task_file_service() -> TaskFileService:
    """Get the task file service instance."""
    return TaskFileService()


@lru_cache(maxsize=1)
def get_file_service() -> FileService:
    """Get the file service instance."""
    return FileService()


@lru_cache(maxsize=1)
def get_flow_repository() -> MongoFlowRepository:
    """Get the flow repository instance."""
    return MongoFlowRepository()


@lru_cache(maxsize=1)
def get_flow_service() -> "FlowService":
    """Get the flow service instance."""
    from qdash.api.services.flow_service import FlowService

    return FlowService(
        flow_repository=get_flow_repository(),
    )


@lru_cache(maxsize=1)
def get_flow_schedule_service() -> "FlowScheduleService":
    """Get the flow schedule service instance."""
    from qdash.api.services.flow_schedule_service import FlowScheduleService

    return FlowScheduleService(
        flow_repository=get_flow_repository(),
    )
