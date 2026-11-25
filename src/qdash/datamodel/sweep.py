"""Declarative sweep values for workflow run parameters.

The helpers in this module retain the constructor name and arguments until
task settings are normalized. They do not materialize NumPy arrays in a
workflow definition. The declarations are :mod:`qdash.calibration.sweep`, the module
the SDK sends and flow authors import, so the API validates sweeps in a declarative
pipeline spec exactly as the worker does; this module adds the value type rules.
"""

from __future__ import annotations

from qdash.calibration.sweep import (
    Sweep,
    SweepArgument,
    SweepValueType,
    arange,
    linspace,
    logspace,
    range,
    values,
)
from qdash.datamodel.task import (
    SWEEP_OVERRIDE_VALUE_TYPES,
    SWEEP_VALUE_TYPES,
    compatible_value_type,
    is_sweep_value_type,
)

__all__ = [
    "SWEEP_OVERRIDE_VALUE_TYPES",
    "SWEEP_VALUE_TYPES",
    "Sweep",
    "SweepArgument",
    "SweepValueType",
    "arange",
    "compatible_value_type",
    "is_sweep_value_type",
    "linspace",
    "logspace",
    "range",
    "values",
]
