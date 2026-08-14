"""Extract Qubex-compatible NetCDF artifacts from task run results."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import is_dataclass
from typing import Any

import numpy as np
from qubex.core import DataModel

from qdash.common.raw_data import PreFitRawData

_AXIS_NAMES = (
    "sweep_range",
    "time_range",
    "frequency_range",
    "amplitude_range",
    "detuning_range",
)


def extract_qubex_raw_data(value: Any) -> list[DataModel]:
    """Extract canonical Qubex models or legacy pre-fit target data recursively."""
    artifacts: list[DataModel] = []
    seen: set[int] = set()

    def visit(item: Any) -> None:
        if item is None or isinstance(item, (str, bytes, int, float, bool, np.generic)):
            return

        item_id = id(item)
        if item_id in seen:
            return
        seen.add(item_id)

        if isinstance(item, DataModel):
            artifacts.append(item)
            return

        if is_dataclass(item) and hasattr(item, "target"):
            data = getattr(item, "data", getattr(item, "raw", None))
            if isinstance(data, np.ndarray):
                axes = {
                    name: np.asarray(getattr(item, name))
                    for name in _AXIS_NAMES
                    if getattr(item, name, None) is not None
                }
                artifacts.append(
                    PreFitRawData(
                        target=str(getattr(item, "target", "")),
                        data=np.asarray(data),
                        axes=axes,
                        source_type=f"{type(item).__module__}.{type(item).__name__}",
                    )
                )
                return

        if isinstance(item, Mapping):
            for nested in item.values():
                visit(nested)
            return

        if isinstance(item, Sequence) and not isinstance(item, np.ndarray):
            for nested in item:
                visit(nested)
            return

        nested_data = getattr(item, "data", None)
        if isinstance(nested_data, Mapping):
            visit(nested_data)

    visit(value)
    return artifacts
