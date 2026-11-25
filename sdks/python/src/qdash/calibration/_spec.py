"""Serializing targets and steps to a pipeline spec, version 2."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from qdash.calibration.steps import ExecutionStep
from qdash.calibration.targets import CalibrationTargets

__all__ = ["SPEC_VERSION", "pipeline_spec", "step_spec", "targets_spec"]

SPEC_VERSION = 2


def targets_spec(targets: Any) -> dict[str, Any]:
    """The ``targets`` JSON object of a target definition, a spec model or a mapping."""
    if isinstance(targets, CalibrationTargets):
        return targets.to_spec()
    if isinstance(targets, Mapping):
        return dict(targets)
    dump = getattr(targets, "model_dump", None)
    if callable(dump):
        return dict(dump(mode="json", exclude_unset=True))
    raise TypeError(
        "targets must be QubitTargets, MuxTargets, CouplingTargets or a mapping, "
        f"got {type(targets).__name__}"
    )


def step_spec(step: Any) -> dict[str, Any]:
    """The JSON object of one step: a step definition, a spec model with ``type``, or a mapping."""
    if isinstance(step, ExecutionStep):
        return step.to_spec()
    if isinstance(step, Mapping):
        return dict(step)
    dump = getattr(step, "model_dump", None)
    step_type = getattr(step, "type", None)
    if callable(dump) and isinstance(step_type, str):
        return {**dump(mode="json", exclude_unset=True), "type": step_type}
    raise TypeError(
        f"steps must be qdash.calibration step definitions or mappings, got {type(step).__name__}"
    )


def pipeline_spec(
    targets: Any,
    steps: Sequence[Any],
    *,
    name: str | None = None,
    default_run_parameters: Mapping[str, Any] | None = None,
    tags: Sequence[str] | None = None,
) -> dict[str, Any]:
    """The pipeline spec JSON for ``targets`` and ``steps``; unset options are left out.

    Sweeps in ``default_run_parameters`` are written in their wire form.
    """
    if isinstance(steps, str | bytes) or not isinstance(steps, Sequence):
        raise TypeError("steps must be a list of steps")
    spec: dict[str, Any] = {
        "spec_version": SPEC_VERSION,
        "targets": targets_spec(targets),
        "steps": [step_spec(step) for step in steps],
    }
    if name is not None:
        spec["name"] = name
    if default_run_parameters is not None:
        spec["default_run_parameters"] = {
            str(key): dict(value) if isinstance(value, Mapping) else value
            for key, value in default_run_parameters.items()
        }
    if tags is not None:
        spec["tags"] = list(tags)
    return spec
