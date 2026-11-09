"""System flow for single-task re-execution.

This flow is registered as a Prefect deployment on worker startup
and allows re-executing a single calibration task from the task detail page.

Unlike user flows, this flow does not require a FlowDocument to exist.
It is always available as a system deployment.

This top-level flow owns its hardware reservation (``use_lock=True``). Its
terminal hooks must release that reservation even when cancellation interrupts
CalibService construction, before the in-process cleanup handler is installed.
The shared finalizer preserves reservations belonging to other executions.
"""

from __future__ import annotations

import contextlib
import warnings
from typing import Any

from prefect import flow, get_run_logger

from qdash.common.config.backend import get_default_backend
from qdash.common.config.loader import ConfigLoader
from qdash.datamodel.task_settings import (
    LEGACY_UPDATE_CALIBRATION_PARAMETERS_DEPRECATION,
    resolve_update_calibration_parameters_alias,
)
from qdash.workflow.engine.task_parameters import (
    UPDATE_CALIBRATION_PARAMETERS,
    merge_task_parameters,
    normalize_task_parameters,
    task_parameters_from_run_parameters,
)
from qdash.workflow.service.calib_service import (
    CalibService,
    on_flow_cancellation,
    on_flow_crashed,
    on_flow_failure,
)
from qdash.workflow.service.github import GitHubPushConfig


def _resolve_single_task_writeback(
    task_name: str,
    *,
    update_calibration_parameters: bool | None,
    persist_output_parameters: bool | None,
    parameter_overrides: dict[str, Any] | None,
    task_run_parameters: dict[str, dict[str, Any]] | None,
    reconfigure: bool,
) -> tuple[bool, dict[str, Any] | None, dict[str, dict[str, Any]] | None]:
    """Resolve the one write-back control of a single-task run.

    The top-level ``update_calibration_parameters`` controls the requested task
    and the optional Configure call. Two migration inputs are still read:

    - the deprecated top-level ``persist_output_parameters`` alias;
    - an ``update_calibration_parameters`` nested in ``parameter_overrides`` or
      in the ``task_run_parameters`` entry of a call this run executes.

    A nested value that matches the top-level control is redundant; one that
    differs is rejected. Without a top-level control, nested values that agree
    become the control. Every legacy form warns. Nested values are stripped from
    the returned settings so they cannot override the control. Raises
    ``ValueError`` before any hardware session exists.

    Returns:
        The effective control and the stripped ``parameter_overrides`` and
        ``task_run_parameters``.
    """
    logger = get_run_logger()
    top_level = resolve_update_calibration_parameters_alias(
        update_calibration_parameters, persist_output_parameters
    )
    if persist_output_parameters is not None:
        warnings.warn(
            LEGACY_UPDATE_CALIBRATION_PARAMETERS_DEPRECATION, DeprecationWarning, stacklevel=2
        )
        logger.warning(LEGACY_UPDATE_CALIBRATION_PARAMETERS_DEPRECATION)

    executed = [task_name, *(["Configure"] if reconfigure else [])]
    nested: dict[str, Any] = {}
    overrides = dict(parameter_overrides) if parameter_overrides is not None else None
    if overrides is not None and UPDATE_CALIBRATION_PARAMETERS in overrides:
        nested["parameter_overrides"] = overrides.pop(UPDATE_CALIBRATION_PARAMETERS)
    run_parameters = (
        {
            name: dict(entries) if isinstance(entries, dict) else entries
            for name, entries in task_run_parameters.items()
        }
        if isinstance(task_run_parameters, dict)
        else task_run_parameters
    )
    if isinstance(run_parameters, dict):
        for name in executed:
            entries = run_parameters.get(name)
            if isinstance(entries, dict) and UPDATE_CALIBRATION_PARAMETERS in entries:
                nested[f"task_run_parameters[{name!r}]"] = entries.pop(
                    UPDATE_CALIBRATION_PARAMETERS
                )
    if not nested:
        return (True if top_level is None else top_level), overrides, run_parameters

    for source, value in nested.items():
        if not isinstance(value, bool):
            raise ValueError(f"{source}.update_calibration_parameters must be a boolean")
    sources = ", ".join(f"{source}={value}" for source, value in nested.items())
    if top_level is not None:
        conflicting = {s: v for s, v in nested.items() if v is not top_level}
        if conflicting:
            raise ValueError(
                f"update_calibration_parameters={top_level} conflicts with the nested "
                f"update_calibration_parameters in {sources}; remove the nested value and "
                "set only the top-level update_calibration_parameters"
            )
        effective = top_level
    else:
        if len(set(nested.values())) > 1:
            raise ValueError(
                f"Nested update_calibration_parameters values disagree ({sources}); one "
                "control applies to every call of a single-task run, so set only the "
                "top-level update_calibration_parameters"
            )
        effective = next(iter(nested.values()))
    message = (
        f"A nested update_calibration_parameters ({sources}) is deprecated for single-task "
        "runs and will be removed; set the top-level update_calibration_parameters instead"
    )
    warnings.warn(message, DeprecationWarning, stacklevel=2)
    logger.warning(message)
    return effective, overrides, run_parameters


def _single_task_defaults(
    task_name: str,
    *,
    parameter_overrides: dict[str, Any] | None,
    task_run_parameters: dict[str, dict[str, Any]] | None,
    update_calibration_parameters: bool,
) -> dict[str, dict[str, Any]]:
    """Return the per-task defaults of one single-task run.

    The run's resolved ``update_calibration_parameters`` applies to the requested
    task; nested values are already stripped by ``_resolve_single_task_writeback``.
    """
    writeback = normalize_task_parameters(
        {task_name: {UPDATE_CALIBRATION_PARAMETERS: update_calibration_parameters}}
    )
    requested = [
        task_parameters_from_run_parameters(task_run_parameters),
        # Request overrides ({"input": ..., "run": ...}) apply to the requested task.
        normalize_task_parameters({task_name: parameter_overrides or {}}),
    ]
    return merge_task_parameters(*requested, writeback)


@flow(
    name="single-task-executor",
    on_cancellation=[on_flow_cancellation],
    on_failure=[on_flow_failure],
    on_crashed=[on_flow_crashed],
)
def single_task_executor(
    username: str,
    chip_id: str,
    qid: str,
    task_name: str,
    source_execution_id: str | None = None,
    project_id: str | None = None,
    flow_name: str | None = None,
    tags: list[str] | None = None,
    source_task_id: str | None = None,
    parameter_overrides: dict[str, dict[str, Any]] | None = None,
    update_params: bool = True,
    update_calibration_parameters: bool | None = None,
    reconfigure: bool = False,
    backend_name: str | None = None,
    default_run_parameters: dict[str, Any] | None = None,
    task_run_parameters: dict[str, dict[str, Any]] | None = None,
    persist_output_parameters: bool | None = None,
) -> Any:
    """Execute a single calibration task.

    This system flow runs one task for one qubit, using snapshot parameters
    from a previous execution. It is designed to be triggered from the
    task detail page's "Re-execute" button.

    Args:
        username: User name
        chip_id: Chip ID
        qid: Qubit ID to calibrate
        task_name: Name of the task to execute (e.g., 'CheckRabi')
        source_execution_id: Execution ID to load snapshot parameters from
        project_id: Project ID (auto-injected)
        flow_name: Flow name for display (auto-injected)
        tags: Tags for categorization
        source_task_id: Task result ID that triggered this re-execution
        parameter_overrides: Overrides for the requested task, shaped as
            ``{"input": {...}, "run": {...}}``. They become that task's entry in
            ``task_parameters`` and are applied on top of the source snapshot.
        update_params: Force backend parameter updates regardless of quality checks.
        update_calibration_parameters: Whether validated outputs of the requested
            task and the optional Configure call replace the current calibration
            values. Task history, figures and raw data are saved either way.
            False also disables GitHub push. Defaults to True when omitted.
        default_run_parameters: Shared fallback run parameters for compatibility.
        task_run_parameters: Explicit run parameters keyed by task name.
        persist_output_parameters: Deprecated alias of
            ``update_calibration_parameters`` kept for runs queued by older API
            servers. It warns, conflicts with a different canonical value raise
            ``ValueError``, and it will be removed.

    Raises:
        ValueError: The write-back controls conflict. Raised before the
            calibration session or hardware is touched.

    Returns:
        Task execution result dictionary
    """
    writeback, parameter_overrides, task_run_parameters = _resolve_single_task_writeback(
        task_name,
        update_calibration_parameters=update_calibration_parameters,
        persist_output_parameters=persist_output_parameters,
        parameter_overrides=parameter_overrides,
        task_run_parameters=task_run_parameters,
        reconfigure=reconfigure,
    )
    logger = get_run_logger()
    logger.info(
        f"Single-task executor: task={task_name}, qid={qid}, "
        f"source={source_execution_id}, chip={chip_id}"
    )

    github_settings = ConfigLoader.load_workflow().get("github", {})
    github_enabled = (
        github_settings.get("enabled", True) is True
        and (backend_name or get_default_backend()) == "qubex"
    )
    # Write-back controls publication; update_params only overrides quality checks.
    push_config = GitHubPushConfig(
        enabled=writeback and github_enabled,
        branch=github_settings.get("branch", "main"),
    )

    snapshot_exempt_tasks = {"Configure"} if reconfigure else set()
    if source_execution_id is None and (
        default_run_parameters is not None or task_run_parameters is not None
    ):
        # Catalog runs can keep a source result for provenance without restoring its parameters.
        snapshot_exempt_tasks.add(task_name)

    task_defaults = _single_task_defaults(
        task_name,
        parameter_overrides=parameter_overrides,
        task_run_parameters=task_run_parameters,
        update_calibration_parameters=writeback,
    )
    cal = CalibService(
        username,
        chip_id,
        qids=[qid],
        source_execution_id=source_execution_id,
        flow_name=flow_name or f"re-execute:{task_name}",
        tags=tags,
        project_id=project_id,
        backend_name=backend_name,
        default_run_parameters=default_run_parameters,
        _task_defaults=task_defaults,
        enable_github_pull=github_enabled,
        enable_github=push_config.enabled,
        github_push_config=push_config,
        use_lock=True,
        source_task_id=source_task_id,
        snapshot_exempt_tasks=snapshot_exempt_tasks or None,
        force_update_params=update_params,
    )

    try:
        if reconfigure:
            logger.info(f"Reconfiguring hardware for qid={qid} before executing {task_name}")
            # Pass the control on the call so a backend without Configure still
            # fails here, rather than while validating service defaults.
            cal.execute_task(
                "Configure",
                qid,
                parameters={UPDATE_CALIBRATION_PARAMETERS: writeback},
            )

        result = cal.execute_task(task_name, qid)
        cal.finish_calibration()

        logger.info(f"Single-task executor completed: {task_name} / {qid}")
        return result
    except BaseException as e:
        from qdash.workflow.service.calib_service import (
            _is_cancellation,
            _is_external_termination,
        )

        if _is_cancellation(e):
            logger.info("Single-task executor was cancelled")
            with contextlib.suppress(Exception):
                cal.cancel_calibration()
        elif _is_external_termination(e):
            logger.info("Single-task executor interrupted by a termination signal")
            with contextlib.suppress(Exception):
                cal.abandon_calibration()
        else:
            logger.error(f"Single-task executor failed: {e}")
            with contextlib.suppress(Exception):
                cal.fail_calibration(str(e))
        raise
