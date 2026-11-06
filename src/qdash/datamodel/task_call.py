"""Task calls: one invocation of a calibration task inside a pipeline step.

A step runs an ordered list of :class:`TaskCall` entries on each of its targets.
The same task may appear several times in one step, for example a coarse and a
fine ``CheckRamsey`` with different run settings::

    from qdash.datamodel.task_call import TaskCall
    from qdash.workflow import sweep

    [
        TaskCall(name="CheckRamsey", call_id="ramsey_coarse",
                 run={"time_range": sweep.arange(0, 10_001, 100), "detuning": 0.001}),
        TaskCall(name="CheckRamsey", call_id="ramsey_fine",
                 run={"time_range": sweep.arange(0, 50_001, 500), "detuning": 0.0002}),
    ]

Identity has three levels, and none of them is an array index:

* ``step_id`` names a step within a plan (see ``qdash.workflow.service.steps``).
* ``call_id`` names a call within its step. It defaults to the task name, so a
  task that appears once needs no explicit id; every occurrence of a task that
  appears more than once must carry its own unique ``call_id``.
* ``task_id`` is the runtime id of one execution of a call on one target, as it
  is for every task result. A call that runs on four qubits has four task ids.

Settings precedence for one call, highest first: the call's own ``run`` /
``input`` / ``update_calibration_parameters``, the workflow's common per-task
defaults (``task_parameters`` keyed by task name), shared
``default_run_parameters``, then the task's declaration. A field that is absent
or ``None`` inherits from the next layer; it never resets a persistence policy.

``on_failure`` decides what happens to the same target's later calls in the step
when this call fails: ``"stop"`` skips them, ``"continue"`` runs them. ``None``
inherits the step's ``continue_on_failure``. The scope is one target: a failure on
qubit 0 never stops qubit 1.

The module only depends on ``qdash.datamodel`` so the API validates a declarative
pipeline spec with the same model the worker runs.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from qdash.datamodel.task_invocation import TaskInvocation
from qdash.datamodel.task_settings import (
    INPUT,
    RUN,
    UPDATE_CALIBRATION_PARAMETERS,
    merge_task_parameters,
    normalize_input_entries,
    normalize_run_entries,
)

__all__ = [
    "CALL_ID_PATTERN",
    "OnFailure",
    "StepCalls",
    "TaskCall",
    "TaskCallResult",
    "TaskInvocation",
    "TaskNameNotCallError",
    "TaskSettings",
    "normalize_calls",
    "plan_digest",
]

TASK_NAME_PATTERN = r"^[A-Za-z][A-Za-z0-9_]{0,127}$"
"""Task names are class-style identifiers such as ``CheckRamsey``."""

CALL_ID_PATTERN = r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$"
"""Call ids accept task names (``CheckRamsey``) as well as ``ramsey_fine``."""

OnFailure = Literal["continue", "stop"]

MIGRATION_HINT = (
    "Task lists take TaskCall entries since spec version 2, e.g. "
    'TaskCall(name="CheckRabi"). Convert saved flows with '
    "`python -m qdash.common.migration.task_calls <file.py>`; see "
    "docs/developer-guide/workflow/task-calls.md."
)


_RUN_DESCRIPTION = (
    "Run parameters. A plain value, "
    '{"value": ..., "value_type": ...}, or a sweep declaration '
    '{"value": [start, stop, step_or_num], "value_type": "np.arange" | '
    '"np.linspace" | "np.logspace" | "range"} or '
    '{"value": [points...], "value_type": "list"}.'
)
_INPUT_DESCRIPTION = "Calibration input overrides, as plain values."
_UPDATE_DESCRIPTION = (
    "False records outputs as measurement history only. None inherits the next "
    "layer and finally the workflow's policy."
)


def _run_or_none(value: Any) -> Any:
    return None if value is None else normalize_run_entries("run", value)


def _input_or_none(value: Any) -> Any:
    return None if value is None else normalize_input_entries("input", value)


def _settings_entry(
    run: Mapping[str, Any] | None,
    input_: Mapping[str, Any] | None,
    update_calibration_parameters: bool | None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {RUN: dict(run or {}), INPUT: dict(input_ or {})}
    if update_calibration_parameters is not None:
        entry[UPDATE_CALIBRATION_PARAMETERS] = update_calibration_parameters
    return entry


class TaskSettings(BaseModel):
    """Common per-task defaults: run parameters, input overrides, persistence policy.

    A workflow's ``task_parameters`` maps a task name to one of these; every call
    of that task starts from it. :class:`TaskCall` carries the same fields for one
    call.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    run: dict[str, Any] | None = Field(default=None, description=_RUN_DESCRIPTION)
    input: dict[str, Any] | None = Field(default=None, description=_INPUT_DESCRIPTION)
    update_calibration_parameters: bool | None = Field(
        default=None, description=_UPDATE_DESCRIPTION
    )

    _normalize_run = field_validator("run", mode="before")(_run_or_none)
    _normalize_input = field_validator("input", mode="before")(_input_or_none)

    def settings(self) -> dict[str, Any]:
        """These settings as one canonical ``task_parameters`` entry.

        ``update_calibration_parameters`` is only present when it is set, so the
        next layer still decides when it is ``None``.
        """
        return _settings_entry(self.run, self.input, self.update_calibration_parameters)


class TaskCall(BaseModel):
    """One call of a task in a step, with its own settings and identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(
        pattern=TASK_NAME_PATTERN,
        description='Registered task name, e.g. "CheckRamsey".',
    )
    call_id: str | None = Field(
        default=None,
        pattern=CALL_ID_PATTERN,
        description=(
            "Identifier of this call, unique within its step. Defaults to the task "
            "name; required on every occurrence of a task that appears more than once."
        ),
    )
    run: dict[str, Any] | None = Field(default=None, description=_RUN_DESCRIPTION)
    input: dict[str, Any] | None = Field(default=None, description=_INPUT_DESCRIPTION)
    update_calibration_parameters: bool | None = Field(
        default=None, description=_UPDATE_DESCRIPTION
    )
    on_failure: OnFailure | None = Field(
        default=None,
        description=(
            '"stop" skips this target\'s later calls in the step when this call fails; '
            '"continue" runs them. None inherits the step\'s continue_on_failure.'
        ),
    )

    _normalize_run = field_validator("run", mode="before")(_run_or_none)
    _normalize_input = field_validator("input", mode="before")(_input_or_none)

    def settings(self) -> dict[str, Any]:
        """This call's own settings as one canonical ``task_parameters`` entry."""
        return _settings_entry(self.run, self.input, self.update_calibration_parameters)

    @property
    def resolved_call_id(self) -> str:
        """The call id, or the task name when none was given."""
        return self.call_id or self.name

    def effective_settings(self, task_defaults: Mapping[str, Any] | None) -> dict[str, Any]:
        """This call's settings merged over the common per-task defaults."""
        defaults = (task_defaults or {}).get(self.name, {RUN: {}, INPUT: {}})
        return merge_task_parameters({self.name: defaults}, {self.name: self.settings()})[self.name]


class TaskNameNotCallError(ValueError, TypeError):
    """A task list entry is a plain task name instead of a TaskCall.

    A ValueError so a pydantic model reports it as a validation problem, and a
    TypeError for Python callers passing the wrong type.
    """


def _coerce_call(entry: Any, where: str) -> TaskCall:
    if isinstance(entry, TaskCall):
        return entry
    if isinstance(entry, str):
        raise TaskNameNotCallError(f"{where} is the task name {entry!r}; {MIGRATION_HINT}")
    if isinstance(entry, Mapping):
        return TaskCall.model_validate(entry)
    raise TaskNameNotCallError(f"{where} must be a TaskCall, got {type(entry).__name__}")


def normalize_calls(calls: Iterable[Any], *, where: str = "tasks") -> tuple[TaskCall, ...]:
    """Validate a step's calls and fill in default call ids.

    Rejects plain task names with migration guidance, a repeated task without an
    explicit ``call_id`` on every occurrence, and duplicate call ids (including a
    default id that collides with another call's explicit one).
    """
    coerced = [_coerce_call(entry, f"{where}[{index}]") for index, entry in enumerate(calls)]
    counts = Counter(call.name for call in coerced)
    problems: list[str] = []
    reported: set[str] = set()
    for name, count in counts.items():
        if count < 2:
            continue
        missing = [
            index for index, call in enumerate(coerced) if call.name == name and not call.call_id
        ]
        if missing:
            reported.add(name)
            positions = ", ".join(f"{where}[{index}]" for index in missing)
            problems.append(
                f"task {name!r} runs {count} times in this step; give every occurrence "
                f"its own call_id (missing at {positions})"
            )
    seen: dict[str, int] = {}
    for index, call in enumerate(coerced):
        call_id = call.resolved_call_id
        if call_id in seen and not (call.call_id is None and call.name in reported):
            problems.append(
                f"{where}[{index}] reuses call_id {call_id!r} of {where}[{seen[call_id]}]"
            )
        else:
            seen[call_id] = index
    if problems:
        raise ValueError("; ".join(problems))
    return tuple(
        call if call.call_id else call.model_copy(update={"call_id": call.name}) for call in coerced
    )


class StepCalls(BaseModel):
    """The normalized calls of one step, as handed to the workers that run them."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: str
    calls: tuple[TaskCall, ...]
    continue_on_failure: bool = False
    plan_digest: str | None = None

    def stops_after_failure(self, call: TaskCall) -> bool:
        """Whether a failure of ``call`` skips the target's later calls."""
        if call.on_failure is not None:
            return call.on_failure == "stop"
        return not self.continue_on_failure

    def task_names(self) -> list[str]:
        """Task names in call order, with repeats."""
        return [call.name for call in self.calls]

    def invocation(self, call: TaskCall) -> TaskInvocation:
        """The identity recorded on every task result of ``call``."""
        return TaskInvocation(
            step_id=self.step_id,
            call_id=call.resolved_call_id,
            plan_digest=self.plan_digest,
        )


class TaskCallResult(BaseModel):
    """What one call did on one target, in call order within the step."""

    model_config = ConfigDict(extra="allow")

    call_id: str
    name: str
    status: Literal["success", "failed", "skipped"]
    task_id: str | None = None
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    reason: str | None = None


def plan_digest(plan: Mapping[str, Any]) -> str:
    """A stable short digest of a JSON-compatible plan, used as its version."""
    encoded = json.dumps(plan, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()[:16]


def calls_json(calls: Sequence[TaskCall]) -> list[dict[str, Any]]:
    """Calls as JSON, omitting unset fields."""
    return [call.model_dump(mode="json", exclude_none=True) for call in calls]
