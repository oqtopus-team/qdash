"""Calibration on one chip: ``Chip.validate_calibration``, ``Chip.calibrate`` and the run.

These are a front door over :class:`~qdash.sdk.Pipelines`: a
:class:`~qdash.sdk.pipeline.Pipeline` is sent as it is, or ``targets`` and ``steps`` become
one, and validation, dispatch and waiting are the pipeline operations' own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, overload

from qdash.sdk._runs import Run
from qdash.sdk.pipeline import CalibrationPipelineSpec, Pipeline

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from pydantic import BaseModel

    from qdash.sdk._generated.types.execute_pipeline_response import ExecutePipelineResponse
    from qdash.sdk._generated.types.validate_pipeline_response import ValidatePipelineResponse
    from qdash.sdk._pipelines import Pipelines
    from qdash.sdk._runs import Executions
    from qdash.sdk.pipeline import PipelineTargets


class CalibrationRun(Run):
    """A dispatched calibration, returned by :meth:`Chip.calibrate`.

    ``execution_id`` is the execution the server created for the first step; ``response`` is
    the dispatch response as the API returned it. :meth:`get` and :meth:`wait` return a
    :class:`~qdash.sdk.RunResult` for the whole calibration: a failed or cancelled one is
    returned, not raised, and a timeout leaves it running.
    """

    def __init__(self, executions: Executions, response: ExecutePipelineResponse) -> None:
        super().__init__(executions, response.execution_id)
        self.response = response


class Chip:
    """Calibration on one chip, reached as ``QDash.chip(chip_id)``.

    Holds the session's client, project and the chip ID; creating it sends no request.
    """

    def __init__(self, pipelines: Pipelines, executions: Executions, chip_id: str) -> None:
        if not isinstance(chip_id, str) or not chip_id:
            raise ValueError("chip_id must be a non-empty string")
        self._pipelines = pipelines
        self._executions = executions
        self._chip_id = chip_id

    @property
    def chip_id(self) -> str:
        return self._chip_id

    def __repr__(self) -> str:
        return f"Chip({self._chip_id!r})"

    @overload
    def validate_calibration(
        self, pipeline: CalibrationPipelineSpec, /, *, backend_name: str | None = None
    ) -> ValidatePipelineResponse: ...

    @overload
    def validate_calibration(
        self,
        targets: PipelineTargets | Mapping[str, Any],
        steps: Sequence[BaseModel | Mapping[str, Any]],
        *,
        name: str | None = None,
        default_run_parameters: Mapping[str, Any] | None = None,
        tags: Sequence[str] | None = None,
        backend_name: str | None = None,
    ) -> ValidatePipelineResponse: ...

    def validate_calibration(
        self,
        targets: CalibrationPipelineSpec | PipelineTargets | Mapping[str, Any],
        steps: Sequence[BaseModel | Mapping[str, Any]] | None = None,
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

    @overload
    def calibrate(
        self, pipeline: CalibrationPipelineSpec, /, *, backend_name: str | None = None
    ) -> CalibrationRun: ...

    @overload
    def calibrate(
        self,
        targets: PipelineTargets | Mapping[str, Any],
        steps: Sequence[BaseModel | Mapping[str, Any]],
        *,
        name: str | None = None,
        default_run_parameters: Mapping[str, Any] | None = None,
        tags: Sequence[str] | None = None,
        backend_name: str | None = None,
    ) -> CalibrationRun: ...

    def calibrate(
        self,
        targets: CalibrationPipelineSpec | PipelineTargets | Mapping[str, Any],
        steps: Sequence[BaseModel | Mapping[str, Any]] | None = None,
        *,
        name: str | None = None,
        default_run_parameters: Mapping[str, Any] | None = None,
        tags: Sequence[str] | None = None,
        backend_name: str | None = None,
    ) -> CalibrationRun:
        """Start a calibration on this chip: a whole ``Pipeline``, or ``targets`` and ``steps``.

        ``chip.calibrate(pipeline)`` sends the :class:`~qdash.sdk.pipeline.Pipeline` (or any
        ``CalibrationPipelineSpec``) as it is, with every field that was set. It takes only
        ``backend_name`` besides; ``steps``, ``name``, ``default_run_parameters`` or ``tags``
        with it raise ``TypeError``, so set them on the pipeline instead.

        ``chip.calibrate(targets, steps, ...)`` builds the pipeline: ``steps`` run in order on
        ``targets``, ``name`` is the execution's display name, ``default_run_parameters`` the
        run parameters every task call starts from, and ``tags`` the execution's tags; the
        server's defaults apply to any left out.

        Dispatches one calibration pipeline execution, which measures on the hardware. The
        request is sent once. The server validates the calibration before dispatch and
        rejects one with problems with ``QDashValidationError``; calling
        :meth:`validate_calibration` first is optional. Requires a project on the session.
        Returns once the run is dispatched; call :meth:`CalibrationRun.wait` to follow it.
        """
        pipeline = _pipeline(targets, steps, name, default_run_parameters, tags)
        run = self._pipelines.execute(pipeline, chip_id=self._chip_id, backend_name=backend_name)
        return CalibrationRun(self._executions, run.response)


def _pipeline(
    targets: CalibrationPipelineSpec | PipelineTargets | Mapping[str, Any],
    steps: Sequence[BaseModel | Mapping[str, Any]] | None,
    name: str | None,
    default_run_parameters: Mapping[str, Any] | None,
    tags: Sequence[str] | None,
) -> CalibrationPipelineSpec:
    if isinstance(targets, CalibrationPipelineSpec):
        # A whole pipeline is sent as it is; a field given beside it would have to override
        # or be dropped, so the call is rejected before any request.
        extra = [
            label
            for label, value in (
                ("steps", steps),
                ("name", name),
                ("default_run_parameters", default_run_parameters),
                ("tags", tags),
            )
            if value is not None
        ]
        if extra:
            raise TypeError(
                f"a Pipeline already defines {', '.join(extra)}; set them on the Pipeline "
                "instead of passing them with it"
            )
        return targets
    if steps is None:
        raise TypeError("steps is required with targets; or pass a whole Pipeline")
    # Only the options given are set, so the spec leaves the rest to the server's defaults.
    options: dict[str, Any] = {}
    if name is not None:
        options["name"] = name
    if default_run_parameters is not None:
        options["default_run_parameters"] = default_run_parameters
    if tags is not None:
        options["tags"] = tags
    return Pipeline(targets=targets, steps=steps, **options)
