"""Workflow service module: the worker-side calibration API.

Main API:
    CalibrationSession: The launch's calibration session; ``run(targets, steps)``
    calibration_flow: Prefect ``@flow`` with QDash's terminal hooks and a session name
    CalibContext: The checked user, chip and project of a run
    resolve_calib_context: Resolve a CalibContext
    CalibService: Legacy entry point, kept for saved flows
    generate_execution_id: Generate unique execution IDs

Targets and steps:
    Write them with :mod:`qdash.calibration`. The runtime classes re-exported here
    (``MuxTargets``, ``OneQubitCheck``, ``Step``, ...) are the worker's implementation;
    they remain for custom steps and saved flows that build them directly.

Example:
    from qdash.calibration import FilterByMetric, MuxTargets, OneQubitCheck, OneQubitFineTune
    from qdash.workflow import CalibrationSession, calibration_flow, resolve_calib_context

    @calibration_flow(session_name="Full calibration")
    def full_calibration(username, chip_id, flow_name=None, project_id=None):
        context = resolve_calib_context(username, chip_id, project_id=project_id)
        return CalibrationSession.from_context(context).run(
            targets=MuxTargets([0, 1, 2, 3]),
            steps=[
                OneQubitCheck(),
                OneQubitFineTune(),
                FilterByMetric(metric="x90_fidelity", threshold=0.9),
            ],
            name=flow_name,
        )
"""

from qdash.datamodel.task_call import TaskCall
from qdash.workflow.service.calib_service import CalibService
from qdash.workflow.service.calibration_flow import calibration_flow
from qdash.workflow.service.calibration_session import CalibrationSession
from qdash.workflow.service.context import (
    CalibContext,
    CalibContextError,
    resolve_calib_context,
)
from qdash.workflow.service.execution_id import generate_execution_id
from qdash.workflow.service.github import (
    ConfigFileType,
    GitHubIntegration,
    GitHubPushConfig,
)
from qdash.workflow.service.steps import (
    CalibrationStep,
    ConfigureAll,
    CustomOneQubit,
    CustomTwoQubit,
    FilterByMetric,
    FilterByStatus,
    GenerateCRSchedule,
    OneQubitCheck,
    OneQubitFineTune,
    Step,
    StepContext,
    TransformStep,
    TwoQubitCalibration,
)
from qdash.workflow.service.targets import (
    AllMuxTargets,
    AllQubitTargets,
    CouplingTargets,
    MuxTargets,
    QubitTargets,
    Target,
)
from qdash.workflow.service.tasks import (
    CHECK_1Q_TASKS,
    FULL_1Q_TASKS,
    FULL_1Q_TASKS_AFTER_CHECK,
    FULL_2Q_TASKS,
)

__all__ = [
    # === Task Lists ===
    "CHECK_1Q_TASKS",
    "FULL_1Q_TASKS",
    "FULL_1Q_TASKS_AFTER_CHECK",
    "FULL_2Q_TASKS",
    "AllMuxTargets",
    "AllQubitTargets",
    # === High-level API ===
    "CalibContext",
    "CalibContextError",
    "CalibService",
    "CalibrationSession",
    "CalibrationStep",
    "ConfigFileType",
    "ConfigureAll",
    "CouplingTargets",
    "CustomOneQubit",
    "CustomTwoQubit",
    "FilterByMetric",
    "FilterByStatus",
    "GenerateCRSchedule",
    # === GitHub Integration ===
    "GitHubIntegration",
    "GitHubPushConfig",
    "MuxTargets",
    "OneQubitCheck",
    "OneQubitFineTune",
    "QubitTargets",
    # === Steps ===
    "Step",
    "StepContext",
    # === Targets ===
    "Target",
    "TaskCall",
    "TransformStep",
    "TwoQubitCalibration",
    "calibration_flow",
    "generate_execution_id",
    "resolve_calib_context",
]
