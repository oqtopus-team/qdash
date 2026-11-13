"""Validation helpers for qubex calibration tasks."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qubex import Experiment

DEFAULT_RABI_R2_THRESHOLD = 0.6


def require_ef_configuration(exp: Experiment, label: str) -> None:
    """Require actual GE and EF targets, not legacy aliases."""
    try:
        exp.targets[exp.ctx.resolve_ge_label(label)]
        exp.targets[exp.ctx.resolve_ef_label(label)]
    except (KeyError, ValueError) as exc:
        raise ValueError(
            f"GE/EF targets are not configured for {label}. Start the session with an "
            "EF-capable configuration_mode, or run ConfigureEF in the same session, before "
            "running an EF-dependent task."
        ) from exc


def require_fh_configuration(exp: Experiment, label: str) -> None:
    """Require actual GE, EF, and FH targets for an FH-dependent task."""
    try:
        exp.targets[exp.ctx.resolve_ge_label(label)]
        exp.targets[exp.ctx.resolve_ef_label(label)]
        exp.targets[exp.ctx.resolve_fh_label(label)]
    except (KeyError, ValueError) as exc:
        raise ValueError(
            f"GE/EF/FH targets are not configured for {label}. Start the session with "
            "configuration_mode='ge-ef-fh', or run ConfigureEF with that mode in the same "
            "session, before running an FH-dependent task."
        ) from exc


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
