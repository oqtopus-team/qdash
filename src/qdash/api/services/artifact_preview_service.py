"""Build lightweight table previews for calibration artifacts."""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING, Any

import numpy as np
from netCDF4 import Dataset

from qdash.api.schemas.execution import ArtifactPreviewResponse

if TYPE_CHECKING:
    from pathlib import Path

_PREVIEW_ROW_LIMIT = 50


def _json_metadata(dataset: Dataset) -> dict[str, Any]:
    if "payload_json" not in dataset.ncattrs():
        return {}
    try:
        payload = json.loads(str(dataset.getncattr("payload_json")))
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _json_scalar(value: Any) -> int | float | str | bool | None:
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    return str(value)


def _optional_string(value: Any) -> str | None:
    """Normalize optional NetCDF metadata to the API schema type."""
    return None if value is None else str(value)


def _axis_variables(dataset: Dataset, shape: tuple[int, ...]) -> list[tuple[str, np.ndarray]]:
    axes: list[tuple[str, np.ndarray]] = []
    for name, variable in dataset.variables.items():
        if not name.startswith("axes_"):
            continue
        values = np.asarray(variable[:]).reshape(-1)
        axes.append((name.removeprefix("axes_"), values))

    matched: list[tuple[str, np.ndarray]] = []
    unused = list(axes)
    for dimension, size in enumerate(shape):
        match_index = next(
            (index for index, (_, values) in enumerate(unused) if values.size == size),
            None,
        )
        if match_index is None:
            matched.append((f"index_{dimension}", np.arange(size)))
        else:
            matched.append(unused.pop(match_index))
    return matched


def preview_netcdf(path: Path, limit: int = _PREVIEW_ROW_LIMIT) -> ArtifactPreviewResponse:
    """Read at most ``limit`` flattened values from a QDash/Qubex NetCDF file."""
    with Dataset(path, mode="r") as dataset:
        metadata = _json_metadata(dataset)
        variables = dataset.variables
        if not variables:
            raise ValueError("NetCDF artifact contains no data variables")

        data_name = (
            "data" if "data" in variables else max(variables, key=lambda name: variables[name].size)
        )
        data_variable = variables[data_name]
        shape = tuple(int(size) for size in data_variable.shape)
        total_rows = int(data_variable.size)
        axes = _axis_variables(dataset, shape)
        preview_size = min(total_rows, limit)
        if shape:
            flat_data = np.asarray(
                [data_variable[np.unravel_index(index, shape)] for index in range(preview_size)]
            )
        else:
            flat_data = np.asarray([data_variable[()]])

        is_complex = bool(data_variable.dtype.fields) and {"r", "i"}.issubset(
            data_variable.dtype.fields or {}
        )
        value_columns = ["real", "imag", "abs"] if is_complex else ["value"]
        columns = [name for name, _ in axes] + value_columns
        rows: list[dict[str, int | float | str | bool | None]] = []

        for flat_index, value in enumerate(flat_data):
            coordinates = np.unravel_index(flat_index, shape) if shape else ()
            row = {
                name: _json_scalar(values[index])
                for (name, values), index in zip(axes, coordinates, strict=True)
            }
            if is_complex:
                real = float(value["r"])
                imag = float(value["i"])
                row.update(real=real, imag=imag, abs=math.hypot(real, imag))
            else:
                row["value"] = _json_scalar(value)
            rows.append(row)

    return ArtifactPreviewResponse(
        filename=path.name,
        target=_optional_string(metadata.get("target")),
        source_type=_optional_string(metadata.get("source_type")),
        shape=list(shape),
        dtype="complex" if is_complex else str(data_variable.dtype),
        columns=columns,
        rows=rows,
        total_rows=total_rows,
        truncated=total_rows > limit,
    )
