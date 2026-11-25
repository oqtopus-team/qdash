"""Sweep declarations for task run parameters: :mod:`qdash.calibration.sweep`.

Each helper returns a :class:`~qdash.calibration.sweep.Sweep`, which is the JSON object a
pipeline spec carries for a swept run parameter, ``{"value": [...], "value_type": ...}``.
Nothing is expanded locally: the worker builds the points from the declaration, so these
helpers need no NumPy. The same module is ``qdash.workflow.sweep``.
"""

from qdash.calibration.sweep import Sweep, arange, linspace, logspace, range, values

__all__ = ["Sweep", "arange", "linspace", "logspace", "range", "values"]
