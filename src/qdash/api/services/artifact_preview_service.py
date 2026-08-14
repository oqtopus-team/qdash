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


def _axis_variables(
    dataset: Dataset,
    shape: tuple[int, ...],
    coordinates: list[tuple[int, ...]],
) -> list[tuple[str, dict[int, Any]]]:
    axes = [
        (name.removeprefix("axes_"), variable)
        for name, variable in dataset.variables.items()
        if name.startswith("axes_")
    ]

    matched: list[tuple[str, dict[int, Any]]] = []
    unused = list(axes)
    for dimension, size in enumerate(shape):
        match_index = next(
            (index for index, (_, variable) in enumerate(unused) if variable.size == size),
            None,
        )
        required_indices = {coordinate[dimension] for coordinate in coordinates}
        if match_index is None:
            matched.append((f"index_{dimension}", {index: index for index in required_indices}))
        else:
            name, variable = unused.pop(match_index)
            matched.append(
                (
                    name,
                    {index: np.asarray(variable[index]).item() for index in required_indices},
                )
            )
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
        preview_size = min(total_rows, limit)
        coordinates: list[tuple[int, ...]] = (
            [
                tuple(int(coordinate) for coordinate in np.unravel_index(index, shape))
                for index in range(preview_size)
            ]
            if shape
            else [()]
        )
        axes = _axis_variables(dataset, shape, coordinates)
        if shape:
            flat_data = np.asarray([data_variable[coordinate] for coordinate in coordinates])
        else:
            flat_data = np.asarray([data_variable[()]])

        is_complex = bool(data_variable.dtype.fields) and {"r", "i"}.issubset(
            data_variable.dtype.fields or {}
        )
        value_columns = ["real", "imag", "abs"] if is_complex else ["value"]
        columns = [name for name, _ in axes] + value_columns
        rows: list[dict[str, int | float | str | bool | None]] = []

        for coordinate, value in zip(coordinates, flat_data, strict=True):
            row = {
                name: _json_scalar(values[index])
                for (name, values), index in zip(axes, coordinate, strict=True)
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
