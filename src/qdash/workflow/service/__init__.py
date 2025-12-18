"""Workflow service module for Python Flow Editor.

This module provides the main calibration API and utility functions.

Main API:
    CalibService: High-level API for calibration workflows
    generate_execution_id: Generate unique execution IDs

Utility Functions:
    extract_candidate_qubits: Extract high-fidelity qubits from results
    get_wiring_config_path: Get chip wiring configuration path

Task Lists:
    CHECK_1Q_TASKS: Basic 1Q characterization tasks
    FULL_1Q_TASKS: Complete 1Q task list
    FULL_1Q_TASKS_AFTER_CHECK: Advanced 1Q tasks (after check)
    FULL_2Q_TASKS: Complete 2Q task list

Example:
    from prefect import flow
    from qdash.workflow.service import CalibService

    @flow
    def simple_calibration(username, chip_id, qids):
        cal = CalibService(username, chip_id)
        return cal.run(groups=[qids], tasks=["CheckRabi", "CreateHPIPulse"])
"""

from qdash.workflow.service.calib_service import (
    CalibService,
    generate_execution_id,
)
from qdash.workflow.service.context import (
    SessionContext,
    clear_current_session,
    get_current_session,
    set_current_session,
)
from qdash.workflow.service.github import (
    ConfigFileType,
    GitHubIntegration,
    GitHubPushConfig,
)
from qdash.workflow.service.scheduled import (
    extract_candidate_qubits,
    get_wiring_config_path,
)
from qdash.workflow.service.tasks import (
    CHECK_1Q_TASKS,
    FULL_1Q_TASKS,
    FULL_1Q_TASKS_AFTER_CHECK,
    FULL_2Q_TASKS,
)

__all__ = [
    # === High-level API ===
    "CalibService",
    "generate_execution_id",
    # === Utility Functions ===
    "extract_candidate_qubits",
    "get_wiring_config_path",
    # === Task Lists ===
    "CHECK_1Q_TASKS",
    "FULL_1Q_TASKS",
    "FULL_1Q_TASKS_AFTER_CHECK",
    "FULL_2Q_TASKS",
    # === GitHub Integration ===
    "GitHubIntegration",
    "GitHubPushConfig",
    "ConfigFileType",
    # === Context Management ===
    "SessionContext",
    "set_current_session",
    "get_current_session",
    "clear_current_session",
]
