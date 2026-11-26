"""Pipeline operations of a QDash session: catalog, validate, execute, plans, wait."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qdash.sdk._http import api_errors, given, read_options
from qdash.sdk.errors import QDashConfigError
from qdash.sdk.pipeline import to_spec

if TYPE_CHECKING:
    from qdash.sdk._config import QDashConfig
    from qdash.sdk._generated.client import QDashApi
    from qdash.sdk._generated.types.execute_pipeline_response import ExecutePipelineResponse
    from qdash.sdk._generated.types.execution_response_detail import ExecutionResponseDetail
    from qdash.sdk._generated.types.pipeline_catalog_response import PipelineCatalogResponse
    from qdash.sdk._generated.types.pipeline_plan_response import PipelinePlanResponse
    from qdash.sdk._generated.types.validate_pipeline_response import ValidatePipelineResponse
    from qdash.sdk._results import ExecutionResult
    from qdash.sdk._runs import Executions
    from qdash.sdk.pipeline import PipelineSpecInput


def _non_empty(label: str, value: str | None) -> None:
    if value is not None and not value.strip():
        raise ValueError(f"{label} must be non-empty")


class PipelineRun:
    """A dispatched pipeline execution.

    ``execution_id`` names the execution the server created for the run. Its detail carries
    ``pipeline`` progress for every step once the worker reports it.
    """

    def __init__(self, executions: Executions, response: ExecutePipelineResponse) -> None:
        self._executions = executions
        self.response = response

    @property
    def execution_id(self) -> str:
        return self.response.execution_id

    def __repr__(self) -> str:
        return f"PipelineRun(execution_id={self.execution_id!r})"

    def get(self) -> ExecutionResponseDetail:
        """The execution's current detail; raises ``QDashNotFoundError`` before it exists."""
        return self._executions.get(self.execution_id)

    def executions(self) -> list[ExecutionResult]:
        """Each execution of the run as it is now, in pipeline step order.

        The same as :meth:`Run.executions <qdash.sdk.Run.executions>`: each result's
        ``status`` is that execution's own, and pending steps and transforms are skipped.
        """
        from qdash.sdk._results import collect_executions

        return collect_executions(self._executions, self.execution_id)

    def wait(
        self,
        *,
        timeout_seconds: float = 3600.0,
        poll_interval_seconds: float = 5.0,
        progress: bool = True,
    ) -> ExecutionResponseDetail:
        """Poll until the whole pipeline run ends, then return the execution detail.

        The run's outcome is ``detail.pipeline.status`` when the server reports pipeline
        progress, otherwise ``detail.status``. A failed or cancelled run is returned, not
        raised. An execution the server does not list yet is polled again. Raises
        ``TimeoutError`` when the run has not ended within ``timeout_seconds``; the run itself
        keeps going.

        ``progress`` shows the whole run's status, its step and task counts as each poll
        reads them, and the time waited: updated in place in a notebook cell or an
        interactive terminal (on stderr), and as one stderr line per change otherwise.
        ``progress=False`` writes nothing.
        """
        return self._executions.wait(
            self.execution_id,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            progress=progress,
            label=f"pipeline run {self.execution_id}",
        )


class Pipelines:
    """Calibration pipeline routes, reached as ``QDash.pipelines``."""

    def __init__(
        self, api: QDashApi, config: QDashConfig, executions: Executions, project_id: str | None
    ) -> None:
        self._api = api
        self._config = config
        self._executions = executions
        self._project_id = project_id

    def catalog(self, *, backend_name: str | None = None) -> PipelineCatalogResponse:
        """Step types, task names by type and the spec schema the server accepts."""
        with api_errors():
            return self._api.calibration_pipeline.get_calibration_pipeline_catalog(
                **given(backend_name=backend_name), request_options=read_options(self._config)
            )

    def validate(
        self,
        pipeline: PipelineSpecInput,
        *,
        chip_id: str,
        backend_name: str | None = None,
    ) -> ValidatePipelineResponse:
        """Check a pipeline against the project, chip and backend without running it.

        The server reports every problem, including preflight checks that read calibration
        data, in the response; ``valid`` is false when there is any. Nothing is dispatched.
        """
        with api_errors():
            return self._api.calibration_pipeline.validate_calibration_pipeline(
                chip_id=chip_id, spec=to_spec(pipeline), **given(backend_name=backend_name)
            )

    def execute(
        self,
        pipeline: PipelineSpecInput,
        *,
        chip_id: str,
        backend_name: str | None = None,
        calibration_session_id: str | None = None,
        idempotency_key: str | None = None,
        decision_id: str | None = None,
    ) -> PipelineRun:
        """Dispatch a pipeline and return a handle for the whole run across steps.

        The server validates the spec again and rejects one with problems with
        ``QDashValidationError``. Requires a configured project, so the run cannot fall back
        to the user's default project. Returns once the run is dispatched; call
        :meth:`PipelineRun.wait` to follow it. The request is sent once: a transport error or
        an error status is raised, never retried.

        The run is recorded before it is launched. It joins ``calibration_session_id`` when
        given, which is read first to check it exists on ``chip_id``; otherwise an automatic
        session created for it. A retry with the same ``idempotency_key`` returns the recorded
        run instead of starting another; without a key every call starts a new run.

        ``decision_id`` names the recorded decision of that session the run carries out, so
        the session's audit links the intent to the run; it needs ``calibration_session_id``.
        A response that does not echo the session or the decision raises ``RuntimeError``: the
        run may have started without the link, so reconcile it instead of retrying.
        """
        if decision_id is not None and calibration_session_id is None:
            raise ValueError("decision_id needs calibration_session_id")
        _non_empty("decision_id", decision_id)
        _non_empty("idempotency_key", idempotency_key)
        _non_empty("calibration_session_id", calibration_session_id)
        if not self._project_id:
            raise QDashConfigError(
                "running a calibration pipeline needs a project: set QDASH_PROJECT_ID, "
                "project_id in the profile, or QDash(..., project_id=...)"
            )
        spec = to_spec(pipeline)
        if calibration_session_id is not None:
            self._preflight_session(calibration_session_id, chip_id)
        with api_errors():
            response = self._api.calibration_pipeline.execute_calibration_pipeline(
                chip_id=chip_id,
                spec=spec,
                **given(
                    backend_name=backend_name,
                    calibration_session_id=calibration_session_id,
                    idempotency_key=idempotency_key,
                    decision_id=decision_id,
                ),
            )
        if calibration_session_id is not None:
            run_id = response.pipeline_run_id
            if response.calibration_session_id != calibration_session_id or not (
                isinstance(run_id, str) and run_id.strip()
            ):
                raise RuntimeError(
                    "Pipeline result unknown: the execution may have started without its "
                    "association. Do not retry automatically or use a new key; "
                    "reconcile the execution first."
                )
            if decision_id is not None and response.decision_id != decision_id:
                raise RuntimeError(
                    "Pipeline result unknown: the run may have been recorded without its "
                    f"decision {decision_id!r}. Do not retry automatically or use a new key; "
                    "reconcile the run in the calibration session audit first."
                )
        return PipelineRun(self._executions, response)

    def create_plan(
        self,
        pipeline: PipelineSpecInput,
        *,
        chip_id: str,
        idempotency_key: str,
        backend_name: str | None = None,
    ) -> PipelinePlanResponse:
        """Validate a pipeline and store it as a plan to approve and run by reference.

        Nothing is run, reserved or recorded in a session; an invalid spec raises
        ``QDashValidationError`` with the problems of :meth:`validate` and stores nothing. The
        plan holds the normalized spec with every default task list written out, the qubits
        its targets resolve to, the resolved calls, and its ``review_digest``; it expires
        after 24 hours and is never renewed.

        ``idempotency_key`` names this creation: repeating it with the same request returns
        the same plan (``replayed``), with another request raises ``QDashConflictError``, and
        once the plan expired raises an error (410). Sent once; after a transport error,
        repeating the call with the same key is safe.
        """
        if not idempotency_key or not idempotency_key.strip():
            raise ValueError("idempotency_key must be non-empty")
        with api_errors():
            return self._api.calibration_pipeline.create_calibration_pipeline_plan(
                chip_id=chip_id,
                spec=to_spec(pipeline),
                idempotency_key=idempotency_key,
                **given(backend_name=backend_name),
            )

    def get_plan(self, plan_id: str) -> PipelinePlanResponse:
        """A stored plan of the signed-in user; ``expired`` says whether it can still run.

        Another user's plan raises ``QDashNotFoundError``.
        """
        _non_empty("plan_id", plan_id)
        with api_errors():
            return self._api.calibration_pipeline.get_calibration_pipeline_plan(
                plan_id, request_options=read_options(self._config)
            )

    def execute_plan(
        self,
        plan_id: str,
        *,
        chip_id: str,
        expected_review_digest: str,
        backend_name: str | None = None,
        calibration_session_id: str | None = None,
        idempotency_key: str | None = None,
        decision_id: str | None = None,
    ) -> PipelineRun:
        """Run a stored plan exactly as it was approved.

        ``expected_review_digest`` is the ``review_digest`` of the plan the person approved.
        The server refuses the plan when it expired, is for another chip or backend, no
        longer has that digest, or resolves to other content now. Recording, retries and
        errors are those of :meth:`execute`; a retry with the same key returns the recorded
        run even after the plan expired. A response that does not echo the plan and its
        review digest (or the session, run and decision asked for) raises ``RuntimeError``:
        the run may have started, so reconcile it instead of retrying.
        """
        _non_empty("plan_id", plan_id)
        if not expected_review_digest or not expected_review_digest.strip():
            raise ValueError("expected_review_digest must be non-empty")
        if decision_id is not None and calibration_session_id is None:
            raise ValueError("decision_id needs calibration_session_id")
        _non_empty("decision_id", decision_id)
        _non_empty("idempotency_key", idempotency_key)
        _non_empty("calibration_session_id", calibration_session_id)
        if not self._project_id:
            raise QDashConfigError(
                "running a calibration pipeline needs a project: set QDASH_PROJECT_ID, "
                "project_id in the profile, or QDash(..., project_id=...)"
            )
        if calibration_session_id is not None:
            self._preflight_session(calibration_session_id, chip_id)
        with api_errors():
            response = self._api.calibration_pipeline.execute_calibration_pipeline_plan(
                plan_id,
                chip_id=chip_id,
                expected_review_digest=expected_review_digest,
                **given(
                    backend_name=backend_name,
                    calibration_session_id=calibration_session_id,
                    idempotency_key=idempotency_key,
                    decision_id=decision_id,
                ),
            )
        if response.plan_id != plan_id or response.review_digest != expected_review_digest:
            raise RuntimeError(
                f"Pipeline plan result unknown: the response does not confirm plan {plan_id!r} "
                f"with review digest {expected_review_digest!r}. Do not retry automatically or "
                "use a new key; reconcile the execution first."
            )
        if calibration_session_id is not None:
            run_id = response.pipeline_run_id
            if response.calibration_session_id != calibration_session_id or not (
                isinstance(run_id, str) and run_id.strip()
            ):
                raise RuntimeError(
                    "Pipeline plan result unknown: the execution may have started without its "
                    "association. Do not retry automatically or use a new key; "
                    "reconcile the execution first."
                )
            if decision_id is not None and response.decision_id != decision_id:
                raise RuntimeError(
                    "Pipeline plan result unknown: the run may have been recorded without its "
                    f"decision {decision_id!r}. Do not retry automatically or use a new key; "
                    "reconcile the run in the calibration session audit first."
                )
        return PipelineRun(self._executions, response)

    def _preflight_session(self, session_id: str, chip_id: str) -> None:
        """Prove the server records sessions before an associated write; nothing is sent else."""
        with api_errors():
            session = self._api.calibration_session.get_calibration_session(
                session_id, request_options=read_options(self._config)
            )
        if session.calibration_session_id != session_id or session.chip_id != chip_id:
            raise ValueError(
                "Calibration session preflight failed; nothing dispatched. "
                "Check server compatibility."
            )
