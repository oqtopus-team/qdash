"""Sweep declarations for task run parameters.

Each helper returns a :class:`Sweep`: the constructor name and its arguments, kept until the
worker expands the points. Nothing is expanded here, so the helpers need no NumPy. A
:class:`Sweep` is also the JSON object a pipeline spec carries for a swept run parameter,
``{"value": [...], "value_type": ...}``, so it can be placed in a ``TaskCall.run`` mapping, sent
by the SDK and read by the worker unchanged.

The same module is ``qdash.workflow.sweep`` and ``qdash.sdk.sweep``.
"""

from __future__ import annotations

from typing import Any, Literal

__all__ = ["Sweep", "SweepValueType", "arange", "linspace", "logspace", "range", "values"]

SweepValueType = Literal["np.linspace", "np.logspace", "np.arange", "range", "list"]
SweepArgument = int | float


class Sweep(dict[str, Any]):
    """A serializable sweep declaration: a constructor call or explicit values.

    The mapping is the wire form, ``{"value": [...], "value_type": ...}``; ``value_type`` and
    ``arguments`` read it back.
    """

    def __init__(self, value_type: SweepValueType, arguments: tuple[SweepArgument, ...]) -> None:
        super().__init__(value=list(arguments), value_type=value_type)

    @property
    def value_type(self) -> SweepValueType:
        value_type: SweepValueType = self["value_type"]
        return value_type

    @property
    def arguments(self) -> tuple[SweepArgument, ...]:
        return tuple(self["value"])

    def as_run_parameter(self) -> dict[str, object]:
        """The canonical run-parameter representation; JSON writes ``value`` as a list."""
        return {"value": self.arguments, "value_type": self.value_type}

    def __repr__(self) -> str:
        return f"Sweep({self.value_type!r}, {self.arguments!r})"


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
    """Explicit sweep points for a run parameter that declares a generated range."""
    if not points:
        raise ValueError("sweep.values needs at least one point")
    for index, point in enumerate(points):
        _require_number("values", f"points[{index}]", point)
    return Sweep("list", tuple(points))


def linspace(start: SweepArgument, stop: SweepArgument, num: int) -> Sweep:
    """``numpy.linspace(start, stop, num)``, declared for the worker to expand."""
    _require_number("linspace", "start", start)
    _require_number("linspace", "stop", stop)
    _require_count("linspace", num)
    return Sweep("np.linspace", (start, stop, num))


def logspace(start: SweepArgument, stop: SweepArgument, num: int) -> Sweep:
    """``numpy.logspace(start, stop, num)``; ``start`` and ``stop`` are base-10 exponents."""
    _require_number("logspace", "start", start)
    _require_number("logspace", "stop", stop)
    _require_count("logspace", num)
    return Sweep("np.logspace", (start, stop, num))


def arange(start: SweepArgument, stop: SweepArgument, step: SweepArgument) -> Sweep:
    """``numpy.arange(start, stop, step)``, declared for the worker to expand."""
    for name, value in (("start", start), ("stop", stop), ("step", step)):
        _require_number("arange", name, value)
    _require_step("arange", step)
    return Sweep("np.arange", (start, stop, step))


# Named after the builtin it declares; this module does not use the builtin.
def range(start: int, stop: int, step: int) -> Sweep:
    """Python ``range(start, stop, step)``, declared for the worker to expand."""
    for name, value in (("start", start), ("stop", stop), ("step", step)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"sweep.range {name} must be an integer, got {value!r}")
    _require_step("range", step)
    return Sweep("range", (start, stop, step))
