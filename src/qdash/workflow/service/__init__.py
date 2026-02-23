"""Workflow service module for Python Flow Editor.

This module provides the main calibration API with a step-based pipeline approach.

Main API:
    CalibService: High-level API for calibration workflows
    generate_execution_id: Generate unique execution IDs

Targets:
    Target: Abstract base class for calibration targets
    MuxTargets: Target qubits by MUX IDs
    QubitTargets: Target specific qubit IDs
    CouplingTargets: Target specific coupling pairs
    AllMuxTargets: Target all MUXes (full chip)

Steps:
    Step: Abstract base class for calibration steps
    StepContext: Context shared between steps
    OneQubitCheck: Basic 1Q characterization
    OneQubitFineTune: Advanced 1Q calibration (DRAG, RB)
    CustomOneQubit: Custom 1Q calibration with user-defined tasks
    CustomTwoQubit: Custom 2Q calibration with user-defined tasks
    FilterByMetric: Filter qubits by named metric threshold
    FilterByStatus: Filter qubits by success status
    GenerateCRSchedule: Generate CR schedule for 2Q calibration
    TwoQubitCalibration: 2Q coupling calibration
    CheckSkew: System-level skew check

Example:
    from prefect import flow
    from qdash.workflow.service import CalibService
    from qdash.workflow.service.targets import MuxTargets
    from qdash.workflow.service.steps import (
        OneQubitCheck,
        OneQubitFineTune,
        FilterByMetric,
        TwoQubitCalibration,
    )

    @flow
    def full_calibration(username: str, chip_id: str):
        cal = CalibService(username, chip_id)
        targets = MuxTargets([0, 1, 2, 3])

        results = cal.run(targets, steps=[
            OneQubitCheck(),
            OneQubitFineTune(),
            FilterByMetric(metric="x90_fidelity", threshold=0.9),
            TwoQubitCalibration(),
        ])
        return results
"""

from qdash.workflow.service.calib_service import CalibService
from qdash.workflow.service.execution_id import generate_execution_id
from qdash.workflow.service.github import (
    ConfigFileType,
    GitHubIntegration,
    GitHubPushConfig,
)
from qdash.workflow.service.session_context import (
    SessionContext,
    clear_current_session,
    get_current_session,
    set_current_session,
)
from qdash.workflow.service.steps import (
    CalibrationStep,
    CheckSkew,
    CustomOneQubit,
    CustomTwoQubit,
    FilterByMetric,
    FilterByStatus,
    GenerateCRSchedule,
    OneQubitCheck,
    OneQubitFineTune,
    Pipeline,
    Step,
    StepContext,
    TransformStep,
    TwoQubitCalibration,
)
from qdash.workflow.service.targets import (
    AllMuxTargets,
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
    # === High-level API ===
    "CalibService",
    "generate_execution_id",
    # === Targets ===
    "Target",
    "MuxTargets",
    "QubitTargets",
    "CouplingTargets",
    "AllMuxTargets",
    # === Steps ===
    "Step",
    "CalibrationStep",
    "TransformStep",
    "StepContext",
    "Pipeline",
    "OneQubitCheck",
    "OneQubitFineTune",
    "CustomOneQubit",
    "CustomTwoQubit",
    "FilterByMetric",
    "FilterByStatus",
    "GenerateCRSchedule",
    "TwoQubitCalibration",
    "CheckSkew",
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
