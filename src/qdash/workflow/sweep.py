"""Declarative sweep values for workflow run parameters.

The helpers in this module retain the constructor name and arguments until
``task_parameters`` is normalized. They do not materialize NumPy arrays in a
workflow definition.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SweepValueType = Literal["np.linspace", "np.logspace", "np.arange", "range"]
SweepArgument = int | float
SWEEP_VALUE_TYPES = frozenset({"np.linspace", "np.logspace", "np.arange", "range"})


@dataclass(frozen=True, slots=True)
class Sweep:
    """A serializable declaration of a three-argument sweep."""

    value_type: SweepValueType
    arguments: tuple[SweepArgument, SweepArgument, SweepArgument]

    def as_run_parameter(self) -> dict[str, object]:
        """Return the canonical run-parameter representation."""
        return {"value": self.arguments, "value_type": self.value_type}


def linspace(start: SweepArgument, stop: SweepArgument, num: int) -> Sweep:
    """Declare ``numpy.linspace(start, stop, num)`` for a run parameter."""
    return Sweep("np.linspace", (start, stop, num))


def logspace(start: SweepArgument, stop: SweepArgument, num: int) -> Sweep:
    """Declare ``numpy.logspace(start, stop, num)`` for a run parameter."""
    return Sweep("np.logspace", (start, stop, num))


def arange(start: SweepArgument, stop: SweepArgument, step: SweepArgument) -> Sweep:
    """Declare ``numpy.arange(start, stop, step)`` for a run parameter."""
    return Sweep("np.arange", (start, stop, step))


def range(start: int, stop: int, step: int) -> Sweep:
    """Declare ``range(start, stop, step)`` for a run parameter."""
    return Sweep("range", (start, stop, step))
