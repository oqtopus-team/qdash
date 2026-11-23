"""CalibService - the workflow author's entry point for calibration runs.

A workflow describes *what* to calibrate: a validated execution context, run
metadata, shared run defaults, and ``run(targets, steps)`` with ``TaskCall``
entries. QDash owns *how* it runs: execution IDs, hardware reservation, worker
sessions, snapshot restoration, GitHub synchronization and closing every
Execution on success, failure or cancellation. None of that is configured
through ``CalibService``.

Example:
    ```python
    from prefect import flow
    from qdash.workflow import CalibService, TaskCall
    from qdash.workflow.service.calib_service import (
        on_flow_cancellation,
        on_flow_crashed,
        on_flow_failure,
    )
    from qdash.workflow.service.steps import CustomOneQubit
    from qdash.workflow.service.targets import MuxTargets


    @flow(
        on_cancellation=[on_flow_cancellation],
        on_failure=[on_flow_failure],
        on_crashed=[on_flow_crashed],
    )
    def calibration_flow(username, chip_id, flow_name=None, project_id=None):
        cal = CalibService(username, chip_id, project_id=project_id, flow_name=flow_name)
        return cal.run(
            MuxTargets([0, 1, 2, 3]),
            steps=[CustomOneQubit(tasks=[TaskCall(name="CheckRabi")])],
        )
    ```
"""

from __future__ import annotations

import copy
import logging
from typing import TYPE_CHECKING, Any

from qdash.workflow.engine.task_parameters import normalize_default_run_parameters
from qdash.workflow.service._internal.lifecycle import (
    on_flow_cancellation,
    on_flow_cancellation_keep_lock,
    on_flow_crashed,
    on_flow_crashed_keep_lock,
    on_flow_failure,
    on_flow_failure_keep_lock,
)
from qdash.workflow.service.context import CalibContext, resolve_calib_context
from qdash.workflow.service.execution_id import generate_execution_id

if TYPE_CHECKING:
    from collections.abc import Sequence

    from qdash.workflow.service.steps import Step
    from qdash.workflow.service.targets import Target

logger = logging.getLogger(__name__)

__all__ = [
    "CalibService",
    "generate_execution_id",
    "on_flow_cancellation",
    "on_flow_cancellation_keep_lock",
    "on_flow_crashed",
    "on_flow_crashed_keep_lock",
    "on_flow_failure",
    "on_flow_failure_keep_lock",
]

_TASKCALL_HINT = (
    "set run, input and update_calibration_parameters on each TaskCall instead "
    "(share values through local variables, and default_run_parameters for run "
    "values every task shares)"
)
_MANAGED_HINT = "QDash manages it for every run; remove the argument"

_GITHUB_HINT = (
    "GitHub pull and push follow github.enabled and github.branch in "
    "config/app/workflow.yaml (qubex backend only); "
    "TaskCall(..., update_calibration_parameters=False) controls calibration writes, "
    "not synchronization"
)

# Removed constructor options and how to migrate each one.
LEGACY_OPTION_MIGRATIONS: dict[str, str] = {
    "qids": "pass targets to run(): cal.run(QubitTargets(qids), steps=[...])",
    "muxes": "pass targets to run(): cal.run(MuxTargets(mux_ids), steps=[...])",
    "name": "use flow_name=... for the display name",
    "task_parameters": _TASKCALL_HINT,
    "task_run_parameters": _TASKCALL_HINT,
    "_task_defaults": _TASKCALL_HINT,
    "execution_id": f"execution IDs are allocated per step Execution; {_MANAGED_HINT}",
    "use_lock": f"every run reserves the hardware it plans to use; {_MANAGED_HINT}",
    "skip_execution": f"every calibration step owns one Execution; {_MANAGED_HINT}",
    "resource_scope": f"the reservation is planned from targets and steps; {_MANAGED_HINT}",
    "enable_github": _GITHUB_HINT,
    "enable_github_pull": _GITHUB_HINT,
    "github_push_config": _GITHUB_HINT,
    "backend_name": "the backend is part of the execution context: "
    "CalibService.from_context(resolve_calib_context(username, chip_id, "
    "project_id=project_id, backend=backend_name))",
    "configuration_mode": "put a ConfigureAll step with "
    'TaskCall(name="ConfigureAll", run={"configuration_mode": ...}) first; the layout applies '
    "from that step on, so earlier steps keep QUBEX_CONFIGURATION_MODE",
    "source_execution_id": "snapshot re-execution is the single-task executor's job "
    "(Re-execute in the task detail page); a flow that declares a source_execution_id "
    "parameter still restores from it",
    "source_task_id": "snapshot re-execution is the single-task executor's job",
    "snapshot_exempt_tasks": "snapshot re-execution is the single-task executor's job",
    "force_update_params": "force updates are a single-task re-execution option "
    "(update_params); TaskCall(..., update_calibration_parameters=False) controls saving",
    "persist_output_parameters": "use TaskCall(..., update_calibration_parameters=False) "
    "for measurement-only calls",
    "user_repo": "resolve the context with resolve_calib_context(...) and pass it to "
    "CalibService.from_context(...)",
    "lock_repo": _MANAGED_HINT,
    "counter_repo": _MANAGED_HINT,
    "enable_github_push": _MANAGED_HINT,
}

# Order of the removed positional parameters after username and chip_id.
_POSITIONAL_LEGACY = (
    "qids",
    "execution_id",
    "backend_name",
    "name",
    "flow_name",
    "tags",
    "use_lock",
    "note",
)


def _reject_legacy_arguments(args: tuple[Any, ...], options: dict[str, Any]) -> None:
    """Raise one actionable error for every removed constructor argument."""
    if not args and not options:
        return
    problems: list[str] = []
    for index, _ in enumerate(args):
        name = _POSITIONAL_LEGACY[index] if index < len(_POSITIONAL_LEGACY) else None
        hint = LEGACY_OPTION_MIGRATIONS.get(name or "", "pass it as a keyword argument")
        label = f"positional argument {index + 3}" + (f" ({name})" if name else "")
        problems.append(f"{label}: {hint}")
    for name in options:
        hint = LEGACY_OPTION_MIGRATIONS.get(
            name, "CalibService accepts flow_name, tags, note and default_run_parameters"
        )
        problems.append(f"{name}: {hint}")
    raise TypeError(
        "CalibService no longer accepts these arguments:\n  - "
        + "\n  - ".join(problems)
        + "\nSee docs/developer-guide/workflow/services.md for the migration."
    )


class CalibService:
    """Run calibration steps for one validated context.

    ``CalibService(username, chip_id, project_id=..., flow_name=...)`` is the
    entry for Prefect flows: QDash injects these parameters when it starts the
    flow, and the constructor checks them with :func:`resolve_calib_context` on
    the configured default backend. For direct Python use, or to choose another
    backend, resolve the context yourself and call :meth:`from_context`.

    The service has no hardware state of its own. Each :meth:`run` reserves the
    hardware its targets and steps need, runs every calibration step in its own
    Execution, and closes each Execution on success, failure or cancellation, so
    there is nothing to finish afterwards and the same service can run again.

    Example:
        ```python
        cal = CalibService(username, chip_id, project_id=project_id, flow_name=flow_name)
        results = cal.run(
            QubitTargets(["0", "1"]),
            steps=[
                CustomOneQubit(
                    step_name="rabi_and_hpi",
                    tasks=[TaskCall(name="CheckRabi"), TaskCall(name="CreateHPIPulse")],
                )
            ],
        )
        ```
    """

    def __init__(
        self,
        username: str,
        chip_id: str,
        *legacy_args: Any,
        project_id: str | None = None,
        flow_name: str | None = None,
        tags: list[str] | None = None,
        note: dict[str, Any] | None = None,
        default_run_parameters: dict[str, Any] | None = None,
        **legacy_options: Any,
    ) -> None:
        """Resolve the context of a Prefect flow run and record run metadata.

        Args:
            username: User the run is attributed to (injected by QDash).
            chip_id: Chip to calibrate.
            project_id: Project of the run (injected by QDash). Defaults to the
                user's default project.
            flow_name: Display name of the run; each step's Execution is named
                ``<flow_name>_<step name>`` (injected by QDash).
            tags: Tags recorded on every Execution of the run.
            note: Extra JSON-serializable data recorded in every Execution's note.
            default_run_parameters: Run values every task shares, in the same
                plain, sweep or wrapped form as ``TaskCall.run``. When omitted,
                the saved flow's defaults apply.

        Raises:
            TypeError: A removed argument was passed; the message says how to
                migrate each one.
            CalibContextError: The user, project or permission is not valid.
        """
        _reject_legacy_arguments(legacy_args, legacy_options)
        context = resolve_calib_context(username, chip_id, project_id=project_id)
        self._setup(context, flow_name, tags, note, default_run_parameters)

    @classmethod
    def from_context(
        cls,
        context: CalibContext,
        *,
        flow_name: str | None = None,
        tags: list[str] | None = None,
        note: dict[str, Any] | None = None,
        default_run_parameters: dict[str, Any] | None = None,
    ) -> CalibService:
        """Create a service for a context from :func:`resolve_calib_context`.

        Example:
            ```python
            context = resolve_calib_context("alice", "64Qv3")
            CalibService.from_context(context, flow_name="nightly").run(targets, steps)
            ```
        """
        if not isinstance(context, CalibContext):
            raise TypeError("context must come from resolve_calib_context(...)")
        service = cls.__new__(cls)
        service._setup(context, flow_name, tags, note, default_run_parameters)
        return service

    def _setup(
        self,
        context: CalibContext,
        flow_name: str | None,
        tags: list[str] | None,
        note: dict[str, Any] | None,
        default_run_parameters: dict[str, Any] | None,
    ) -> None:
        self._context = context
        self._flow_name = flow_name
        self._tags = list(tags) if tags is not None else None
        self._note = copy.deepcopy(note) if note is not None else None
        self._default_run_parameters = (
            normalize_default_run_parameters(default_run_parameters)
            if default_run_parameters
            else None
        )

    @property
    def context(self) -> CalibContext:
        """The validated user, chip and project of every run."""
        return self._context

    @property
    def username(self) -> str:
        return self._context.username

    @property
    def chip_id(self) -> str:
        return self._context.chip_id

    @property
    def project_id(self) -> str:
        return self._context.project_id

    @property
    def backend_name(self) -> str:
        return self._context.backend_name

    @property
    def flow_name(self) -> str | None:
        return self._flow_name

    @property
    def tags(self) -> list[str] | None:
        return list(self._tags) if self._tags is not None else None

    @property
    def note(self) -> dict[str, Any] | None:
        return copy.deepcopy(self._note) if self._note is not None else None

    @property
    def default_run_parameters(self) -> dict[str, Any]:
        """Explicit shared run defaults; the saved flow's apply when this is empty."""
        return dict(self._default_run_parameters or {})

    def run(self, targets: Target, steps: Sequence[Step]) -> dict[str, Any]:
        """Run the steps on the targets, one Execution per calibration step.

        Targets selected in the QDash UI for this run replace ``targets``.

        Args:
            targets: ``MuxTargets``, ``QubitTargets`` or another target.
            steps: Calibration and transform steps, run in order.

        Returns:
            Results dictionary with typed results of each step.
        """
        from qdash.workflow.service._internal.runs import run_calibration, workflow_settings

        settings = workflow_settings(
            self._context,
            flow_name=self._flow_name,
            tags=self._tags,
            note=self._note,
            default_run_parameters=self._default_run_parameters,
        )
        return run_calibration(settings, targets, steps)
