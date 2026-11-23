"""Entry points that build typed session settings and run them.

Every route into a calibration goes through here: ``CalibService.run``, the
declarative pipeline flow and the single-task executor. Each builds one
:class:`SessionSettings` and hands it to a :class:`CalibSession` that owns the
whole lifecycle, so no caller finishes, fails or cancels an Execution itself.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from qdash.workflow.engine.task_parameters import (
    UPDATE_CALIBRATION_PARAMETERS,
    normalize_default_run_parameters,
)
from qdash.workflow.service._internal.session import CalibSession, SessionRepositories
from qdash.workflow.service._internal.settings import (
    GitHubPolicy,
    SessionSettings,
    SnapshotSource,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from qdash.workflow.service.context import CalibContext
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
) -> SessionSettings:
    """Settings of a workflow run.

    ``default_run_parameters`` falls back to the saved flow's defaults when
    empty. A flow that declares a ``source_execution_id`` parameter restores
    snapshot parameters from it, in its own sessions and in its workers alike.
    ``task_defaults`` is only set by the declarative pipeline flow, from its
    spec's deprecated ``task_parameters``. GitHub pull and push follow the
    deployment (:meth:`GitHubPolicy.from_deployment`).
    """
    defaults = default_run_parameters or load_flow_default_run_parameters(
        context.project_id, flow_name
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
) -> dict[str, Any]:
    """Run a pipeline under one owner session, applying the run's target override.

    Selected pairs replace the initial ``CouplingTargets``; the automatic
    two-qubit steps group them with the session's pinned MUX mapping, the one
    its reservation and workers use.
    """
    from qdash.workflow.service.flow_targets import override_pipeline, read_target_override

    targets, pipeline_steps = override_pipeline(targets, steps, read_target_override())
    session = CalibSession(settings, repositories=repositories)
    return session.run_pipeline(targets, pipeline_steps)


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
    session = CalibSession(settings, repositories=repositories)
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
