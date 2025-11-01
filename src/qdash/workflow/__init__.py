"""QDash Workflow - Calibration workflow engine and Flow Editor.

This module provides the core workflow engine and Flow Editor API for
quantum calibration workflows.

Public API:
    Flow Editor (user-facing API):
        - FlowSession: Main session class for custom flows
        - init_calibration: Initialize a calibration session
        - get_session: Get current session
        - finish_calibration: Complete calibration session
        - GitHubIntegration: GitHub config management
        - GitHubPushConfig: GitHub push configuration
        - ConfigFileType: Config file type enum

Example:
    ```python
    from prefect import flow
    from qdash.workflow import init_calibration, finish_calibration

    @flow
    def my_calibration(username, chip_id, qids):
        session = init_calibration(username, chip_id, qids)
        result = session.execute_task("CheckFreq", "0")
        finish_calibration()
        return result
    ```
"""

from qdash.workflow.flow import (
    ConfigFileType,
    FlowSession,
    GitHubIntegration,
    GitHubPushConfig,
    finish_calibration,
    generate_execution_id,
    get_session,
    init_calibration,
)

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
]
