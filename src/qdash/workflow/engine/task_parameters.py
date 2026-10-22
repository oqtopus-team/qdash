"""Task-scoped parameter settings for workflows.

``task_parameters`` maps a task name to the settings that apply only to that task::

    {
        "CheckAdaptiveChevron": {
            "run": {"shots": 256},
            "input": {"coarse_control_amplitude": 0.05},
            "update_calibration_parameters": False,
        }
    }

``run`` holds experiment configuration declared in the task's ``run_spec``.
``input`` holds overrides for calibration inputs declared in the task's
``input_spec``; they replace the resolved baseline after preprocessing.
``update_calibration_parameters`` is an execution policy, not a task parameter.

``CalibService.execute_task(parameters=...)`` takes one entry of the same form for a
single call, and the single-task flow turns a request's ``{"input": ..., "run": ...}``
overrides into the requested task's entry.
"""

from __future__ import annotations

import copy
import difflib
import warnings
from collections.abc import Mapping
from typing import Any

from qdash.workflow.sweep import SWEEP_VALUE_TYPES, Sweep

RUN = "run"
INPUT = "input"
UPDATE_CALIBRATION_PARAMETERS = "update_calibration_parameters"
_SETTING_KEYS = frozenset({RUN, INPUT, UPDATE_CALIBRATION_PARAMETERS})
_TASK_DETAILS_KEYS = _SETTING_KEYS | {"run_parameters", "input_parameters", "calibration_inputs"}


def normalize_task_parameters(
    task_parameters: Mapping[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Return a validated deep copy of ``task_parameters`` in canonical form.

    Every task entry gets ``run`` and ``input`` mappings. Run values written as
    scalars become ``{"value": ...}``, and declarative sweeps become serializable
    value/type mappings. Input values written as ``{"value": ...}`` become the
    bare value.
    """
    if task_parameters is None:
        return {}
    if not isinstance(task_parameters, Mapping):
        raise ValueError("task_parameters must be a mapping of task name to settings")
    return {
        task_name: normalize_task_settings(task_name, settings)
        for task_name, settings in task_parameters.items()
    }


def normalize_task_settings(task_name: str, settings: Any) -> dict[str, Any]:
    """Return one task's settings in canonical form (see ``normalize_task_parameters``)."""
    if settings is None:
        settings = {}
    if not isinstance(settings, Mapping):
        raise ValueError(f"task_parameters[{task_name!r}] must be a mapping")
    settings = copy.deepcopy(dict(settings))
    unknown = sorted(set(settings) - _SETTING_KEYS)
    if unknown:
        raise ValueError(
            f"task_parameters[{task_name!r}] has unknown keys {unknown}; put run "
            f"parameters under {RUN!r} and calibration input overrides under {INPUT!r}"
        )
    entry: dict[str, Any] = {
        RUN: _normalize_run_entries(task_name, settings.get(RUN, {})),
        INPUT: _normalize_input_entries(task_name, settings.get(INPUT, {})),
    }
    if UPDATE_CALIBRATION_PARAMETERS in settings:
        value = settings[UPDATE_CALIBRATION_PARAMETERS]
        if not isinstance(value, bool):
            raise ValueError(f"update_calibration_parameters for {task_name} must be a boolean")
        entry[UPDATE_CALIBRATION_PARAMETERS] = value
    return entry


def task_settings_from_task_details(
    task_name: str,
    task_details: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Convert the deprecated ``task_details`` mapping into one task's settings.

    ``task_details[task_name]`` may hold ``run``, ``run_parameters`` or the older
    ``input_parameters`` for run parameters, ``input`` or ``calibration_inputs`` for
    calibration input overrides, and ``update_calibration_parameters``.
    """
    task_config = (task_details or {}).get(task_name, {})
    if not isinstance(task_config, Mapping):
        raise ValueError(f"Task details for {task_name} must be a mapping")
    unknown = sorted(set(task_config) - _TASK_DETAILS_KEYS)
    if unknown:
        raise ValueError(f"task_details[{task_name!r}] has unknown keys {unknown}")
    settings: dict[str, Any] = {
        RUN: {
            **task_config.get("input_parameters", {}),
            **task_config.get("run_parameters", {}),
            **task_config.get(RUN, {}),
        },
        INPUT: {**task_config.get("calibration_inputs", {}), **task_config.get(INPUT, {})},
    }
    if UPDATE_CALIBRATION_PARAMETERS in task_config:
        settings[UPDATE_CALIBRATION_PARAMETERS] = task_config[UPDATE_CALIBRATION_PARAMETERS]
    return normalize_task_settings(task_name, settings)


def task_parameters_from_run_parameters(
    task_run_parameters: Mapping[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Convert the flat ``task_run_parameters`` form into ``task_parameters``.

    The flat form keeps run parameters and ``update_calibration_parameters``
    side by side in each task entry.
    """
    if task_run_parameters is None:
        return {}
    if not isinstance(task_run_parameters, Mapping):
        raise ValueError("task_run_parameters must be a mapping of task name to parameters")
    converted: dict[str, dict[str, Any]] = {}
    for task_name, entries in task_run_parameters.items():
        if not isinstance(entries, Mapping):
            raise ValueError(f"Task run parameters for {task_name} must be a mapping")
        run = {
            name: data for name, data in entries.items() if name != UPDATE_CALIBRATION_PARAMETERS
        }
        settings: dict[str, Any] = {RUN: run}
        if UPDATE_CALIBRATION_PARAMETERS in entries:
            settings[UPDATE_CALIBRATION_PARAMETERS] = entries[UPDATE_CALIBRATION_PARAMETERS]
        converted[task_name] = settings
    return normalize_task_parameters(converted)


def resolve_task_parameters(
    task_parameters: Mapping[str, Any] | None,
    task_run_parameters: Mapping[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Combine ``task_parameters`` with the deprecated ``task_run_parameters``.

    ``task_parameters`` takes precedence for any parameter set in both.
    """
    if task_run_parameters:
        warnings.warn(
            "task_run_parameters is deprecated; use task_parameters="
            '{"<task>": {"run": {...}, "input": {...}}} instead',
            DeprecationWarning,
            stacklevel=3,
        )
    return merge_task_parameters(
        task_parameters_from_run_parameters(task_run_parameters),
        normalize_task_parameters(task_parameters),
    )


def merge_task_parameters(
    *layers: Mapping[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Merge canonical ``task_parameters`` layers; later layers win per parameter."""
    merged: dict[str, dict[str, Any]] = {}
    for layer in layers:
        for task_name, settings in layer.items():
            entry = merged.setdefault(task_name, {RUN: {}, INPUT: {}})
            entry[RUN].update(copy.deepcopy(settings.get(RUN, {})))
            entry[INPUT].update(copy.deepcopy(settings.get(INPUT, {})))
            if UPDATE_CALIBRATION_PARAMETERS in settings:
                entry[UPDATE_CALIBRATION_PARAMETERS] = settings[UPDATE_CALIBRATION_PARAMETERS]
    return merged


def validate_task_names(task_parameters: Mapping[str, Any], backend_name: str) -> None:
    """Reject task names that no task registered for ``backend_name`` uses.

    Settings under a misspelled task name would otherwise never reach a task.
    """
    from qdash.workflow.calibtasks.base import BaseTask

    registered = BaseTask.registry.get(backend_name, {})
    unknown = [name for name in task_parameters if name not in registered]
    if not unknown:
        return
    described = []
    for name in unknown:
        matches = difflib.get_close_matches(name, registered, n=1)
        described.append(f"{name!r} (did you mean {matches[0]!r}?)" if matches else repr(name))
    raise ValueError(
        f"task_parameters names tasks not registered for backend {backend_name!r}: "
        + ", ".join(described)
    )


def validate_task_settings(
    task_class: type[Any],
    task_name: str,
    settings: Mapping[str, Any],
    *,
    source: str,
) -> None:
    """Reject task-scoped names the task does not declare in the matching spec."""
    run_spec = getattr(task_class, "run_spec", {})
    input_spec = getattr(task_class, "input_spec", {})
    for name, data in settings.get(RUN, {}).items():
        if name in run_spec:
            value_type = data.get("value_type") if isinstance(data, Mapping) else None
            declared_type = run_spec[name].value_type
            if value_type in SWEEP_VALUE_TYPES and value_type != declared_type:
                raise ValueError(
                    f"{source}: {task_name}.{name} declares {declared_type!r}, "
                    f"but the workflow uses {value_type!r}"
                )
            continue
        if name in input_spec:
            raise ValueError(
                f"{source}: {name!r} is a calibration input of {task_name}; "
                f"set it under {INPUT!r} instead of {RUN!r}"
            )
        raise ValueError(f"{source}: {task_name} does not declare run parameter {name!r}")
    for name in settings.get(INPUT, {}):
        if name in input_spec:
            continue
        if name in run_spec:
            raise ValueError(
                f"{source}: {name!r} is a run parameter of {task_name}; "
                f"set it under {RUN!r} instead of {INPUT!r}"
            )
        raise ValueError(f"{source}: {task_name} does not declare calibration input {name!r}")


def _normalize_run_entries(task_name: str, entries: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(entries, Mapping):
        raise ValueError(f"task_parameters[{task_name!r}][{RUN!r}] must be a mapping")
    return {
        name: (
            data.as_run_parameter()
            if isinstance(data, Sweep)
            else dict(data)
            if isinstance(data, Mapping)
            else {"value": data}
        )
        for name, data in entries.items()
    }


def _normalize_input_entries(task_name: str, entries: Any) -> dict[str, Any]:
    if not isinstance(entries, Mapping):
        raise ValueError(f"task_parameters[{task_name!r}][{INPUT!r}] must be a mapping")
    normalized: dict[str, Any] = {}
    # Calibration inputs are scalars, so a mapping is the {"value": ...} form.
    for name, data in entries.items():
        if isinstance(data, Sweep):
            raise ValueError(
                f"task_parameters[{task_name!r}][{INPUT!r}][{name!r}] uses a sweep; "
                f"put generated experiment ranges under {RUN!r}"
            )
        value = data.get("value") if isinstance(data, Mapping) else data
        if value is None:
            raise ValueError(f"task_parameters[{task_name!r}][{INPUT!r}][{name!r}] needs a value")
        normalized[name] = value
    return normalized
