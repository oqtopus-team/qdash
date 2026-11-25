"""Calibration pipeline definitions that serialize to pipeline spec version 2.

:class:`Pipeline` and the step models re-exported here (``OneQubitCheckStep`` and the others)
are strict pipeline models generated from the API's OpenAPI document into
``qdash.sdk._generated._authoring`` (unknown fields, patterns, constants and defaults are
enforced locally); :class:`Pipeline` fixes ``spec_version``. :class:`TaskCall`,
:class:`QubitTargets`, :class:`MuxTargets` and :class:`CustomOneQubit` are the shared
definitions of :mod:`qdash.calibration`. Building them checks only the structure
the schema describes, such as required fields, ID patterns and literal values. Whether a
pipeline can run, including task names, call ID uniqueness, step order and calibration data,
is decided by the server's validate and execute routes.

Defining a pipeline has no effects: no request is sent and nothing runs until
``Chip.validate_calibration``, ``Chip.calibrate``, ``QDash.pipelines.validate`` or
``QDash.pipelines.execute`` is called.

This module is the wire-level layer. Write calibrations with the shared definitions of
:mod:`qdash.calibration` (re-exported by :mod:`qdash.sdk.calibration`) and run them with
:class:`qdash.sdk.CalibrationSession`; :class:`Pipeline` accepts those definitions too.

Any other step type can be passed as its generated model, re-exported here (for example
``OneQubitCheckStep(type="OneQubitCheck")``), or as a plain dictionary in the spec's JSON form.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Literal

from pydantic import model_validator

from qdash.calibration import (
    CalibrationTargets,
    CustomOneQubit,
    ExecutionStep,
    MuxTargets,
    QubitTargets,
    TaskCall,
)
from qdash.calibration.steps import OneQubitStepExecutionMode as OneQubitExecutionMode
from qdash.sdk import sweep
from qdash.sdk._generated._authoring import (
    BringUpStep,
    CalibrationPipelineSpec,
    ConfigureAllStep,
    CustomOneQubitStep,
    CustomTwoQubitStep,
    FilterByMetricStep,
    FilterByStatusStep,
    GenerateCRScheduleStep,
    OneQubitCheckStep,
    OneQubitFineTuneStep,
    PipelineTargets,
    TaskSettings,
    TwoQubitCalibrationStep,
)

if TYPE_CHECKING:
    from pydantic import BaseModel

__all__ = [
    "BringUpStep",
    "CalibrationPipelineSpec",
    "ConfigureAllStep",
    "CustomOneQubit",
    "CustomOneQubitStep",
    "CustomTwoQubitStep",
    "FilterByMetricStep",
    "FilterByStatusStep",
    "GenerateCRScheduleStep",
    "MuxTargets",
    "OnFailure",
    "OneQubitCheckStep",
    "OneQubitExecutionMode",
    "OneQubitFineTuneStep",
    "Pipeline",
    "PipelineSpecInput",
    "PipelineTargets",
    "QubitTargets",
    "Qubits",
    "TaskCall",
    "TaskSettings",
    "TwoQubitCalibrationStep",
    "sweep",
    "to_spec",
]

OnFailure = Literal["continue", "stop"]


Qubits = QubitTargets
"""The earlier name of :class:`QubitTargets`; the same class."""


class Pipeline(CalibrationPipelineSpec):
    """A calibration pipeline spec, version 2.

    Targets and steps may also be the shared definitions of :mod:`qdash.calibration`; they
    are written in their spec JSON, with only the fields that were set.
    """

    spec_version: Literal[2] = 2

    @model_validator(mode="before")
    @classmethod
    def _shared_definitions(cls, data: Any) -> Any:
        if not isinstance(data, Mapping):
            return data
        converted = dict(data)
        for key in ("targets", "steps"):
            if key in converted:
                converted[key] = _plain(converted[key])
        return converted

    if TYPE_CHECKING:

        def __init__(
            self,
            *,
            targets: PipelineTargets | CalibrationTargets | Mapping[str, Any],
            steps: Sequence[BaseModel | Mapping[str, Any]],
            name: str = ...,
            default_run_parameters: Mapping[str, Any] = ...,
            tags: Sequence[str] = ...,
            spec_version: Literal[2] = 2,
        ) -> None: ...

    def to_spec(self) -> dict[str, Any]:
        """The spec as the JSON object the validate and execute routes accept."""
        return to_spec(self)


def _plain(value: Any) -> Any:
    """Shared definitions anywhere in ``value`` as their spec JSON; anything else as it is."""
    if isinstance(value, CalibrationTargets | ExecutionStep | TaskCall):
        return value.to_spec()
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    return value


PipelineSpecInput = CalibrationPipelineSpec | Mapping[str, Any]
"""A :class:`Pipeline`, any generated ``CalibrationPipelineSpec``, or a spec as a mapping."""


def to_spec(pipeline: PipelineSpecInput) -> dict[str, Any]:
    """Serialize a pipeline to the spec JSON object the API accepts.

    A model is written with only the fields that were set, plus ``spec_version`` and each
    step's ``type``, so server defaults apply to everything left out. A mapping is copied
    unchanged and is not checked locally; the server reports its problems, and migrates a
    version 1 spec when validating it.
    """
    if not isinstance(pipeline, CalibrationPipelineSpec):
        if not isinstance(pipeline, Mapping):
            raise TypeError(
                "pipeline must be a Pipeline, a CalibrationPipelineSpec or a mapping, "
                f"got {type(pipeline).__name__}"
            )
        return dict(pipeline)
    spec = {
        "spec_version": pipeline.spec_version,
        **pipeline.model_dump(mode="json", exclude_unset=True),
    }
    for step_json, step in zip(spec["steps"], pipeline.steps, strict=True):
        step_json["type"] = step.type
    return spec
