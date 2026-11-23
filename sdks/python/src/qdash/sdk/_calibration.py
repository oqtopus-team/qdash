"""Calibration on one chip: ``Chip.validate_calibration``, ``Chip.calibrate`` and the run.

These are a front door over :class:`~qdash.sdk.Pipelines`: ``targets`` and ``steps`` become a
:class:`~qdash.sdk.pipeline.Pipeline`, and validation, dispatch and waiting are the pipeline
operations' own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from qdash.sdk._runs import RunResult
from qdash.sdk.pipeline import Pipeline

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from pydantic import BaseModel

    from qdash.client.services.models import (
        ExecutePipelineResponse,
        PipelineTargets,
        ValidatePipelineResponse,
    )
    from qdash.sdk._pipelines import PipelineRun, Pipelines


class CalibrationRun:
    """A dispatched calibration, returned by :meth:`Chip.calibrate`.

    ``execution_id`` is the execution the server created for the first step; ``response`` is
    the dispatch response as the API returned it.
    """

    def __init__(self, run: PipelineRun) -> None:
        self._run = run

    @property
    def execution_id(self) -> str:
        return self._run.execution_id

    @property
    def response(self) -> ExecutePipelineResponse:
        return self._run.response

    def __repr__(self) -> str:
        return f"CalibrationRun(execution_id={self.execution_id!r})"

    def get(self) -> RunResult:
        """The run's current state; raises ``QDashNotFoundError`` before it exists."""
        return RunResult(self.execution_id, self._run.get())

    def wait(
        self,
        *,
        timeout_seconds: float = 3600.0,
        poll_interval_seconds: float = 5.0,
    ) -> RunResult:
        """Poll until the whole calibration ends and return its result.

        A failed or cancelled calibration is returned, not raised; check ``result.status``.
        Raises ``TimeoutError`` when the run has not ended within ``timeout_seconds``; the
        run itself keeps going. Same polling as :meth:`PipelineRun.wait`.
        """
        detail = self._run.wait(
            timeout_seconds=timeout_seconds, poll_interval_seconds=poll_interval_seconds
        )
        return RunResult(self.execution_id, detail)


class Chip:
    """Calibration on one chip, reached as ``QDash.chip(chip_id)``.

    Holds the session's client, project and the chip ID; creating it sends no request.
    """

    def __init__(self, pipelines: Pipelines, chip_id: str) -> None:
        if not isinstance(chip_id, str) or not chip_id:
            raise ValueError("chip_id must be a non-empty string")
        self._pipelines = pipelines
        self._chip_id = chip_id

    @property
    def chip_id(self) -> str:
        return self._chip_id

    def __repr__(self) -> str:
        return f"Chip({self._chip_id!r})"

    def validate_calibration(
        self,
        targets: PipelineTargets | Mapping[str, Any],
        steps: Sequence[BaseModel | Mapping[str, Any]],
        *,
        name: str | None = None,
        default_run_parameters: Mapping[str, Any] | None = None,
        tags: Sequence[str] | None = None,
        backend_name: str | None = None,
    ) -> ValidatePipelineResponse:
        """Check a calibration on this chip without running it.

        Takes the same arguments as :meth:`calibrate`. The server reports every problem,
        including preflight checks that read calibration data, in the response; ``valid`` is
        false when there is any. Nothing is dispatched.
        """
        pipeline = _pipeline(targets, steps, name, default_run_parameters, tags)
        return self._pipelines.validate(pipeline, chip_id=self._chip_id, backend_name=backend_name)

    def calibrate(
        self,
        targets: PipelineTargets | Mapping[str, Any],
        steps: Sequence[BaseModel | Mapping[str, Any]],
        *,
        name: str | None = None,
        default_run_parameters: Mapping[str, Any] | None = None,
        tags: Sequence[str] | None = None,
        backend_name: str | None = None,
    ) -> CalibrationRun:
        """Start a calibration of ``targets`` on this chip: ``steps`` run in order.

        Dispatches one calibration pipeline execution, which measures on the hardware.
        ``name`` is the execution's display name, ``default_run_parameters`` the run
        parameters every task call starts from, and ``tags`` the execution's tags; the
        server's defaults apply to any left out. The server validates the calibration
        before dispatch and rejects one with problems with ``QDashValidationError``; calling
        :meth:`validate_calibration` first is optional. Requires a project on the session.
        Returns once the run is dispatched; call :meth:`CalibrationRun.wait` to follow it.
        """
        pipeline = _pipeline(targets, steps, name, default_run_parameters, tags)
        run = self._pipelines.execute(pipeline, chip_id=self._chip_id, backend_name=backend_name)
        return CalibrationRun(run)


def _pipeline(
    targets: PipelineTargets | Mapping[str, Any],
    steps: Sequence[BaseModel | Mapping[str, Any]],
    name: str | None,
    default_run_parameters: Mapping[str, Any] | None,
    tags: Sequence[str] | None,
) -> Pipeline:
    # Only the options given are set, so the spec leaves the rest to the server's defaults.
    options: dict[str, Any] = {}
    if name is not None:
        options["name"] = name
    if default_run_parameters is not None:
        options["default_run_parameters"] = default_run_parameters
    if tags is not None:
        options["tags"] = tags
    return Pipeline(targets=targets, steps=steps, **options)
