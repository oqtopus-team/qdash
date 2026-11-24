"""Definitions for a calibration started with ``Chip.calibrate``.

The names mirror ``qdash.workflow``: :class:`QubitTargets` or :class:`MuxTargets` select the
targets, and :class:`CustomOneQubit` runs its :class:`TaskCall` list, in order, on each target
qubit. They are the same serializable classes :mod:`qdash.sdk.pipeline` defines, not the
workflow runtime classes, so building them sends no request and needs no worker packages:

.. code-block:: python

    from qdash.sdk import QDash
    from qdash.sdk.calibration import CustomOneQubit, QubitTargets, TaskCall

    qdash = QDash.from_env()
    chip = qdash.chip("64Qv3")
    targets = QubitTargets(["0", "1"])
    steps = [CustomOneQubit(step_name="t1", tasks=[TaskCall(name="CheckT1")])]
    run = chip.calibrate(targets, steps)
    print(run.wait().status)

:class:`Pipeline` holds a whole calibration, including its name, default run parameters and
tags, for ``Chip.calibrate(pipeline)``. Other step types are passed as their generated models
from :mod:`qdash.sdk.pipeline` or as dictionaries in the spec's JSON form.
"""

from qdash.sdk import sweep
from qdash.sdk.pipeline import (
    CustomOneQubit,
    MuxTargets,
    OneQubitExecutionMode,
    OnFailure,
    Pipeline,
    QubitTargets,
    TaskCall,
)

__all__ = [
    "CustomOneQubit",
    "MuxTargets",
    "OnFailure",
    "OneQubitExecutionMode",
    "Pipeline",
    "QubitTargets",
    "TaskCall",
    "sweep",
]
