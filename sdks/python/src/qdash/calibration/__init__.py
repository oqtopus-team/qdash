"""Calibration definitions shared by the QDash SDK and QDash workflows.

The same classes describe a calibration in a script that talks to QDash through
``qdash.sdk.CalibrationSession`` and in a saved workflow that runs on the worker through
``qdash.workflow.CalibrationSession``: targets (:class:`QubitTargets`, :class:`MuxTargets`,
:class:`CouplingTargets`), the built-in steps, :class:`TaskCall` and :mod:`sweep`. Building
them sends no request, runs nothing and needs neither Prefect nor a database; they serialize
to the pipeline spec (version 2) that the server validates and the worker runs.

.. code-block:: python

    from qdash.calibration import (
        CustomOneQubit,
        ExecutionStep,
        FilterByStatus,
        QubitTargets,
        TaskCall,
        sweep,
    )

    targets = QubitTargets(["0", "1"])
    steps: list[ExecutionStep] = [
        CustomOneQubit(
            step_name="t1",
            tasks=[TaskCall(name="CheckT1", run={"time_range": sweep.linspace(0, 100_000, 51)})],
        ),
        FilterByStatus(step="t1"),
    ]

Every step is an :class:`ExecutionStep`: each one a run reaches is recorded as its own
Execution, in order, including filters and schedules that measure nothing.

:class:`CalibrationResult` and :class:`CalibrationValidation` are what both sessions' ``run``
and ``validate`` return; :class:`CalibrationRunError` is what the SDK raises for a run that
did not complete.
"""

from qdash.calibration import sweep
from qdash.calibration._spec import SPEC_VERSION, pipeline_spec, step_spec, targets_spec
from qdash.calibration._task_call import OnFailure, TaskCall
from qdash.calibration.results import (
    CalibrationResult,
    CalibrationRunError,
    CalibrationValidation,
)
from qdash.calibration.steps import (
    STEP_TYPES,
    BringUp,
    CalibrationStepDefinition,
    ConfigureAll,
    CustomOneQubit,
    CustomTwoQubit,
    ExecutionStep,
    FilterByMetric,
    FilterByStatus,
    GenerateCRSchedule,
    OneQubitCheck,
    OneQubitExecutionMode,
    OneQubitFineTune,
    OneQubitStepExecutionMode,
    TwoQubitCalibration,
    TwoQubitExecutionMode,
)
from qdash.calibration.targets import (
    CalibrationTargets,
    CouplingTargets,
    MuxTargets,
    QubitTargets,
)

__all__ = [
    "SPEC_VERSION",
    "STEP_TYPES",
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
    "QubitTargets",
    "TaskCall",
    "TwoQubitCalibration",
    "TwoQubitExecutionMode",
    "pipeline_spec",
    "step_spec",
    "sweep",
    "targets_spec",
]
