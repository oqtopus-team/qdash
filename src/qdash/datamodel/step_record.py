"""What a pipeline step records in its own Execution's note.

Every step a run reaches is one Execution. Its note names the step with these keys, next to
the run identity and plan the pipeline writes on every step:

- ``step_index``: 1-based position in the run's plan.
- ``step_key``: the step occurrence's identifier in the plan (see :func:`step_keys`).
- ``step_kind``: ``"calibration"`` for a step that measures, ``"transform"`` for one that only
  selects or plans (``FilterByStatus``, ``FilterByMetric``, ``GenerateCRSchedule``).
- ``step_type``: the step's class name.
- ``step_id``: a calibration step's plan-scoped ``step_id`` (filters reference it); transforms
  have none.

A transform step also records its outcome under ``transform_result``
(:class:`TransformStepRecord`). Executions recorded before transforms had their own
Execution carry none of the ``step_kind``, ``step_key`` or ``transform_result`` keys; nothing
is inferred for them.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "NOTE_STEP_KEY",
    "NOTE_STEP_KIND",
    "NOTE_STEP_TYPE",
    "NOTE_TRANSFORM_RESULT",
    "PLAN_RECORDS_TRANSFORMS",
    "ExcludedTarget",
    "TransformStepRecord",
    "read_transform_record",
    "step_keys",
]

NOTE_STEP_KEY = "step_key"
NOTE_STEP_KIND = "step_kind"
NOTE_STEP_TYPE = "step_type"
NOTE_TRANSFORM_RESULT = "transform_result"
PLAN_RECORDS_TRANSFORMS = "records_transform_steps"
"""Key of ``note.pipeline`` set by workers that record every transform in an Execution.

A plan without it comes from a run recorded before then: its transforms have no
Execution, and a reader must not report them as pending or failed.
"""

TransformKind = Literal["filter", "cr_schedule", "transform"]


class ExcludedTarget(BaseModel):
    """A candidate a filter left out, and why."""

    model_config = ConfigDict(extra="ignore")

    target: str = Field(description="Qubit ID the filter removed from the candidates")
    reason: str = Field(description="Why it did not pass, read from the source result")


class TransformStepRecord(BaseModel):
    """The outcome of one transform step, copied when the step ended.

    Lists are snapshots: later steps never change a recorded outcome. Fields that do not
    apply to a kind stay at their defaults (``None`` or empty).
    """

    model_config = ConfigDict(extra="ignore")

    kind: TransformKind = Field(
        description='"filter", "cr_schedule", or "transform" for a custom transform step'
    )
    input_qids: list[str] = Field(default_factory=list, description="Candidates before the step")
    output_qids: list[str] = Field(default_factory=list, description="Candidates after the step")
    input_couplings: list[str] = Field(
        default_factory=list, description="Candidate couplings before the step"
    )
    output_couplings: list[str] = Field(
        default_factory=list, description="Candidate couplings after the step"
    )
    excluded: list[ExcludedTarget] = Field(
        default_factory=list, description="Filters: each removed candidate with its reason"
    )
    criteria: str | None = Field(default=None, description="Filters: the condition applied")
    source_step: str | None = Field(
        default=None, description="Filters: step_id read; null for the latest one-qubit result"
    )
    source_call_id: str | None = Field(default=None, description="Filters: call_id read")
    metric: str | None = Field(default=None, description="FilterByMetric: the metric compared")
    threshold: float | None = Field(default=None, description="FilterByMetric: minimum kept")
    source_found: bool | None = Field(
        default=None,
        description=(
            "Filters: false when no one-qubit result existed, so every candidate was kept "
            "unfiltered"
        ),
    )
    groups: list[list[str]] | None = Field(
        default=None,
        description="cr_schedule: parallel groups of control-target couplings, in order",
    )
    max_parallel_ops: int | None = Field(default=None, description="cr_schedule: group cap")
    direction: str | None = Field(
        default=None, description='cr_schedule: "forward", "reverse" or "as listed"'
    )
    message: str | None = Field(
        default=None, description="Why the step produced nothing, when it did not"
    )


def read_transform_record(note: dict[str, Any] | None) -> TransformStepRecord | None:
    """The transform outcome in an Execution note, or None when absent or unreadable."""
    raw = (note or {}).get(NOTE_TRANSFORM_RESULT)
    if not isinstance(raw, dict):
        return None
    try:
        return TransformStepRecord.model_validate(raw)
    except ValidationError:
        return None


def step_keys(steps: Sequence[tuple[str, str | None]]) -> list[str]:
    """The identifier of each step occurrence of one plan, in plan order.

    ``steps`` lists each step's ``(name, step_id)``; transforms have no ``step_id``. A
    calibration step is identified by its ``step_id``, which a plan keeps unique. A transform
    is identified by its name when no other step uses it, else by ``<name>_<index>`` with its
    1-based position, so repeated filters stay apart. The keys depend on the plan alone.
    """
    reserved = {step_id for _, step_id in steps if step_id}
    repeats = Counter(name for name, step_id in steps if not step_id)
    used = set(reserved)
    keys: list[str] = []
    for index, (name, step_id) in enumerate(steps, start=1):
        if step_id:
            keys.append(step_id)
            continue
        key = name if repeats[name] == 1 and name not in reserved else f"{name}_{index}"
        while key in used:
            key = f"{key}_{index}"
        used.add(key)
        keys.append(key)
    return keys
