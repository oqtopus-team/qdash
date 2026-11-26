"""Snapshot parameter resolution for task re-execution.

This module owns the pure data transformations that turn a recorded snapshot
of task input and run parameters into the parameters a re-executed task uses:
merging explicit overrides, seeding current run declarations, normalizing
legacy or fallback input names, checking compatibility with the current task
definition, and reconstructing parameter models.

``TaskExecutor`` owns loading the snapshot, mutating the task, and recording
state; nothing here touches the task instance or the state manager.
"""

import logging
from collections.abc import Mapping
from typing import Any, TypeVar

from qdash.datamodel.task import InputParameterSpec

logger = logging.getLogger(__name__)

_ModelT = TypeVar("_ModelT")


def merge_overrides(snapshot_dict: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Merge explicit overrides on top of snapshot parameters.

    For each key in *overrides*, if the snapshot entry is a dict with a
    ``"value"`` key the override replaces only the ``"value"`` field
    (preserving ``unit``, ``value_type``, ``description``, etc.).
    Otherwise the entry is replaced entirely.
    """
    if not overrides:
        return snapshot_dict
    merged = {**snapshot_dict}
    for key, new_value in overrides.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and "value" in existing:
            merged[key] = {**existing, "value": new_value}
        else:
            merged[key] = new_value
    return merged


def apply_run_overrides(
    snap_run: dict[str, Any],
    run_overrides: dict[str, Any],
    declared_run_parameters: Mapping[str, Any],
) -> dict[str, Any]:
    """Return snapshot run parameters with explicit run overrides applied.

    When overrides are present, parameters missing from older snapshots are
    seeded with the current declaration so explicit overrides retain their
    ``value_type`` and unrelated declared defaults remain available. Without
    overrides the snapshot is used as recorded.
    """
    if run_overrides:
        snap_run = {
            **{name: model.model_dump() for name, model in declared_run_parameters.items()},
            **snap_run,
        }
    return merge_overrides(snap_run, run_overrides)


def normalize_snapshot_inputs(
    snap_input: dict[str, Any],
    declarations: Mapping[str, Any],
) -> dict[str, Any]:
    """Map legacy alias and fallback input names onto declared input names.

    A declared input missing from the snapshot takes the value recorded under
    the first compatible name (its parameter aliases, then its fallback
    parameter names), keeping the qid-role prefix of the declared name. A
    dict value without a ``parameter_name`` records the compatible name it
    came from. Compatible entries that are not themselves declared inputs are
    dropped.
    """
    normalized_input = dict(snap_input)
    for param_name, declaration in declarations.items():
        if not isinstance(declaration, InputParameterSpec):
            continue
        lookup_key = declaration.parameter_name or param_name
        prefix = param_name[: -len(lookup_key)] if param_name.endswith(lookup_key) else ""
        compatible_names = (
            *declaration.parameter_aliases,
            *declaration.fallback_parameter_names,
        )
        for compatible_name in compatible_names:
            compatible_key = f"{prefix}{compatible_name}"
            if param_name not in normalized_input and compatible_key in snap_input:
                compatible_value = snap_input[compatible_key]
                if isinstance(compatible_value, dict):
                    compatible_value = dict(compatible_value)
                    if not compatible_value.get("parameter_name"):
                        compatible_value["parameter_name"] = compatible_name
                normalized_input[param_name] = compatible_value
            if compatible_key not in declarations:
                normalized_input.pop(compatible_key, None)
    return normalized_input


def ensure_snapshot_inputs_compatible(
    task_name: str,
    qid: str,
    snap_input: Mapping[str, Any],
    declarations: Mapping[str, Any],
) -> None:
    """Raise when a required snapshot lacks inputs the current task declares.

    Raises
    ------
    ValueError
        If any declared input is absent from the normalized snapshot inputs.
    """
    missing_inputs = set(declarations) - set(snap_input)
    if missing_inputs:
        missing = ", ".join(sorted(missing_inputs))
        raise ValueError(
            f"Snapshot inputs for task '{task_name}' and qid '{qid}' are incompatible "
            f"with the current task definition; run a fresh calibration instead. "
            f"Missing inputs: {missing}"
        )


def reconstruct_param(model_cls: type[_ModelT], key: str, value: Any) -> _ModelT | None:
    """Reconstruct a single parameter model from snapshot data.

    Returns the model instance, or None if the data is invalid.
    """
    try:
        if isinstance(value, dict):
            return model_cls(**value)
        return model_cls(value=value)  # type: ignore[call-arg]
    except (TypeError, ValueError) as e:
        logger.error("Invalid snapshot parameter %s=%r: %s", key, value, e)
        return None


def reconstruct_params(model_cls: type[_ModelT], params: Mapping[str, Any]) -> dict[str, _ModelT]:
    """Reconstruct parameter models, dropping entries whose data is invalid."""
    return {
        key: model
        for key, value in params.items()
        if (model := reconstruct_param(model_cls, key, value)) is not None
    }
