"""Pipeline operations of a QDash session: catalog, validate, execute, wait."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qdash.client.services.errors import QDashConfigError
from qdash.sdk.pipeline import to_spec

if TYPE_CHECKING:
    from qdash.client.services.client import QDashClient
    from qdash.client.services.models import (
        ExecutePipelineResponse,
        ExecutionResponseDetail,
        PipelineCatalogResponse,
        ValidatePipelineResponse,
    )
    from qdash.sdk.pipeline import PipelineSpecInput


class PipelineRun:
    """A dispatched pipeline execution.

    ``execution_id`` names the execution the server created for the run. Its detail carries
    ``pipeline`` progress for every step once the worker reports it.
    """

    def __init__(self, client: QDashClient, response: ExecutePipelineResponse) -> None:
        self._client = client
        self.response = response

    @property
    def execution_id(self) -> str:
        return self.response.execution_id

    def __repr__(self) -> str:
        return f"PipelineRun(execution_id={self.execution_id!r})"

    def get(self) -> ExecutionResponseDetail:
        """The execution's current detail; raises ``QDashNotFoundError`` before it exists."""
        return self._client.get_execution(self.execution_id)

    def wait(
        self,
        *,
        timeout_seconds: float = 3600.0,
        poll_interval_seconds: float = 5.0,
    ) -> ExecutionResponseDetail:
        """Poll until the whole pipeline run ends, then return the execution detail.

        The run's outcome is ``detail.pipeline.status`` when the server reports pipeline
        progress, otherwise ``detail.status``. A failed or cancelled run is returned, not
        raised. An execution the server does not list yet is polled again. Raises
        ``TimeoutError`` when the run has not ended within ``timeout_seconds``; the run itself
        keeps going.
        """
        return self._client.wait_for_execution(
            self.execution_id,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            whole_pipeline=True,
        )


class Pipelines:
    """Calibration pipeline routes, reached as ``QDash.pipelines``."""

    def __init__(self, client: QDashClient) -> None:
        self._client = client

    def catalog(self, *, backend_name: str | None = None) -> PipelineCatalogResponse:
        """Step types, task names by type and the spec schema the server accepts."""
        return self._client.get_calibration_pipeline_catalog(backend_name=backend_name)

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
        return self._client.validate_calibration_pipeline(
            chip_id=chip_id, spec=to_spec(pipeline), backend_name=backend_name
        )

    def execute(
        self,
        pipeline: PipelineSpecInput,
        *,
        chip_id: str,
        backend_name: str | None = None,
        calibration_session_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> PipelineRun:
        """Dispatch a pipeline as one execution and return its run handle.

        The server validates the spec again and rejects one with problems with
        ``QDashValidationError``. Requires a configured project, so the run cannot fall back
        to the user's default project. Returns once the run is dispatched; call
        :meth:`PipelineRun.wait` to follow it.

        ``calibration_session_id`` and ``idempotency_key``, given together, record the run in
        that calibration session before it is launched; a retry with the same key returns the
        recorded run instead of starting another. Grouping grants nothing.
        """
        if (calibration_session_id is None) != (idempotency_key is None):
            raise ValueError("calibration_session_id and idempotency_key are given together")
        if not self._client.config.project_id:
            raise QDashConfigError(
                "running a calibration pipeline needs a project: set QDASH_PROJECT_ID, "
                "project_id in the profile, or QDash(..., project_id=...)"
            )
        response = self._client.execute_calibration_pipeline(
            chip_id=chip_id,
            spec=to_spec(pipeline),
            backend_name=backend_name,
            calibration_session_id=calibration_session_id,
            idempotency_key=idempotency_key,
        )
        return PipelineRun(self._client, response)
