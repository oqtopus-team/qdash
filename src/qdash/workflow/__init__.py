"""QDash Workflow - Calibration workflow engine and CalibService API.

This module provides the core workflow engine and CalibService API for
quantum calibration workflows.

Public API:
    CalibService: Main class for calibration workflows; ``run()`` executes steps
    TaskCall: One call of a task inside a step, with its own settings and call_id
    sweep: Declarative sweep values for run parameters

Example:
    ```python
    from prefect import flow
    from qdash.workflow import CalibService, TaskCall
    from qdash.workflow.service.steps import CustomOneQubit
    from qdash.workflow.service.targets import QubitTargets

    @flow
    def my_calibration(username, chip_id, qids, flow_name=None, project_id=None):
        cal = CalibService(username, chip_id, flow_name=flow_name, project_id=project_id)
        return cal.run(
            QubitTargets(qids=qids),
            steps=[
                CustomOneQubit(
                    step_name="rabi_and_pulse",
                    tasks=[TaskCall(name="CheckRabi"), TaskCall(name="CreateHPIPulse")],
                )
            ],
        )
    ```
"""

from qdash.datamodel.task_call import TaskCall
from qdash.workflow import sweep
from qdash.workflow.service import (
    CalibContext,
    CalibContextError,
    CalibService,
    ConfigFileType,
    GitHubIntegration,
    GitHubPushConfig,
    generate_execution_id,
    resolve_calib_context,
)

__all__ = [
    # === High-level API ===
    "CalibContext",
    "CalibContextError",
    "CalibService",
    "ConfigFileType",
    # === GitHub Integration ===
    "GitHubIntegration",
    "GitHubPushConfig",
    "TaskCall",
    "generate_execution_id",
    "resolve_calib_context",
    "sweep",
]
