"""Canonical form of task-scoped settings, shared by the API and the worker.

A task settings entry holds the settings that apply to one task::

    {
        "run": {"shots": 256},
        "input": {"coarse_control_amplitude": 0.05},
        "update_calibration_parameters": False,
    }

``run`` holds experiment configuration declared in the task's ``run_spec``.
``input`` holds overrides for calibration inputs declared in the task's
``input_spec``; they replace the resolved baseline after preprocessing.
``update_calibration_parameters`` is an execution policy, not a task parameter;
when it is absent the next layer decides.

``task_parameters`` maps a task name to such an entry and acts as the common
per-task defaults of a workflow. A :class:`qdash.datamodel.task_call.TaskCall`
carries the same fields for one call. This module has no workflow imports so the
API validates declarative specs with the same normalization the worker applies.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from qdash.datamodel.sweep import Sweep

RUN = "run"
INPUT = "input"
UPDATE_CALIBRATION_PARAMETERS = "update_calibration_parameters"
SETTING_KEYS = frozenset({RUN, INPUT, UPDATE_CALIBRATION_PARAMETERS})
_TASK_DETAILS_KEYS = SETTING_KEYS | {"run_parameters", "input_parameters", "calibration_inputs"}


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


def normalize_default_run_parameters(
    default_run_parameters: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return shared run defaults in the same canonical value form as task settings.

    Flat values and sweep declarations become ``{"value": ...}`` mappings. Legacy
    task-nested defaults remain supported and their parameter values are normalized
    recursively.
    """
    if default_run_parameters is None:
        return {}
    if not isinstance(default_run_parameters, Mapping):
        raise ValueError("default_run_parameters must be a mapping of parameter names to values")

    normalized: dict[str, Any] = {}
    for name, data in copy.deepcopy(dict(default_run_parameters)).items():
        if isinstance(data, Mapping) and "value" not in data and "value_type" not in data:
            nested: dict[str, Any] = {}
            for parameter_name, parameter_data in data.items():
                if parameter_name == UPDATE_CALIBRATION_PARAMETERS:
                    nested[parameter_name] = parameter_data
                else:
                    nested[parameter_name] = _normalize_run_value(parameter_data)
            normalized[name] = nested
        else:
            normalized[name] = _normalize_run_value(data)
    return normalized


def normalize_task_settings(task_name: str, settings: Any) -> dict[str, Any]:
    """Return one task's settings in canonical form (see ``normalize_task_parameters``)."""
    if settings is None:
        settings = {}
    if not isinstance(settings, Mapping):
        raise ValueError(f"task_parameters[{task_name!r}] must be a mapping")
    settings = copy.deepcopy(dict(settings))
    unknown = sorted(set(settings) - SETTING_KEYS)
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


def normalize_run_entries(owner: str, entries: Any) -> dict[str, dict[str, Any]]:
    """Return run values in canonical ``{"value": ..., "value_type": ...}`` form.

    Plain values become ``{"value": ...}``, :class:`Sweep` declarations become
    their value/type mapping, and mappings are kept as written. ``owner`` names
    the settings in error messages, e.g. ``task_parameters['CheckRabi']``.
    """
    if not isinstance(entries, Mapping):
        raise ValueError(f"{owner}[{RUN!r}] must be a mapping")
    return {str(name): _normalize_run_value(data) for name, data in entries.items()}


def normalize_input_entries(owner: str, entries: Any) -> dict[str, Any]:
    """Return calibration input overrides as bare values (see ``normalize_run_entries``)."""
    if not isinstance(entries, Mapping):
        raise ValueError(f"{owner}[{INPUT!r}] must be a mapping")
    normalized: dict[str, Any] = {}
    # Calibration inputs are scalars, so a mapping is the {"value": ...} form.
    for name, data in entries.items():
        if isinstance(data, Sweep):
            raise ValueError(
                f"{owner}[{INPUT!r}][{name!r}] uses a sweep; "
                f"put generated experiment ranges under {RUN!r}"
            )
        value = data.get("value") if isinstance(data, Mapping) else data
        if value is None:
            raise ValueError(f"{owner}[{INPUT!r}][{name!r}] needs a value")
        normalized[str(name)] = value
    return normalized


def _normalize_run_entries(task_name: str, entries: Any) -> dict[str, dict[str, Any]]:
    return normalize_run_entries(f"task_parameters[{task_name!r}]", entries)


def _normalize_run_value(data: Any) -> dict[str, Any]:
    if isinstance(data, Sweep):
        return data.as_run_parameter()
    if isinstance(data, Mapping):
        return dict(data)
    return {"value": data}


def _normalize_input_entries(task_name: str, entries: Any) -> dict[str, Any]:
    return normalize_input_entries(f"task_parameters[{task_name!r}]", entries)
