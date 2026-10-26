"""Run one task from the task catalog, as the Task Workbench does.

A catalog run resolves its inputs from the current calibration state and opens
the Qubex session with the task's own ``readout_duration``, so the session and
the task always agree. The Task Workbench and agent actions both start runs
through here, so they share one path and one set of override checks.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, status

from qdash.common.config.backend import (
    get_available_backends,
    get_default_backend,
    is_task_available,
)
from qdash.common.config.calibration import DEFAULT_READOUT_DURATION
from qdash.datamodel.task import compatible_value_type

if TYPE_CHECKING:
    from qdash.api.schemas.flow import ExecuteFlowResponse
    from qdash.api.schemas.task_file import TaskInfo
    from qdash.api.services.flow_service import FlowService
    from qdash.api.services.task_file_service import TaskFileService


def matches_parameter_type(value: object, value_type: object) -> bool:
    """Return whether a JSON value matches a known task parameter type."""
    if value_type == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if value_type == "float":
        return (
            isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        )
    if value_type == "bool":
        return isinstance(value, bool)
    if value_type == "list":
        return isinstance(value, list)
    if value_type in {"np.linspace", "np.logspace", "np.arange", "range"}:
        return isinstance(value, list) and len(value) == 3
    if value_type in {"str", "string"}:
        return isinstance(value, str)
    return True


def run_override_parts(override: Any) -> tuple[Any, str | None]:
    """Split a run override into its value and the ``value_type`` it carries, if any.

    A run override is either a bare value, which takes the task's declared type, or
    ``{"value": ..., "value_type": ...}`` when the caller picks another sweep form
    for a parameter that declares a generated range.
    """
    if isinstance(override, dict) and "value" in override:
        value_type = override.get("value_type")
        return override["value"], str(value_type) if value_type is not None else None
    return override, None


def run_override_value(override: Any) -> Any:
    """Return the value a run override carries."""
    return run_override_parts(override)[0]


def validate_overrides(
    task: TaskInfo,
    input_overrides: dict[str, Any],
    run_overrides: dict[str, Any],
) -> None:
    """Reject overrides that the selected task cannot apply."""
    unknown_inputs = set(input_overrides) - set(task.input_parameters)
    unknown_run_parameters = set(run_overrides) - set(task.run_parameters)
    forbidden_inputs = {
        name
        for name in input_overrides
        if task.input_parameters.get(name, {}).get("user_override") == "forbidden"
    }
    invalid_types = []
    for name, value in input_overrides.items():
        metadata = task.input_parameters.get(name)
        if metadata is not None and not matches_parameter_type(value, metadata.get("value_type")):
            invalid_types.append(f"input.{name} must be {metadata.get('value_type')}")
    for name, override in run_overrides.items():
        metadata = task.run_parameters.get(name)
        if metadata is None:
            continue
        declared_type = metadata.get("value_type")
        value, requested_type = run_override_parts(override)
        if not compatible_value_type(declared_type, requested_type):
            invalid_types.append(
                f"run.{name} declares {declared_type} and cannot take {requested_type}"
            )
            continue
        effective_type = requested_type if requested_type is not None else declared_type
        if not matches_parameter_type(value, effective_type):
            invalid_types.append(f"run.{name} must be {effective_type}")

    errors = []
    if unknown_inputs:
        errors.append(f"unknown input parameters: {', '.join(sorted(unknown_inputs))}")
    if unknown_run_parameters:
        errors.append(f"unknown run parameters: {', '.join(sorted(unknown_run_parameters))}")
    if forbidden_inputs:
        errors.append(
            f"input parameters do not allow overrides: {', '.join(sorted(forbidden_inputs))}"
        )
    if invalid_types:
        errors.append("invalid parameter types: " + ", ".join(sorted(invalid_types)))
    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid parameter overrides: " + "; ".join(errors),
        )


def resolve_catalog_task(
    task_file_service: TaskFileService, task_name: str, backend_name: str | None
) -> tuple[TaskInfo, str]:
    """Return the enabled task definition and the backend it runs on."""
    backend = backend_name or get_default_backend()
    if backend not in get_available_backends():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown backend: {backend}",
        )
    if not is_task_available(task_name, backend):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task '{task_name}' is not enabled for backend '{backend}'",
        )
    task = next(
        (
            task
            for task in task_file_service.list_task_info(backend, enabled_only=True).tasks
            if task.name == task_name
        ),
        None,
    )
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task metadata for '{task_name}' is not available in backend '{backend}'",
        )
    return task, backend


async def run_catalog_task(
    *,
    flow_service: FlowService,
    task: TaskInfo,
    backend_name: str,
    chip_id: str,
    qid: str,
    username: str,
    project_id: str,
    input_overrides: dict[str, Any],
    run_overrides: dict[str, Any],
    persist_output_parameters: bool,
    update_params: bool,
    reconfigure: bool,
    execution_name: str,
    source_task_id: str | None = None,
    tags: list[str] | None = None,
) -> ExecuteFlowResponse:
    """Start one catalog run of ``task`` after checking the overrides."""
    validate_overrides(task, input_overrides, run_overrides)

    # The session takes the same readout_duration the task runs with.
    readout_duration = (
        run_override_value(run_overrides.get("readout_duration", DEFAULT_READOUT_DURATION))
        if "readout_duration" in task.run_parameters
        else None
    )
    default_run_parameters = (
        {"readout_duration": {"value": readout_duration, "value_type": "float"}}
        if readout_duration is not None
        else None
    )

    return await flow_service.execute_single_task_from_snapshot(
        task_name=task.name,
        qid=qid,
        chip_id=chip_id,
        source_execution_id=None,
        source_task_id=source_task_id,
        tags=tags,
        username=username,
        project_id=project_id,
        backend_name=backend_name,
        default_run_parameters=default_run_parameters,
        parameter_overrides={"input": input_overrides},
        task_run_parameters={
            task.name: {
                name: _run_parameter_entry(override) for name, override in run_overrides.items()
            }
        },
        persist_output_parameters=persist_output_parameters,
        update_params=update_params,
        reconfigure=reconfigure,
        execution_name=execution_name,
    )


def _run_parameter_entry(override: Any) -> dict[str, Any]:
    """Return the ``{"value": ..., "value_type"?: ...}`` entry one run override sets."""
    value, value_type = run_override_parts(override)
    entry: dict[str, Any] = {"value": value}
    if value_type is not None:
        entry["value_type"] = value_type
    return entry
