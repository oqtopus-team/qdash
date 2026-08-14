"""Serializable raw-data artifacts produced by calibration tasks."""

from __future__ import annotations

from typing import Any

import numpy.typing as npt  # noqa: TC002
from pydantic import Field
from qubex.core import DataModel


class ArrayRawData(DataModel):
    """Lossless NetCDF wrapper for an unlabelled raw NumPy array."""

    data: npt.NDArray[Any]


class PreFitRawData(DataModel):
    """Pre-fit values and coordinate axes exported from an experiment result."""

    target: str
    data: npt.NDArray[Any]
    axes: dict[str, npt.NDArray[Any]] = Field(default_factory=dict)
    source_type: str
