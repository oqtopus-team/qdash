"""QDash Workflow - Calibration workflow engine and CalibService API.

This module provides the core workflow engine and CalibService API for
quantum calibration workflows.

Public API:
    CalibService: Main class for calibration workflows
    - run(): Sequential calibration
    - run_parallel(): Parallel group calibration
    - run_full_chip(): Full chip 1Q+2Q calibration
    - sweep(): Parameter sweep
    - two_qubit(): 2-qubit coupling calibration
    - check_skew(): System-level skew check

Example:
    ```python
    from prefect import flow
    from qdash.workflow import CalibService

    @flow
    def my_calibration(username, chip_id, qids, flow_name=None, project_id=None):
        cal = CalibService(username, chip_id, flow_name=flow_name, project_id=project_id)
        return cal.run(qids=qids, tasks=["CheckRabi", "CreateHPIPulse"])
    ```
"""

from qdash.workflow.service import (
    CalibService,
    ConfigFileType,
    GitHubIntegration,
    GitHubPushConfig,
    generate_execution_id,
)

__all__ = [
    # === High-level API ===
    "CalibService",
    "generate_execution_id",
    # === GitHub Integration ===
    "GitHubIntegration",
    "GitHubPushConfig",
    "ConfigFileType",
]
