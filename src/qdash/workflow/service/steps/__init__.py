"""Step classes for calibration workflows.

This module defines the Step abstraction for building calibration pipelines.
Steps are composable units of calibration work that can be chained together.

Each step declares:
- `requires`: Context keys it needs from previous steps
- `provides`: Context keys it produces

Example:
    from qdash.workflow.service import CalibService
    from qdash.workflow.service.targets import MuxTargets
    from qdash.workflow.service.steps import (
        OneQubitCheck,
        OneQubitFineTune,
        FilterByMetric,
        TwoQubitCalibration,
    )

    service = CalibService(username, chip_id)
    targets = MuxTargets([0, 1, 2, 3])

    steps = [
        OneQubitCheck(),
        OneQubitFineTune(),
        FilterByMetric(metric="x90_fidelity", threshold=0.9),
        TwoQubitCalibration(),
    ]

    results = service.run(targets, steps=steps)
"""

# Base classes
from qdash.workflow.service.steps.base import (
    CalibrationStep,
    Step,
    TransformStep,
)

# Context and Pipeline
from qdash.workflow.service.steps.context import (
    Pipeline,
    StepContext,
)

# Filter steps
from qdash.workflow.service.steps.filters import (
    FilterByMetric,
    FilterByStatus,
)

# 1-Qubit steps
from qdash.workflow.service.steps.one_qubit import (
    CustomOneQubit,
    OneQubitCheck,
    OneQubitFineTune,
)

# 2-Qubit and system steps
from qdash.workflow.service.steps.two_qubit import (
    CheckSkew,
    CustomTwoQubit,
    GenerateCRSchedule,
    TwoQubitCalibration,
)

__all__ = [
    # Base classes
    "Step",
    "CalibrationStep",
    "TransformStep",
    # Context and Pipeline
    "StepContext",
    "Pipeline",
    # 1-Qubit steps
    "CustomOneQubit",
    "OneQubitCheck",
    "OneQubitFineTune",
    # Filter steps
    "FilterByMetric",
    "FilterByStatus",
    # 2-Qubit steps
    "CustomTwoQubit",
    "GenerateCRSchedule",
    "TwoQubitCalibration",
    # System steps
    "CheckSkew",
]
