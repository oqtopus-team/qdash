"""Turning :mod:`qdash.calibration` definitions into the worker's runtime targets and steps.

A definition is serialized to the pipeline spec's JSON, validated with the server's spec
model and built by :func:`~qdash.workflow.service.pipeline_flow.build_step`, exactly as a
spec the SDK sent is, so a definition means the same thing in a script and in a workflow.

Runtime targets and steps (``qdash.workflow.service.targets``, ``qdash.workflow.service.steps``,
and custom ``Step`` subclasses) pass through unchanged: that is the worker-only path for
custom steps and for saved flows written before the shared definitions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from pydantic import TypeAdapter

from qdash.calibration import (
    CalibrationTargets,
    ExecutionStep,
    TaskCall,
    step_spec,
    targets_spec,
)
from qdash.datamodel.calibration_pipeline import PipelineStep, PipelineTargets
from qdash.datamodel.task_call import worker_call

if TYPE_CHECKING:
    from qdash.workflow.service.steps.base import Step
    from qdash.workflow.service.targets import Target

__all__ = ["runtime_steps", "runtime_target"]

_STEP_ADAPTER: TypeAdapter[Any] = TypeAdapter(PipelineStep)


def runtime_target(targets: Any) -> Target:
    """The runtime target of a definition, a spec mapping, or a runtime target as it is."""
    from qdash.workflow.service.pipeline_flow import build_target
    from qdash.workflow.service.targets import Target

    if isinstance(targets, Target):
        return targets
    if isinstance(targets, CalibrationTargets | Mapping):
        return build_target(PipelineTargets.model_validate(targets_spec(targets)))
    raise TypeError(
        "targets must be QubitTargets, MuxTargets or CouplingTargets from qdash.calibration, "
        f"got {type(targets).__name__}"
    )


def _worker_value(value: Any) -> Any:
    if isinstance(value, TaskCall):
        return worker_call(value)
    if isinstance(value, list):
        return [_worker_value(item) for item in value]
    return value


def runtime_step(step: Any, index: int) -> Step:
    """The runtime step of one definition or spec mapping; a runtime step as it is."""
    from qdash.workflow.service.pipeline_flow import build_step
    from qdash.workflow.service.steps.base import Step

    if isinstance(step, Step):
        return step
    if isinstance(step, ExecutionStep | Mapping):
        # The fields that were set, as written: calls become the worker's validated calls
        # with their sweeps, as a runtime step receives them; the fields and defaults are
        # those of the JSON the SDK sends.
        data = (
            {
                "type": step.type,
                **{name: _worker_value(getattr(step, name)) for name in step.model_fields_set},
            }
            if isinstance(step, ExecutionStep)
            else step_spec(step)
        )
        try:
            validated = _STEP_ADAPTER.validate_python(data)
        except ValueError as exc:
            raise ValueError(f"steps[{index}]: {exc}") from exc
        return build_step(validated)
    raise TypeError(
        f"steps[{index}] must be a step from qdash.calibration, got {type(step).__name__}"
    )


def runtime_steps(steps: Sequence[Any]) -> list[Step]:
    """The runtime steps of a list of definitions, spec mappings and runtime steps."""
    if isinstance(steps, str | bytes) or not isinstance(steps, Sequence):
        raise TypeError("steps must be a list of steps")
    return [runtime_step(step, index) for index, step in enumerate(steps)]
