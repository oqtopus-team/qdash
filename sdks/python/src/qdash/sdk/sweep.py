"""Sweep declarations for task run parameters, in the pipeline spec's wire format.

Each helper returns the JSON object a pipeline spec carries for a swept run parameter,
``{"value": [...], "value_type": ...}``. Nothing is expanded locally: the worker builds the
points from the declaration, so these helpers need no NumPy. They match
``qdash.workflow.sweep`` constructor for constructor.
"""

from __future__ import annotations

from typing import Any

__all__ = ["arange", "linspace", "logspace", "range", "values"]

Number = int | float


def _number(constructor: str, name: str, value: object) -> None:
    # bool is an int subclass, but True as a bound or step is a mistake.
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"sweep.{constructor} {name} must be a number, got {value!r}")


def _count(constructor: str, num: object) -> None:
    if isinstance(num, bool) or not isinstance(num, int) or num < 1:
        raise ValueError(f"sweep.{constructor} num must be a positive integer, got {num!r}")


def _declaration(value_type: str, arguments: list[Number]) -> dict[str, Any]:
    return {"value": arguments, "value_type": value_type}


def values(*points: Number) -> dict[str, Any]:
    """Explicit sweep points: ``{"value": [p0, p1, ...], "value_type": "list"}``."""
    if not points:
        raise ValueError("sweep.values needs at least one point")
    for index, point in enumerate(points):
        _number("values", f"points[{index}]", point)
    return _declaration("list", list(points))


def linspace(start: Number, stop: Number, num: int) -> dict[str, Any]:
    """``numpy.linspace(start, stop, num)``, declared for the worker to expand."""
    _number("linspace", "start", start)
    _number("linspace", "stop", stop)
    _count("linspace", num)
    return _declaration("np.linspace", [start, stop, num])


def logspace(start: Number, stop: Number, num: int) -> dict[str, Any]:
    """``numpy.logspace(start, stop, num)``; ``start`` and ``stop`` are base-10 exponents."""
    _number("logspace", "start", start)
    _number("logspace", "stop", stop)
    _count("logspace", num)
    return _declaration("np.logspace", [start, stop, num])


def arange(start: Number, stop: Number, step: Number) -> dict[str, Any]:
    """``numpy.arange(start, stop, step)``, declared for the worker to expand."""
    for name, value in (("start", start), ("stop", stop), ("step", step)):
        _number("arange", name, value)
    if step == 0:
        raise ValueError("sweep.arange step must not be zero")
    return _declaration("np.arange", [start, stop, step])


# Named after the builtin it declares; this module does not use the builtin.
def range(start: int, stop: int, step: int) -> dict[str, Any]:
    """Python ``range(start, stop, step)``, declared for the worker to expand."""
    for name, value in (("start", start), ("stop", stop), ("step", step)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"sweep.range {name} must be an integer, got {value!r}")
    if step == 0:
        raise ValueError("sweep.range step must not be zero")
    return _declaration("range", [start, stop, step])
