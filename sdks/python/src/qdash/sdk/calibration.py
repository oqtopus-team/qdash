"""Calibration definitions for the SDK: the shared :mod:`qdash.calibration` classes.

The same targets, steps, :class:`TaskCall` and :mod:`sweep` describe a calibration here and in
a saved workflow (``qdash.workflow.CalibrationSession``), and serialize to the pipeline spec
the server validates and the worker runs. Building them sends no request and needs no worker
packages:

.. code-block:: python

    from qdash.sdk import CalibrationSession, QDash
    from qdash.sdk.calibration import CustomOneQubit, QubitTargets, TaskCall

    client = QDash.from_env()
    session = CalibrationSession.create(client, chip_id="64Qv3", name="T1 check")
    result = session.run(
        targets=QubitTargets(["0", "1"]),
        steps=[CustomOneQubit(step_name="t1", tasks=[TaskCall(name="CheckT1")])],
    )

:class:`Pipeline` (from :mod:`qdash.sdk.pipeline`) holds a whole spec for the legacy
``Chip.calibrate(pipeline)``; it accepts these definitions too.
"""

from qdash.calibration import (
    BringUp,
    CalibrationResult,
    CalibrationRunError,
    CalibrationStepDefinition,
    CalibrationTargets,
    CalibrationValidation,
    ConfigureAll,
    CouplingTargets,
    CustomOneQubit,
    CustomTwoQubit,
    ExecutionStep,
    FilterByMetric,
    FilterByStatus,
    GenerateCRSchedule,
    MuxTargets,
    OneQubitCheck,
    OneQubitExecutionMode,
    OneQubitFineTune,
    OneQubitStepExecutionMode,
    OnFailure,
    QubitTargets,
    TaskCall,
    TwoQubitCalibration,
    TwoQubitExecutionMode,
    sweep,
)
from qdash.sdk.pipeline import Pipeline

__all__ = [
    "BringUp",
    "CalibrationResult",
    "CalibrationRunError",
    "CalibrationStepDefinition",
    "CalibrationTargets",
    "CalibrationValidation",
    "ConfigureAll",
    "CouplingTargets",
    "CustomOneQubit",
    "CustomTwoQubit",
    "ExecutionStep",
    "FilterByMetric",
    "FilterByStatus",
    "GenerateCRSchedule",
    "MuxTargets",
    "OnFailure",
    "OneQubitCheck",
    "OneQubitExecutionMode",
    "OneQubitFineTune",
    "OneQubitStepExecutionMode",
    "Pipeline",
    "QubitTargets",
    "TaskCall",
    "TwoQubitCalibration",
    "TwoQubitExecutionMode",
    "sweep",
]
