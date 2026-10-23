"""Declarative sweep values for workflow run parameters.

The helpers in this module retain the constructor name and arguments until
``task_parameters`` is normalized. They do not materialize NumPy arrays in a
workflow definition.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

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
    "arange",
    "compatible_value_type",
    "is_sweep_value_type",
    "linspace",
    "logspace",
    "range",
    "values",
]

SweepValueType = Literal["np.linspace", "np.logspace", "np.arange", "range", "list"]
SweepArgument = int | float


@dataclass(frozen=True, slots=True)
class Sweep:
    """A serializable declaration of a sweep: a constructor call or explicit values."""

    value_type: SweepValueType
    arguments: tuple[SweepArgument, ...]

    def as_run_parameter(self) -> dict[str, object]:
        """Return the canonical run-parameter representation."""
        return {"value": self.arguments, "value_type": self.value_type}


def _require_number(constructor: str, name: str, value: object) -> None:
    # bool is an int subclass, but True as a bound or step is a mistake.
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"sweep.{constructor} {name} must be a number, got {value!r}")


def _require_count(constructor: str, num: object) -> None:
    if isinstance(num, bool) or not isinstance(num, int) or num < 1:
        raise ValueError(f"sweep.{constructor} num must be a positive integer, got {num!r}")


def _require_step(constructor: str, step: SweepArgument) -> None:
    if step == 0:
        raise ValueError(f"sweep.{constructor} step must not be zero")


def values(*points: SweepArgument) -> Sweep:
    """Declare explicit sweep points for a run parameter that declares a generated range."""
    if not points:
        raise ValueError("sweep.values needs at least one point")
    for index, point in enumerate(points):
        _require_number("values", f"points[{index}]", point)
    return Sweep("list", tuple(points))


def linspace(start: SweepArgument, stop: SweepArgument, num: int) -> Sweep:
    """Declare ``numpy.linspace(start, stop, num)`` for a run parameter."""
    _require_number("linspace", "start", start)
    _require_number("linspace", "stop", stop)
    _require_count("linspace", num)
    return Sweep("np.linspace", (start, stop, num))


def logspace(start: SweepArgument, stop: SweepArgument, num: int) -> Sweep:
    """Declare ``numpy.logspace(start, stop, num)`` for a run parameter."""
    _require_number("logspace", "start", start)
    _require_number("logspace", "stop", stop)
    _require_count("logspace", num)
    return Sweep("np.logspace", (start, stop, num))


def arange(start: SweepArgument, stop: SweepArgument, step: SweepArgument) -> Sweep:
    """Declare ``numpy.arange(start, stop, step)`` for a run parameter."""
    for name, value in (("start", start), ("stop", stop), ("step", step)):
        _require_number("arange", name, value)
    _require_step("arange", step)
    return Sweep("np.arange", (start, stop, step))


# Named after the builtin it declares; this module does not use the builtin.
def range(start: int, stop: int, step: int) -> Sweep:
    """Declare ``range(start, stop, step)`` for a run parameter."""
    for name, value in (("start", start), ("stop", stop), ("step", step)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"sweep.range {name} must be an integer, got {value!r}")
    _require_step("range", step)
    return Sweep("range", (start, stop, step))
