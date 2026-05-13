"""Compact formatting helpers for Copilot LLM-facing payloads."""

from __future__ import annotations

import math
from typing import Any


def compact_number(value: Any) -> Any:
    """Round floats to 4 significant figures to save tokens."""
    if not isinstance(value, float) or not math.isfinite(value):
        return value
    if value == 0.0:
        return 0.0
    magnitude = math.floor(math.log10(abs(value)))
    rounded = round(value, -magnitude + 3)  # 4 significant figures
    if rounded == int(rounded) and abs(rounded) < 1e15:
        return int(rounded)
    return rounded


def compact_timestamp(iso_str: str | None) -> str:
    """Shorten ISO timestamp: '2026-02-24T02:22:04.211000' -> '02-24 02:22'."""
    if not iso_str:
        return ""
    try:
        date_part, _, time_part = iso_str.partition("T")
        month_day = date_part[5:10]
        hour_min = time_part[:5]
        return f"{month_day} {hour_min}"
    except (IndexError, ValueError):
        return iso_str[:16]


def compact_output_parameters(params: dict[str, Any]) -> dict[str, Any]:
    """Compress output_parameters to {param_name: {value, unit, error}}."""
    result: dict[str, Any] = {}
    for name, data in params.items():
        if not isinstance(data, dict):
            result[name] = data
            continue
        compact: dict[str, Any] = {"value": compact_number(data.get("value"))}
        unit = data.get("unit")
        if unit:
            compact["unit"] = unit
        error = data.get("error")
        if error and error != 0:
            compact["error"] = compact_number(error)
        result[name] = compact
    return result
