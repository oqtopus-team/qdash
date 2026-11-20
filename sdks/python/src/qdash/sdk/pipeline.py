"""Calibration pipeline definitions that serialize to pipeline spec version 2.

The classes here are the API's generated pipeline models (``qdash.client`` builds them from the
OpenAPI document) with a few conveniences: :class:`Pipeline` fixes ``spec_version``,
:class:`QubitTargets` and :class:`MuxTargets` select qubit IDs or MUXes, and
:class:`CustomOneQubit` fills in the step ``type``. Building them checks only the structure
the schema describes, such as required fields, ID patterns and literal values. Whether a
pipeline can run, including task names, call ID uniqueness, step order and calibration data,
is decided by the server's validate and execute routes.

Defining a pipeline has no effects: no request is sent and nothing runs until
``Chip.validate_calibration``, ``Chip.calibrate``, ``QDash.pipelines.validate`` or
``QDash.pipelines.execute`` is called. :mod:`qdash.sdk.calibration` re-exports the definitions
a calibration needs; this module adds :class:`Pipeline` for building a whole spec.

Any other step type can be passed as its generated model from
``qdash.client.services.models`` (for example ``OneQubitCheckStep(type="OneQubitCheck")``) or
as a plain dictionary in the spec's JSON form.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Literal

from qdash.client.services import models
from qdash.client.services.models import (
    CalibrationPipelineSpec,
    CustomOneQubitStep,
    PipelineTargets,
)
from qdash.sdk import sweep

if TYPE_CHECKING:
    from pydantic import BaseModel

__all__ = [
    "CustomOneQubit",
    "MuxTargets",
    "OnFailure",
    "OneQubitExecutionMode",
    "Pipeline",
    "PipelineSpecInput",
    "QubitTargets",
    "Qubits",
    "TaskCall",
    "sweep",
    "to_spec",
]

# The generated models type these fields as enums and root models, which type checkers would
# demand instead of plain strings. The signatures below, seen only by type checkers, accept the
# strings; validation at run time stays the generated models'.
OneQubitExecutionMode = Literal[
    "parallel_by_round", "parallel_by_mux", "simultaneous_spectroscopy", "sequential", "manual"
]
OnFailure = Literal["continue", "stop"]


class TaskCall(models.TaskCall):
    """One call of a task in a step. ``call_id`` defaults to the task name."""

    if TYPE_CHECKING:

        def __init__(
            self,
            *,
            name: str,
            call_id: str | None = None,
            run: Mapping[str, Any] | None = None,
            input: Mapping[str, Any] | None = None,
            update_calibration_parameters: bool | None = None,
            on_failure: OnFailure | None = None,
        ) -> None: ...


class QubitTargets(PipelineTargets):
    """Explicit target qubits by the IDs QDash lists, e.g. ``QubitTargets(["0", "1"])``.

    Named after ``qdash.workflow``'s ``QubitTargets``; it serializes to ``{"qids": [...]}``.
    """

    def __init__(self, qids: Iterable[str]) -> None:
        if isinstance(qids, str):
            raise TypeError('QubitTargets takes a list of qubit IDs, e.g. QubitTargets(["0", "1"])')
        super().__init__(qids=list(qids))


Qubits = QubitTargets
"""The earlier name of :class:`QubitTargets`; the same class."""


class MuxTargets(PipelineTargets):
    """Every qubit of the given MUXes, e.g. ``MuxTargets([0, 1], exclude_qids=["5"])``.

    Named after ``qdash.workflow``'s ``MuxTargets``; it serializes to
    ``{"mux_ids": [...], "exclude_qids": [...]}``. The server resolves the MUXes to qubits
    from the chip topology.
    """

    def __init__(self, mux_ids: Iterable[int], *, exclude_qids: Iterable[str] = ()) -> None:
        for name, value in (("mux_ids", mux_ids), ("exclude_qids", exclude_qids)):
            if isinstance(value, str):
                raise TypeError(f"MuxTargets {name} must be a list, got {value!r}")
        excluded = list(exclude_qids)
        if excluded:
            super().__init__(mux_ids=list(mux_ids), exclude_qids=excluded)
        else:
            super().__init__(mux_ids=list(mux_ids))


class CustomOneQubit(CustomOneQubitStep):
    """A ``CustomOneQubit`` step: the given task calls, in order, on every candidate qubit."""

    type: Literal["CustomOneQubit"] = "CustomOneQubit"

    if TYPE_CHECKING:

        def __init__(
            self,
            *,
            tasks: Sequence[models.TaskCall | Mapping[str, Any]],
            step_name: str = ...,
            execution_mode: OneQubitExecutionMode = ...,
            rounds: Sequence[Sequence[str]] | None = None,
            continue_on_failure: bool = ...,
        ) -> None: ...


class Pipeline(CalibrationPipelineSpec):
    """A calibration pipeline spec, version 2."""

    spec_version: Literal[2] = 2

    if TYPE_CHECKING:

        def __init__(
            self,
            *,
            targets: PipelineTargets | Mapping[str, Any],
            steps: Sequence[BaseModel | Mapping[str, Any]],
            name: str = ...,
            default_run_parameters: Mapping[str, Any] | None = None,
            tags: Sequence[str] | None = None,
            spec_version: Literal[2] = 2,
        ) -> None: ...

    def to_spec(self) -> dict[str, Any]:
        """The spec as the JSON object the validate and execute routes accept."""
        return to_spec(self)


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
