"""Workflow helper functions and utilities for Python Flow Editor."""

from qdash.workflow.helpers.flow_helpers import (
    FlowSession,
    finish_calibration,
    generate_execution_id,
    get_session,
    init_calibration,
)
from qdash.workflow.helpers.github_integration import (
    ConfigFileType,
    GitHubIntegration,
    GitHubPushConfig,
)
from qdash.workflow.helpers.parallel_helpers import calibrate_parallel, parallel_map

__all__ = [
    # === Session Management ===
    "FlowSession",
    "init_calibration",
    "get_session",
    "finish_calibration",
    "generate_execution_id",
    # === GitHub Integration ===
    "GitHubIntegration",
    "GitHubPushConfig",
    "ConfigFileType",
    # === Parallel Execution (Recommended) ===
    "calibrate_parallel",  # True parallel execution across qubits using @task + submit
    "parallel_map",  # Generic parallel map for custom logic with Prefect UI visibility
]
