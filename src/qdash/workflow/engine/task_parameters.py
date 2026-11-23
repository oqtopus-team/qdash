"""Task-scoped parameter settings for workflows.

``task_parameters`` maps a task name to the settings that apply to every call of
that task (per-task defaults). Workflows set these settings on each ``TaskCall``;
``CalibService`` does not accept per-task defaults. The mapping is the internal
form that carries defaults QDash resolves itself (a pipeline spec's deprecated
``task_parameters`` and single-task request overrides) to owner and worker
sessions::

    {
        "CheckAdaptiveChevron": {
            "run": {"shots": 256},
            "input": {"coarse_control_amplitude": 0.05},
            "update_calibration_parameters": False,
        }
    }

A :class:`qdash.datamodel.task_call.TaskCall` in a step carries the same fields
for one call and takes precedence over these defaults. The canonical form and the
normalization live in :mod:`qdash.datamodel.task_settings` so the API normalizes a
declarative spec the same way; this module re-exports them and adds the checks
that need the task registry.

A session's ``execute_task(parameters=...)`` takes one entry of the same form for a
single call, and the single-task flow turns a request's ``{"input": ..., "run": ...}``
overrides into the requested task's entry.
"""

from __future__ import annotations

import difflib
from collections.abc import Mapping
from typing import Any

from qdash.datamodel.sweep import compatible_value_type
from qdash.datamodel.task_settings import (
    INPUT,
    RUN,
    SETTING_KEYS,
    UPDATE_CALIBRATION_PARAMETERS,
    merge_task_parameters,
    normalize_default_run_parameters,
    normalize_task_parameters,
    normalize_task_settings,
    task_parameters_from_run_parameters,
    task_settings_from_task_details,
)

__all__ = [
    "INPUT",
    "RUN",
    "SETTING_KEYS",
    "UPDATE_CALIBRATION_PARAMETERS",
    "merge_task_parameters",
    "normalize_default_run_parameters",
    "normalize_task_parameters",
    "normalize_task_settings",
    "task_parameters_from_run_parameters",
    "task_settings_from_task_details",
    "validate_sweep_type",
    "validate_task_names",
    "validate_task_settings",
]


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
            validate_sweep_type(task_class, task_name, name, data, source=source)
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


def validate_sweep_type(
    task_class: type[Any],
    task_name: str,
    name: str,
    data: Any,
    *,
    source: str,
) -> None:
    """Reject a value whose ``value_type`` the declared ``run_spec`` type cannot take.

    A parameter declared with a sweep constructor takes any sweep constructor or
    explicit ``list`` values. A sweep for a scalar parameter, or a scalar for a sweep
    parameter, fails here with the workflow source instead of inside the task.
    """
    value_type = data.get("value_type") if isinstance(data, Mapping) else None
    declared_type = task_class.run_spec[name].value_type
    if not compatible_value_type(declared_type, value_type):
        raise ValueError(
            f"{source}: {task_name}.{name} declares {declared_type!r} "
            f"and cannot take a {value_type!r} value"
        )
