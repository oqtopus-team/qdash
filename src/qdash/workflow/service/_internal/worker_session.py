"""Configuration shared with isolated calibration worker sessions."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from qdash.workflow.service.calib_service import CalibService


class IsolatedSessionConfig(TypedDict):
    """Serializable settings needed to reproduce the parent session in a worker."""

    username: str
    chip_id: str
    backend_name: str
    project_id: str | None
    muxes: list[int] | None
    execution_id: str | None
    default_run_parameters: dict[str, Any]
    task_run_parameters: dict[str, dict[str, Any]]
    source_execution_id: str | None
    source_task_id: str | None
    snapshot_exempt_tasks: list[str]
    parameter_overrides: dict[str, dict[str, Any]] | None
    force_update_params: bool
    persist_output_parameters: bool
    tags: list[str] | None
    flow_name: str | None
    note: dict[str, Any] | None


def build_isolated_session_config(
    service: CalibService,
    *,
    execution_id: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Take an immutable-by-convention snapshot of parent settings for workers."""
    config: IsolatedSessionConfig = {
        "username": service.username,
        "chip_id": service.chip_id,
        "backend_name": service.backend_name,
        "project_id": project_id if project_id is not None else service.project_id,
        # Isolated workers are scoped by their explicit qids. They must not
        # inherit the parent pipeline's broader MUX selection.
        "muxes": None,
        "execution_id": execution_id if execution_id is not None else service.execution_id,
        "default_run_parameters": deepcopy(service.default_run_parameters),
        "task_run_parameters": deepcopy(service.task_run_parameters),
        "source_execution_id": getattr(service, "source_execution_id", None),
        "source_task_id": getattr(service, "source_task_id", None),
        "snapshot_exempt_tasks": sorted(getattr(service, "snapshot_exempt_tasks", ())),
        "parameter_overrides": deepcopy(service.parameter_overrides),
        "force_update_params": service.force_update_params,
        "persist_output_parameters": service.persist_output_parameters,
        "tags": deepcopy(service.tags),
        "flow_name": service.flow_name,
        "note": deepcopy(service.note),
    }
    # Prefect-facing helpers historically accept a regular dictionary. Keep
    # that interface while checking completeness above with IsolatedSessionConfig.
    return dict(config)
