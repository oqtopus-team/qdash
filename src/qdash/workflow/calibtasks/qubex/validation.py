"""Validation helpers for qubex calibration task outputs."""

from __future__ import annotations

import math
from typing import Any


def finite_value_error(
    value: Any, name: str, *, minimum: float | None = None, maximum: float | None = None
) -> str | None:
    if value is None:
        return f"{name} is missing"
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return f"{name} is not numeric: {value}"
    if not math.isfinite(numeric_value):
        return f"{name} is non-finite: {value}"
    if minimum is not None and numeric_value < minimum:
        return f"{name} is below minimum {minimum}: {value}"
    if maximum is not None and numeric_value > maximum:
        return f"{name} is above maximum {maximum}: {value}"
    return None


def first_validation_error(*errors: str | None) -> str | None:
    return next((error for error in errors if error is not None), None)
