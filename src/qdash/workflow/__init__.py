"""QDash Workflow - run calibrations inside a saved workflow.

Public API:
    CalibrationSession: The launch's calibration session; ``run()`` executes steps
    calibration_flow: Prefect ``@flow`` with QDash's terminal hooks and a session name
    resolve_calib_context: Check the user, chip, project and backend of a run
    CalibrationResult, CalibrationValidation: What ``run()`` and ``validate()`` return
    TaskCall: One call of a task inside a step (the worker's validated subclass of
        ``qdash.calibration.TaskCall``)
    sweep: Declarative sweep values for run parameters
    CalibService: Legacy entry point, kept for saved flows

Targets and steps come from :mod:`qdash.calibration`, the definitions the SDK sends too.

Example:
    ```python
    from qdash.calibration import CustomOneQubit, QubitTargets, TaskCall
    from qdash.workflow import CalibrationSession, calibration_flow, resolve_calib_context


    @calibration_flow(session_name="Rabi and pulses")
    def my_calibration(username, chip_id, qids, flow_name=None, project_id=None):
        context = resolve_calib_context(username, chip_id, project_id=project_id)
        session = CalibrationSession.from_context(context)
        return session.run(
            targets=QubitTargets(qids),
            steps=[
                CustomOneQubit(
                    step_name="rabi_and_pulse",
                    tasks=[TaskCall(name="CheckRabi"), TaskCall(name="CreateHPIPulse")],
                )
            ],
        )
    ```
"""

from qdash.calibration import CalibrationResult, CalibrationValidation
from qdash.datamodel.task_call import TaskCall
from qdash.workflow import sweep
from qdash.workflow.service import (
    CalibContext,
    CalibContextError,
    CalibrationSession,
    CalibService,
    ConfigFileType,
    GitHubIntegration,
    GitHubPushConfig,
    calibration_flow,
    generate_execution_id,
    resolve_calib_context,
)

__all__ = [
    "CalibContext",
    "CalibContextError",
    "CalibService",
    "CalibrationResult",
    "CalibrationSession",
    "CalibrationValidation",
    "ConfigFileType",
    "GitHubIntegration",
    "GitHubPushConfig",
    "TaskCall",
    "calibration_flow",
    "generate_execution_id",
    "resolve_calib_context",
    "sweep",
]
