"""Registered workflows of a project: list, inspect and run them by name.

A registered workflow is a flow saved to QDash, from the UI or ``QDash.api.flow.save_flow``, with a
deployment and a target chip. These operations reach the server's ``/flows`` routes: they read
the stored metadata and dispatch the saved deployment. Nothing is uploaded, registered,
imported or run locally.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from qdash.sdk._http import api_errors, given, read_options
from qdash.sdk._runs import Run
from qdash.sdk.errors import QDashConfigError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from qdash.sdk._config import QDashConfig
    from qdash.sdk._generated.client import QDashApi
    from qdash.sdk._generated.types.execute_flow_response import ExecuteFlowResponse
    from qdash.sdk._generated.types.flow_summary import FlowSummary
    from qdash.sdk._generated.types.get_flow_response import GetFlowResponse
    from qdash.sdk._runs import Executions

# The names the server accepts when a flow is saved; anything else cannot name a saved flow,
# and is rejected before it becomes part of a request path.
_NAME_PATTERN = re.compile(r"[A-Za-z0-9_]+")


def _checked_name(name: str) -> str:
    if not isinstance(name, str) or not _NAME_PATTERN.fullmatch(name):
        raise ValueError(f"workflow name must be letters, digits and underscores, got {name!r}")
    return name


class WorkflowRun(Run):
    """A dispatched workflow run, returned by :meth:`Workflow.run` and :meth:`Workflows.run`.

    ``execution_id`` is the QDash execution the server created for the run; ``response`` is
    the dispatch response as the API returned it, including ``flow_run_id``. Every step
    execution of the run belongs to ``calibration_session_id`` and ``calibration_run_id``.
    :meth:`get` and :meth:`wait` follow the whole run, as for a calibration.
    """

    def __init__(self, executions: Executions, name: str, response: ExecuteFlowResponse) -> None:
        super().__init__(executions, response.execution_id)
        self.name = name
        self.response = response

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
        signed-in user); otherwise an automatic session created for it. A retry with the same ``idempotency_key`` returns the
        recorded run instead of starting another; without a key every call starts a new run.
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
            # A server that predates run recording ignores both fields and starts the flow
            # anyway, so a missing echo means the run started without them.
            recorded = isinstance(response.calibration_run_id, str)
            named = (
                calibration_session_id is None
                or response.calibration_session_id == calibration_session_id
            )
            if not (recorded and named):
                raise RuntimeError(
                    "Workflow result unknown: the run may have started without its calibration "
                    "session or key. Do not retry automatically; reconcile the execution first."
                )
        return WorkflowRun(self._executions, checked, response)
