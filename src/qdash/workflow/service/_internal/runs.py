"""Entry points that build typed session settings and run them.

Every route into a calibration goes through here: ``CalibrationSession.run`` (and
the legacy ``CalibService.run``), the declarative pipeline flow and the single-task
executor. Each builds one :class:`SessionSettings` and hands it to an
:class:`ExecutionRuntime` that owns the
whole lifecycle, so no caller finishes, fails or cancels an Execution itself.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from qdash.workflow.engine.task_parameters import (
    UPDATE_CALIBRATION_PARAMETERS,
    normalize_default_run_parameters,
)
from qdash.workflow.service._internal.session import ExecutionRuntime, SessionRepositories
from qdash.workflow.service._internal.settings import (
    GitHubPolicy,
    SessionSettings,
    SnapshotSource,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import EllipsisType

    from qdash.workflow.service.context import CalibContext
    from qdash.workflow.service.plan_approval import ApprovedPlanCheck
    from qdash.workflow.service.steps import Step
    from qdash.workflow.service.targets import Target

logger = logging.getLogger(__name__)


def read_source_execution_id_from_context() -> str | None:
    """Return the ``source_execution_id`` parameter of the current Prefect flow run."""
    try:
        from prefect.context import get_run_context

        ctx = get_run_context()
        flow_run = getattr(ctx, "flow_run", None)
        if flow_run and flow_run.parameters:
            value = flow_run.parameters.get("source_execution_id")
            return str(value) if value is not None else None
    except Exception:
        logger.debug("No Prefect run context available for source_execution_id")
    return None


def _flow_run_context() -> tuple[Any, Any] | None:
    """The current Prefect flow run and its flow, or None outside a flow run."""
    try:
        from prefect.context import FlowRunContext

        context = FlowRunContext.get()
    except Exception:
        logger.debug("No Prefect flow run context available")
        return None
    if context is None or context.flow_run is None:
        return None
    return context.flow_run, getattr(context, "flow", None)


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def read_saved_flow_name_from_context() -> str | None:
    """The saved QDash flow the current flow run was launched from, or None.

    QDash injects the saved flow's name as the ``flow_name`` parameter of every launch
    (execute, schedule and preview). A flow run started in Prefect directly, or a call
    outside a flow run, has no saved flow.
    """
    found = _flow_run_context()
    if found is None:
        return None
    parameters = getattr(found[0], "parameters", None) or {}
    return _text(parameters.get("flow_name")) if isinstance(parameters, dict) else None


def resolve_launch_names(name: str | None) -> tuple[str | None, str | None]:
    """The display name of a ``CalibrationSession.run`` and the saved flow of its defaults.

    The display name is, in order: ``name`` when the flow passes one (legacy flows pass
    the injected ``flow_name``), the saved QDash flow the launch came from, the Prefect
    flow's name for a flow run started without QDash, and None outside a flow run (the
    Execution then falls back to its step name). The saved defaults are read from the
    launch's saved flow, whatever display name is passed; without one (outside QDash)
    from ``name``, as before. The Prefect flow name never selects saved defaults.
    """
    saved = read_saved_flow_name_from_context()
    display = name
    if display is None:
        display = saved
    if display is None:
        found = _flow_run_context()
        display = _text(getattr(found[1], "name", None)) if found is not None else None
    return display, saved if saved is not None else name


def load_flow_default_run_parameters(project_id: str, flow_name: str | None) -> dict[str, Any]:
    """Return the saved flow's ``default_run_parameters``, or nothing."""
    if not flow_name:
        return {}
    try:
        from qdash.repository.flow import MongoFlowRepository

        flow = MongoFlowRepository().find_by_project_and_name(project_id, flow_name)
        if flow and flow.default_run_parameters:
            logger.debug(
                "Loaded default_run_parameters from flow '%s': %s",
                flow_name,
                flow.default_run_parameters,
            )
            return normalize_default_run_parameters(flow.default_run_parameters)
    except Exception:
        logger.warning(
            "Failed to load default_run_parameters for flow '%s'", flow_name, exc_info=True
        )
    return {}


def workflow_settings(
    context: CalibContext,
    *,
    flow_name: str | None,
    tags: list[str] | None,
    note: dict[str, Any] | None,
    default_run_parameters: dict[str, Any] | None,
    task_defaults: dict[str, dict[str, Any]] | None = None,
    saved_flow_name: str | None | EllipsisType = ...,
) -> SessionSettings:
    """Settings of a workflow run.

    ``default_run_parameters`` falls back to the saved flow's defaults when
    empty. A flow that declares a ``source_execution_id`` parameter restores
    snapshot parameters from it, in its own sessions and in its workers alike.
    ``task_defaults`` is only set by the declarative pipeline flow, from its
    spec's deprecated ``task_parameters``. GitHub pull and push follow the
    deployment (:meth:`GitHubPolicy.from_deployment`). ``saved_flow_name`` names the saved
    flow whose defaults apply when it differs from the display ``flow_name``
    (see :func:`resolve_launch_names`); by default it is ``flow_name``.
    """
    defaults_from = flow_name if saved_flow_name is ... else saved_flow_name
    defaults = default_run_parameters or load_flow_default_run_parameters(
        context.project_id, defaults_from
    )
    source_execution_id = read_source_execution_id_from_context()
    return SessionSettings(
        username=context.username,
        chip_id=context.chip_id,
        project_id=context.project_id,
        backend_name=context.backend_name,
        flow_name=flow_name,
        tags=tags,
        note=note,
        default_run_parameters=defaults,
        task_defaults=task_defaults or {},
        snapshot=SnapshotSource(execution_id=source_execution_id),
        github=GitHubPolicy.from_deployment(context.backend_name),
    )


def run_calibration(
    settings: SessionSettings,
    targets: Target,
    steps: Sequence[Step],
    *,
    repositories: SessionRepositories | None = None,
    approved_plan: ApprovedPlanCheck | None = None,
) -> dict[str, Any]:
    """Run a pipeline under one owner session, applying the run's target override.

    Selected pairs replace the initial ``CouplingTargets``; the automatic
    two-qubit steps group them with the session's pinned MUX mapping, the one
    its reservation and workers use. ``approved_plan`` holds a run started from a stored
    plan to that plan (see :mod:`qdash.workflow.service.plan_approval`); an override that
    changes its targets then stops the run before anything is reserved.
    """
    if approved_plan is None:
        results, _ = run_calibration_with_runtime(
            settings, targets, steps, repositories=repositories
        )
    else:
        results, _ = run_calibration_with_runtime(
            settings, targets, steps, repositories=repositories, approved_plan=approved_plan
        )
    return results


def run_calibration_with_runtime(
    settings: SessionSettings,
    targets: Target,
    steps: Sequence[Step],
    *,
    repositories: SessionRepositories | None = None,
    approved_plan: ApprovedPlanCheck | None = None,
) -> tuple[dict[str, Any], ExecutionRuntime]:
    """:func:`run_calibration`, also returning the runtime that ran it.

    The runtime's ``run_identity`` and ``run_execution_ids`` name the persisted run and
    the step Executions; ``CalibrationSession.run`` reports them.
    """
    from qdash.workflow.service.flow_targets import override_pipeline, read_target_override

    targets, pipeline_steps = override_pipeline(targets, steps, read_target_override())
    runtime = ExecutionRuntime(settings, repositories=repositories)
    if approved_plan is None:
        return runtime.run_pipeline(targets, pipeline_steps), runtime
    return runtime.run_pipeline(targets, pipeline_steps, approved_plan=approved_plan), runtime


def run_single_task(
    settings: SessionSettings,
    *,
    qid: str,
    task_name: str,
    reconfigure: bool,
    update_calibration_parameters: bool,
    repositories: SessionRepositories | None = None,
) -> dict[str, Any]:
    """Run one task (after an optional Configure) in one owned Execution.

    The session reserves ``qid``, and on success, failure or cancellation closes
    the Execution and releases the reservation, exactly as a pipeline step does.
    """
    session = ExecutionRuntime(settings, repositories=repositories)
    with session.owned_execution([qid]):
        if reconfigure:
            # Pass the control on the call so a backend without Configure still
            # fails here, rather than while validating the per-task defaults.
            session.execute_task(
                "Configure",
                qid,
                parameters={UPDATE_CALIBRATION_PARAMETERS: update_calibration_parameters},
            )
        return session.execute_task(task_name, qid)
