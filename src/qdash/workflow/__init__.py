"""QDash Workflow - Calibration workflow engine and CalService API.

This module provides the core workflow engine and CalService API for
quantum calibration workflows.

Public API:
    CalService: Main class for calibration workflows
    - run(): Sequential calibration
    - run_parallel(): Parallel group calibration
    - run_full_chip(): Full chip 1Q+2Q calibration
    - sweep(): Parameter sweep
    - two_qubit(): 2-qubit coupling calibration
    - check_skew(): System-level skew check

Example:
    ```python
    from prefect import flow
    from qdash.workflow import CalService

    @flow
    def my_calibration(username, chip_id, qids, flow_name=None, project_id=None):
        cal = CalService(username, chip_id, flow_name=flow_name, project_id=project_id)
        return cal.run(qids=qids, tasks=["CheckRabi", "CreateHPIPulse"])
    ```
"""

from qdash.workflow.flow import (
    CalService,
    ConfigFileType,
    GitHubIntegration,
    GitHubPushConfig,
    generate_execution_id,
)

__all__ = [
    # === High-level API ===
    "CalService",
    "generate_execution_id",
    # === GitHub Integration ===
    "GitHubIntegration",
    "GitHubPushConfig",
    "ConfigFileType",
]
