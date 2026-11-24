"""Registered workflows of a project: list, inspect and run them by name.

A registered workflow is a flow saved to QDash, from the UI or ``QDash.api.flow.save_flow``, with a
deployment and a target chip. These operations reach the server's ``/flows`` routes: they read
the stored metadata and dispatch the saved deployment. Nothing is uploaded, registered,
imported or run locally.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from qdash.sdk._http import api_errors, given, read_options
from qdash.sdk._runs import FLOW_TERMINAL_STATUSES
from qdash.sdk.errors import QDashConfigError, QDashNotFoundError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from qdash.sdk._config import QDashConfig
    from qdash.sdk._generated.client import QDashApi
    from qdash.sdk._generated.types.calibration_run_state_response import (
        CalibrationRunStateResponse,
    )
    from qdash.sdk._generated.types.execute_flow_response import ExecuteFlowResponse
    from qdash.sdk._generated.types.execution_response_detail import ExecutionResponseDetail
    from qdash.sdk._generated.types.flow_summary import FlowSummary
    from qdash.sdk._generated.types.get_flow_response import GetFlowResponse
    from qdash.sdk._results import ExecutionResult
    from qdash.sdk._runs import Executions

# The names the server accepts when a flow is saved; anything else cannot name a saved flow,
# and is rejected before it becomes part of a request path.
_NAME_PATTERN = re.compile(r"[A-Za-z0-9_]+")


def _checked_name(name: str) -> str:
    if not isinstance(name, str) or not _NAME_PATTERN.fullmatch(name):
        raise ValueError(f"workflow name must be letters, digits and underscores, got {name!r}")
    return name


def check_recorded_launch(
    response: ExecuteFlowResponse, calibration_session_id: str | None, *, what: str
) -> None:
    """Raise ``RuntimeError`` when a launch sent with a session or key was not recorded so.

    A server that predates run recording ignores both fields and starts the run anyway, so a
    missing echo means the run started without them.
    """
    recorded = isinstance(response.calibration_run_id, str)
    named = (
        calibration_session_id is None or response.calibration_session_id == calibration_session_id
    )
    if not (recorded and named):
        raise RuntimeError(
            f"{what} result unknown: the run may have started without its calibration "
            "session or key. Do not retry automatically; reconcile the execution first."
        )


@dataclass(frozen=True, repr=False)
class WorkflowRunResult:
    """A workflow run's state when it was read, from its recorded run.

    ``status`` is the whole flow run's ``run.flow_status`` as the server read it from Prefect
    in that request: ``dispatching``, ``running``, ``completed``, ``failed``, ``cancelled``,
    ``crashed``, ``not_launched``, ``unknown`` or ``unavailable``. It is never taken from a
    step execution, so a first execution that completed while the flow goes on reads
    ``running``. ``unknown`` (no flow run recorded, or Prefect does not report it) and
    ``unavailable`` (Prefect could not be read) are neither running nor ended. ``run`` is the
    run state response as the API returned it, with every step execution of the run.

    ``detail`` is the first execution's detail, read in the same call, or None when the server
    had no such execution then: a flow that failed, crashed or was never launched before it
    created one, or one still starting. The whole run's status never depends on it. It is not a
    :class:`~qdash.sdk.RunResult`, whose ``detail`` is always present.
    """

    execution_id: str
    run: CalibrationRunStateResponse
    detail: ExecutionResponseDetail | None

    @property
    def status(self) -> str:
        return str(self.run.flow_status)

    @property
    def succeeded(self) -> bool:
        """Whether Prefect reported the whole flow run completed in this read."""
        return self.status == "completed"

    @property
    def done(self) -> bool:
        """Whether the whole flow run ended (completed, failed, cancelled or crashed) or was
        never launched."""
        return self.status in FLOW_TERMINAL_STATUSES

    def __repr__(self) -> str:
        return f"{type(self).__name__}(execution_id={self.execution_id!r}, status={self.status!r})"


@dataclass(frozen=True)
class WorkflowCancellation:
    """The server's answer to :meth:`WorkflowRun.cancel`.

    ``flow_run_id`` is the Prefect flow run the cancellation was requested for: the whole
    workflow, every step execution included. ``status`` is the state the server set,
    ``cancelling``: the request was accepted, and the flow run has not ended yet. Follow it
    with :meth:`WorkflowRun.wait` until the run reads ``cancelled`` (or another end state, when
    it ended first). ``message`` is the server's description.
    """

    flow_run_id: str
    status: str
    message: str


_UNRECORDED = (
    "Workflow run {execution_id!r} has no recorded calibration run: the server that started "
    "it predates run recording, so the whole workflow's state cannot be read. QDash.run("
    "execution_id) follows the first execution's pipeline progress instead, which does not "
    "say whether a workflow with several executions ended."
)


class WorkflowRun:
    """A dispatched workflow run, returned by :meth:`Workflow.run` and :meth:`Workflows.run`.

    ``execution_id`` is the QDash execution the server created for the run; ``response`` is
    the dispatch response as the API returned it, including ``flow_run_id``. Every step
    execution of the run belongs to ``calibration_session_id`` and ``calibration_run_id``.

    :meth:`get` and :meth:`wait` follow the whole flow run through that recorded run, in a
    manual or an automatic session alike, and return a :class:`WorkflowRunResult`. The handle
    is not a :class:`~qdash.sdk.Run`: it follows the recorded run, not one execution.
    :meth:`executions` lists every execution recorded for the run. A run started by a server
    that predates run recording has no recorded run: :meth:`get` and :meth:`wait` raise
    ``RuntimeError`` instead of reporting the first execution's status, and :meth:`executions`
    follows the first execution's pipeline progress. ``QDash.run(execution_id)`` follows that
    execution as a :class:`~qdash.sdk.Run`.

    :meth:`cancel` asks the server to cancel the whole flow run, named by ``flow_run_id``.
    """

    def __init__(
        self,
        executions: Executions,
        name: str,
        response: ExecuteFlowResponse,
        *,
        project_id: str | None = None,
    ) -> None:
        self._executions = executions
        self.name = name
        self.response = response
        self._project_id = project_id

    @property
    def execution_id(self) -> str:
        """The first execution the server created for the run."""
        return self.response.execution_id

    @property
    def flow_run_id(self) -> str:
        """The Prefect flow run of the whole workflow, as the launch response named it."""
        return self.response.flow_run_id

    @property
    def calibration_session_id(self) -> str | None:
        """The run's calibration session: the one named, an automatic one, or None."""
        return self.response.calibration_session_id

    @property
    def calibration_run_id(self) -> str | None:
        """The run's record in that session; every step execution of the run carries it."""
        return self.response.calibration_run_id

    def __repr__(self) -> str:
        return f"WorkflowRun(name={self.name!r}, execution_id={self.execution_id!r})"

    def _recorded(self) -> tuple[str, str] | None:
        session_id, run_id = self.calibration_session_id, self.calibration_run_id
        if isinstance(session_id, str) and session_id and isinstance(run_id, str) and run_id:
            return session_id, run_id
        return None

    def _require_recorded(self) -> tuple[str, str]:
        recorded = self._recorded()
        if recorded is None:
            raise RuntimeError(_UNRECORDED.format(execution_id=self.execution_id))
        return recorded

    def _result(self, state: CalibrationRunStateResponse) -> WorkflowRunResult:
        # The first execution may not exist: the flow can end, or still be starting, before it
        # creates one. Only that absence is tolerated; any other read error is raised.
        try:
            detail: ExecutionResponseDetail | None = self._executions.get(self.execution_id)
        except QDashNotFoundError:
            detail = None
        return WorkflowRunResult(self.execution_id, state, detail)

    def get(self) -> WorkflowRunResult:
        """The whole workflow run's state now, read from its recorded run.

        Reads the run (the server reads Prefect for it) and then its first execution, whose
        absence leaves ``detail`` None. Raises ``QDashNotFoundError`` when the run is not
        found, and ``RuntimeError`` for a run without a recorded calibration run.
        """
        session_id, run_id = self._require_recorded()
        return self._result(self._executions.calibration_run(session_id, run_id))

    def wait(
        self,
        *,
        timeout_seconds: float = 3600.0,
        poll_interval_seconds: float = 5.0,
    ) -> WorkflowRunResult:
        """Poll the recorded run until the whole flow run ends and return its result.

        Ends on ``completed``, ``failed``, ``cancelled``, ``crashed`` or ``not_launched``; a
        failed one is returned, not raised. ``running``, ``dispatching``, ``unknown`` and
        ``unavailable`` are polled again, as is a run the server does not list yet. No
        execution status ends the wait, and an ended run is returned without waiting for its
        first execution: ``detail`` is None when the server has none. Raises ``TimeoutError``,
        naming the last state read, when the run has not ended within ``timeout_seconds``; the
        run keeps going. Raises ``RuntimeError`` for a run without a recorded calibration run.
        """
        session_id, run_id = self._require_recorded()
        last: list[str] = ["the run was not found"]

        def read() -> WorkflowRunResult | None:
            try:
                state = self._executions.calibration_run(session_id, run_id)
            except QDashNotFoundError:
                last[0] = "the run was not found"
                return None
            flow_status = str(state.flow_status)
            last[0] = f"{flow_status}: {state.flow_status_reason}".rstrip(": ")
            if flow_status not in FLOW_TERMINAL_STATUSES:
                return None
            return self._result(state)

        return self._executions.poll(
            read,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            describe=lambda: (
                f"Workflow run {run_id!r} (execution {self.execution_id!r}) did not end within "
                f"{timeout_seconds} seconds; last read: {last[0]}"
            ),
        )

    def cancel(self) -> WorkflowCancellation:
        """Ask the server to cancel the whole workflow run and return its answer.

        Cancels the Prefect flow run named by :attr:`flow_run_id`, not one step execution:
        every step of the workflow stops. Sends one ``POST /executions/{flow_run_id}/cancel``
        in the handle's project, which needs editor access there. The request is never
        retried and nothing is waited for: the result's ``status`` is ``cancelling``, and the
        run is not done until :meth:`get` or :meth:`wait` reads an end state, usually
        ``cancelled``. A run that ended first keeps its own end state.

        Raises ``QDashConfigError`` without a project and ``RuntimeError`` when the launch
        response names no valid flow run; nothing is sent then. The server's refusals are
        raised: ``QDashConflictError`` when the flow run is no longer cancellable (it ended),
        ``QDashNotFoundError`` when it is not found and ``QDashAuthError`` without editor
        access or for another project's run. After a ``QDashTransportError`` the
        cancellation may have been requested; read the run before sending it again.
        """
        if not self._project_id:
            raise QDashConfigError(
                "cancelling a workflow run needs a project: set QDASH_PROJECT_ID, "
                "project_id in the profile, or QDash(..., project_id=...)"
            )
        flow_run_id = self.response.flow_run_id
        try:
            # The server names flow runs by UUID; anything else cannot name this run, and is
            # rejected before it becomes part of a request path.
            parsed = uuid.UUID(flow_run_id)
        except (TypeError, ValueError, AttributeError):
            raise RuntimeError(
                f"Workflow run {self.execution_id!r} cannot be cancelled: its launch response "
                f"names no valid flow run (flow_run_id={flow_run_id!r})"
            ) from None
        response = self._executions.cancel_flow_run(str(parsed))
        return WorkflowCancellation(str(parsed), response.status, response.message)

    def executions(self) -> list[ExecutionResult]:
        """Every execution recorded for the run as it is now, oldest first.

        Reads the recorded run, then each of its executions; a pipeline step's result carries
        its ``step``. Each result's ``status`` is that execution's own; :meth:`get` reports the
        whole run's. Waits for nothing. A run without a recorded calibration run follows its
        first execution's pipeline progress instead, as :meth:`~qdash.sdk.Run.executions` does.
        """
        from qdash.sdk._results import ExecutionResult, collect_executions

        recorded = self._recorded()
        if recorded is None:
            return collect_executions(self._executions, self.execution_id)

        state = self._executions.calibration_run(*recorded)
        steps = {
            step.execution_id: step
            for step in (state.pipeline.steps if state.pipeline is not None else [])
            if step.execution_id
        }
        results: list[ExecutionResult] = []
        for summary in state.executions or []:
            detail = self._executions.get(summary.execution_id)
            results.append(
                ExecutionResult(
                    self._executions,
                    summary.execution_id,
                    detail,
                    step=steps.get(summary.execution_id),
                )
            )
        return results


class Workflow:
    """A registered workflow as :meth:`Workflows.get` read it.

    ``chip_id`` is the chip the workflow was saved for. ``default_parameters`` are the saved
    parameters a run starts from; they are not a full list of the parameters the workflow
    accepts. ``detail`` is the response as the API returned it, including the source ``code``.
    """

    def __init__(self, workflows: Workflows, detail: GetFlowResponse) -> None:
        self._workflows = workflows
        self.detail = detail

    @property
    def name(self) -> str:
        return self.detail.name

    @property
    def chip_id(self) -> str:
        return self.detail.chip_id

    @property
    def description(self) -> str:
        return self.detail.description

    @property
    def default_parameters(self) -> dict[str, Any]:
        return dict(self.detail.default_parameters)

    def __repr__(self) -> str:
        return f"Workflow(name={self.name!r}, chip_id={self.chip_id!r})"

    def run(
        self,
        *,
        parameters: Mapping[str, Any] | None = None,
        calibration_session_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> WorkflowRun:
        """Run this workflow; the same as ``Workflows.run(self.name, ...)``."""
        return self._workflows.run(
            self.name,
            parameters=parameters,
            calibration_session_id=calibration_session_id,
            idempotency_key=idempotency_key,
        )


class Workflows:
    """The project's registered workflows, reached as ``QDash.workflows``."""

    def __init__(
        self, api: QDashApi, config: QDashConfig, executions: Executions, project_id: str | None
    ) -> None:
        self._api = api
        self._config = config
        self._executions = executions
        self._project_id = project_id

    def list(self) -> list[FlowSummary]:
        """Summaries of the workflows registered in the session's project."""
        with api_errors():
            response = self._api.flow.list_flows(request_options=read_options(self._config))
        return list(response.flows)

    def get(self, name: str) -> Workflow:
        """The registered workflow ``name``; raises ``QDashNotFoundError`` when there is none."""
        checked = _checked_name(name)
        with api_errors():
            detail = self._api.flow.get_flow(checked, request_options=read_options(self._config))
        return Workflow(self, detail)

    def run(
        self,
        name: str,
        *,
        parameters: Mapping[str, Any] | None = None,
        calibration_session_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> WorkflowRun:
        """Dispatch the registered workflow ``name`` and return its run handle.

        The server starts from the workflow's saved ``default_parameters`` and overrides them
        with ``parameters`` for this run only; leaving them out runs the saved defaults. The
        server runs the saved deployment on the workflow's saved ``chip_id`` unless the merged
        parameters carry a ``chip_id``; the SDK adds no chip of its own. Requires a configured
        project, so the run cannot fall back to the user's default project. Returns once the
        run is dispatched; call :meth:`WorkflowRun.wait` to follow it.

        The server records the run, with every step execution, before launching it. The run
        joins ``calibration_session_id`` when given (open, on the run's chip, created by the
        signed-in user); otherwise an automatic session created for it. A retry with the same
        ``idempotency_key`` returns the recorded run instead of starting another; without a key every call starts a new run.
        The request is sent once: a transport error or an error status is raised, never
        retried. With a session or key, a response that does not echo the recorded run raises
        ``RuntimeError``: the run may have started without them, so reconcile it first.
        """
        checked = _checked_name(name)
        for label, value in (
            ("calibration_session_id", calibration_session_id),
            ("idempotency_key", idempotency_key),
        ):
            if value is not None and not value.strip():
                raise ValueError(f"{label} must be non-empty")
        if not self._project_id:
            raise QDashConfigError(
                "running a workflow needs a project: set QDASH_PROJECT_ID, "
                "project_id in the profile, or QDash(..., project_id=...)"
            )
        options = given(
            calibration_session_id=calibration_session_id, idempotency_key=idempotency_key
        )
        with api_errors():
            # The request's parameters are an object; null is rejected, so None sends {}.
            response = self._api.flow.execute_flow(
                checked,
                parameters=dict(parameters) if parameters is not None else {},
                **options,
            )
        if options:
            check_recorded_launch(response, calibration_session_id, what="Workflow")
        return WorkflowRun(self._executions, checked, response, project_id=self._project_id)
