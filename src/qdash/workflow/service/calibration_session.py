"""``CalibrationSession`` inside a workflow: run calibrations in the launch's session.

A calibration session is a named, persistent objective on one chip that groups the runs
started for it. It holds no hardware, opens no connection and is not a transaction. A saved
workflow does not create one: the launch already belongs to one, either the session the
caller named or the automatic session QDash created for it (named by
``@calibration_flow(session_name=...)``). :meth:`CalibrationSession.from_context` binds to
that membership, and every :meth:`~CalibrationSession.run` of the flow run is recorded in
the same run of the same session.

The SDK's ``qdash.sdk.CalibrationSession`` is the remote counterpart: it creates or opens a
session by ID and launches runs into it over HTTP. Both take the same targets and steps from
:mod:`qdash.calibration` and return the same :class:`~qdash.calibration.CalibrationResult`.
Here, ``run`` executes in the current flow run and a failed step raises its own exception.

Example:
    ```python
    from qdash.calibration import CustomOneQubit, MuxTargets, TaskCall
    from qdash.workflow import CalibrationSession, calibration_flow, resolve_calib_context


    @calibration_flow(session_name="Rabi check")
    def rabi_check(username, chip_id, mux_ids, flow_name=None, project_id=None):
        context = resolve_calib_context(username, chip_id, project_id=project_id)
        session = CalibrationSession.from_context(context)
        return session.run(
            targets=MuxTargets(mux_ids),
            steps=[CustomOneQubit(step_name="rabi", tasks=[TaskCall(name="CheckRabi")])],
            name=flow_name,
        )
    ```
"""

from __future__ import annotations

import copy
import logging
from typing import TYPE_CHECKING, Any

from qdash.calibration import CalibrationResult, CalibrationValidation
from qdash.workflow.engine.task_parameters import normalize_default_run_parameters
from qdash.workflow.service.context import CalibContext

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

logger = logging.getLogger(__name__)

__all__ = ["CalibrationSession"]


class CalibrationSession:
    """The calibration session of the running launch, for one validated context.

    Create it with :meth:`from_context`. It records nothing by itself and holds no
    hardware: each :meth:`run` reserves the hardware its targets and steps need, records every
    step it reaches in its own Execution (filters and schedules too, without hardware) and
    closes each one however the run ends.
    """

    def __init__(self, context: CalibContext, *, _token: object = None) -> None:
        if _token is not _FROM_CONTEXT:
            raise TypeError(
                "create a CalibrationSession with CalibrationSession.from_context(context)"
            )
        self._context = context
        self._calibration_session_id: str | None = None
        self._run_id: str | None = None

    @classmethod
    def from_context(cls, context: CalibContext) -> CalibrationSession:
        """Bind to the launch's calibration session for ``context``.

        ``context`` comes from :func:`~qdash.workflow.resolve_calib_context`, which checks
        the user's project permission. No session is created: a flow run launched by QDash
        already belongs to one, and a scheduled or directly started flow run is recorded in
        an automatic session of its own when its first run starts.
        """
        if not isinstance(context, CalibContext):
            raise TypeError("context must come from resolve_calib_context(...)")
        return cls(context, _token=_FROM_CONTEXT)

    @property
    def context(self) -> CalibContext:
        """The validated user, chip, project and backend of every run."""
        return self._context

    @property
    def chip_id(self) -> str:
        return self._context.chip_id

    @property
    def calibration_session_id(self) -> str | None:
        """The persisted session the runs were recorded in; None before the first run, or
        when running outside a flow run (a local script or a test)."""
        return self._calibration_session_id

    @property
    def run_id(self) -> str | None:
        """The persisted run of this flow run, which every :meth:`run` shares."""
        return self._run_id

    def __repr__(self) -> str:
        return (
            f"CalibrationSession(chip_id={self.chip_id!r}, "
            f"calibration_session_id={self._calibration_session_id!r})"
        )

    def validate(
        self,
        targets: Any,
        steps: Sequence[Any],
        *,
        default_run_parameters: Mapping[str, Any] | None = None,
        name: str | None = None,
        tags: Sequence[str] | None = None,
    ) -> CalibrationValidation:
        """Check a calibration as :meth:`run` would before reserving anything.

        Takes the arguments of :meth:`run`. Converts the definitions with the server's spec
        model, normalizes ``default_run_parameters`` and checks the step order, step IDs
        and filter references. Checks that need the chip (manual round layout, topology)
        run when the run starts. Reads and records nothing; ``name`` and ``tags`` are run
        metadata and are not checked.
        """
        from qdash.workflow.service.definitions import runtime_steps, runtime_target
        from qdash.workflow.service.steps import StepSequence

        del name, tags
        try:
            runtime_target(targets)
            StepSequence(runtime_steps(steps))
            if default_run_parameters:
                normalize_default_run_parameters(dict(default_run_parameters))
        except (TypeError, ValueError) as exc:
            return CalibrationValidation(valid=False, problems=(str(exc),))
        return CalibrationValidation(valid=True)

    def run(
        self,
        targets: Any,
        steps: Sequence[Any],
        *,
        default_run_parameters: Mapping[str, Any] | None = None,
        name: str | None = None,
        tags: Sequence[str] | None = None,
        note: Mapping[str, Any] | None = None,
    ) -> CalibrationResult:
        """Run the steps on the targets in this flow run and return the completed result.

        Args:
            targets: ``QubitTargets``, ``MuxTargets`` or ``CouplingTargets`` from
                :mod:`qdash.calibration`. Targets selected in the QDash UI for this launch
                replace them.
            steps: Steps from :mod:`qdash.calibration`, run in order. Runtime steps,
                including custom ``Step`` subclasses, are accepted on this worker-only path.
            default_run_parameters: Run values every task call starts from, plain or as
                sweeps. When omitted, the saved flow's defaults apply.
            name: Display name of the run; each step's Execution is named
                ``<name>_<step name>``. Pass the injected ``flow_name``.
            tags: Tags recorded on every Execution.
            note: Extra JSON-serializable data recorded in every Execution's note.

        Returns:
            The completed run: its session and run IDs, the Execution of every step it
            reached in order, final candidates, the typed result of every calibration step by
            ``step_id``, and each transform step's recorded outcome under
            ``details["transforms"]``.

        Raises:
            Exception: A step that fails raises its own exception, after its Execution is
                closed; nothing is turned into a returned failure.
        """
        from qdash.repository.run_ledger import NOTE_RUN_KEY, NOTE_SESSION_KEY
        from qdash.workflow.service._internal.runs import (
            run_calibration_with_runtime,
            workflow_settings,
        )
        from qdash.workflow.service.definitions import runtime_steps, runtime_target

        runtime_targets = runtime_target(targets)
        built = runtime_steps(steps)
        settings = workflow_settings(
            self._context,
            flow_name=name,
            tags=list(tags) if tags is not None else None,
            note=copy.deepcopy(dict(note)) if note is not None else None,
            default_run_parameters=(
                normalize_default_run_parameters(dict(default_run_parameters))
                if default_run_parameters
                else None
            ),
        )
        results, runtime = run_calibration_with_runtime(settings, runtime_targets, built)
        identity = runtime.run_identity
        self._calibration_session_id = identity.get(NOTE_SESSION_KEY, self._calibration_session_id)
        self._run_id = identity.get(NOTE_RUN_KEY, self._run_id)
        return CalibrationResult(
            status="completed",
            calibration_session_id=identity.get(NOTE_SESSION_KEY),
            run_id=identity.get(NOTE_RUN_KEY),
            execution_ids=tuple(runtime.run_execution_ids),
            candidate_qids=tuple(results.get("candidate_qids") or ()),
            candidate_couplings=tuple(results.get("candidate_couplings") or ()),
            steps=dict(results.get("steps") or {}),
            details=results,
        )


_FROM_CONTEXT = object()
