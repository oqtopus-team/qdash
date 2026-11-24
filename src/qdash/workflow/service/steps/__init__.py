"""Runtime step classes: the worker's implementation of calibration steps.

Write calibrations with the step definitions of :mod:`qdash.calibration`; the
worker converts each definition into the runtime step here, through the same
pipeline spec the SDK sends, so both run alike.

This module is the advanced, worker-only layer. A custom step subclasses
:class:`CalibrationStep` or :class:`TransformStep`, declares the context keys
it ``requires`` and ``provides``, and is passed to
``qdash.workflow.CalibrationSession.run`` among the definitions. Such a step
cannot be sent from the SDK, and the execution preview cannot read it, but it
runs. Saved flows that build these runtime classes directly keep running.

Example:
    from qdash.calibration import FilterByMetric, MuxTargets, OneQubitCheck
    from qdash.workflow import CalibrationSession
    from qdash.workflow.service.steps import CalibrationStep

    class MyStep(CalibrationStep):
        ...

    session.run(
        targets=MuxTargets([0, 1]),
        steps=[OneQubitCheck(), MyStep(), FilterByMetric(metric="t1_average", threshold=30.0)],
    )
"""

# Base classes
from qdash.workflow.service.steps.base import (
    CalibrationStep,
    Step,
    TransformStep,
)

# Box setup steps
from qdash.workflow.service.steps.box_setup import (
    ConfigureAll,
)

# MUX-level bring-up steps
from qdash.workflow.service.steps.bringup import (
    BringUp,
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

# Context and the internal step sequence validator
from qdash.workflow.service.steps.pipeline import Pipeline as Pipeline  # deprecated name
from qdash.workflow.service.steps.pipeline import (
    StepContext,
    StepSequence,
)

# 2-Qubit and system steps
from qdash.workflow.service.steps.two_qubit import (
    CustomTwoQubit,
    GenerateCRSchedule,
    TwoQubitCalibration,
)

__all__ = [
    # MUX-level bring-up steps
    "BringUp",
    "CalibrationStep",
    # Box setup steps
    "ConfigureAll",
    # 1-Qubit steps
    "CustomOneQubit",
    # 2-Qubit steps
    "CustomTwoQubit",
    # Filter steps
    "FilterByMetric",
    "FilterByStatus",
    "GenerateCRSchedule",
    "OneQubitCheck",
    "OneQubitFineTune",
    # Base classes
    "Step",
    # Context and Pipeline
    "StepContext",
    "StepSequence",
    "TransformStep",
    "TwoQubitCalibration",
]
