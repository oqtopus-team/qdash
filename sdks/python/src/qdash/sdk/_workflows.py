"""Registered workflows of a project: list, inspect and run them by name.

A registered workflow is a flow saved to QDash, from the UI or ``QDashClient.save_flow``, with a
deployment and a target chip. These operations reach the server's ``/flows`` routes: they read
the stored metadata and dispatch the saved deployment. Nothing is uploaded, registered,
imported or run locally.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from qdash.client.services.errors import QDashConfigError
from qdash.sdk._runs import RunResult

if TYPE_CHECKING:
    from collections.abc import Mapping

    from qdash.client.services.client import QDashClient
    from qdash.client.services.models import (
        ExecuteFlowResponse,
        FlowSummary,
        GetFlowResponse,
    )

# The names the server accepts when a flow is saved; anything else cannot name a saved flow,
# and is rejected before it becomes part of a request path.
_NAME_PATTERN = re.compile(r"[A-Za-z0-9_]+")


def _checked_name(name: str) -> str:
    if not isinstance(name, str) or not _NAME_PATTERN.fullmatch(name):
        raise ValueError(f"workflow name must be letters, digits and underscores, got {name!r}")
    return name


class WorkflowRun:
    """A dispatched workflow run, returned by :meth:`Workflow.run` and :meth:`Workflows.run`.

    ``execution_id`` is the QDash execution the server created for the run; ``response`` is
    the dispatch response as the API returned it, including ``flow_run_id``. Every step
    execution of the run belongs to ``calibration_session_id`` and ``calibration_run_id``.
    """

    def __init__(self, client: QDashClient, name: str, response: ExecuteFlowResponse) -> None:
        self._client = client
        self.name = name
        self.response = response

    @property
    def execution_id(self) -> str:
        return self.response.execution_id

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

    def get(self) -> RunResult:
        """The run's current state; raises ``QDashNotFoundError`` before it exists."""
        return RunResult(self.execution_id, self._client.get_execution(self.execution_id))

    def wait(
        self,
        *,
        timeout_seconds: float = 3600.0,
        poll_interval_seconds: float = 5.0,
    ) -> RunResult:
        """Poll until the whole run ends and return its result.

        A failed or cancelled run is returned, not raised; check ``result.status``. An
        execution the server does not list yet is polled again. Raises ``TimeoutError`` when
        the run has not ended within ``timeout_seconds``; the run itself keeps going. Same
        polling as :meth:`PipelineRun.wait`.
        """
        detail = self._client.wait_for_execution(
            self.execution_id,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            whole_pipeline=True,
        )
        return RunResult(self.execution_id, detail)


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

    def __init__(self, client: QDashClient) -> None:
        self._client = client

    def list(self) -> list[FlowSummary]:
        """Summaries of the workflows registered in the session's project."""
        return list(self._client.list_flows().flows)

    def get(self, name: str) -> Workflow:
        """The registered workflow ``name``; raises ``QDashNotFoundError`` when there is none."""
        return Workflow(self, self._client.get_flow(_checked_name(name)))

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
        signed-in user); otherwise an automatic session when the server groups runs
        automatically, or none. A retry with the same ``idempotency_key`` returns the
        recorded run instead of starting another; without a key every call starts a new run.
        """
        checked = _checked_name(name)
        if not self._client.config.project_id:
            raise QDashConfigError(
                "running a workflow needs a project: set QDASH_PROJECT_ID, "
                "project_id in the profile, or QDash(..., project_id=...)"
            )
        response = self._client.execute_flow(
            checked,
            parameters=dict(parameters) if parameters is not None else {},
            calibration_session_id=calibration_session_id,
            idempotency_key=idempotency_key,
        )
        return WorkflowRun(self._client, checked, response)
