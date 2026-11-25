"""Built-in calibration steps, in the form both the SDK and the worker accept.

Every class mirrors one step type of the pipeline spec (version 2) field for field, with the
same defaults, and serializes with :meth:`ExecutionStep.to_spec` to that step's JSON
with only the fields that were set. The SDK sends that JSON to the server; the worker validates
the same JSON with the server's model and builds its runtime step from it, so a step written
here runs the same way from a script and from a saved workflow.

Checks that need the chip, the task catalog or the whole pipeline (task names, call ID
uniqueness, step order, manual round layout) are made by the server when validating, and by
the worker before anything is reserved.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from qdash.calibration._task_call import CALL_ID_PATTERN, TaskCall

__all__ = [
    "DEFAULT_MAX_PARALLEL_OPS",
    "STEP_ID_PATTERN",
    "BringUp",
    "CalibrationStepDefinition",
    "ConfigureAll",
    "CustomOneQubit",
    "CustomTwoQubit",
    "ExecutionStep",
    "FilterByMetric",
    "FilterByStatus",
    "GenerateCRSchedule",
    "OneQubitCheck",
    "OneQubitExecutionMode",
    "OneQubitFineTune",
    "OneQubitStepExecutionMode",
    "TwoQubitCalibration",
    "TwoQubitExecutionMode",
]

STEP_ID_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"

OneQubitExecutionMode = Literal[
    "parallel_by_round", "parallel_by_mux", "simultaneous_spectroscopy", "sequential"
]
"""Modes of ``BringUp``; it has no manual rounds."""

OneQubitStepExecutionMode = Literal[
    "parallel_by_round", "parallel_by_mux", "simultaneous_spectroscopy", "sequential", "manual"
]
"""Modes of ``OneQubitCheck``, ``OneQubitFineTune`` and ``CustomOneQubit``."""

TwoQubitExecutionMode = Literal["automatic", "manual"]

DEFAULT_MAX_PARALLEL_OPS = 10
"""Pairs per automatically generated CR group when ``max_parallel_ops`` is unset."""


def _calls(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str) or not isinstance(value, Iterable):
        raise ValueError("tasks must be a list of TaskCall entries")
    calls = []
    for index, entry in enumerate(value):
        if isinstance(entry, str):
            raise ValueError(
                f"tasks[{index}] is the task name {entry!r}; wrap it as TaskCall(name={entry!r})"
            )
        if isinstance(entry, TaskCall) and type(entry) is not TaskCall:
            # The worker's validated subclass, or another TaskCall subclass: keep what was set.
            calls.append(TaskCall.model_validate(entry.model_dump(exclude_unset=True)))
        else:
            calls.append(entry)
    return calls


class ExecutionStep(BaseModel):
    """Base of the built-in step definitions; each step that a run reaches is one Execution.

    A run records every step it reaches, measurement or not, in its own Execution in the
    step's order: calibration steps with their task results, ``FilterByStatus`` and
    ``FilterByMetric`` with the candidates they kept and why each excluded one was left out,
    and ``GenerateCRSchedule`` with the groups it planned. A step the run never reaches has
    no Execution. Building a definition is pure: it reads nothing and runs nothing.
    """

    model_config = ConfigDict(extra="forbid")

    type: ClassVar[str]

    def to_spec(self) -> dict[str, Any]:
        """The step as the pipeline spec's JSON, with only the fields that were set."""
        return {"type": self.type, **self.model_dump(mode="json", exclude_unset=True)}


def _check_qubit_rounds(mode: str, rounds: Sequence[Sequence[str]] | None, step: str) -> None:
    if mode == "manual" and rounds is None:
        raise ValueError(f"{step}: execution_mode 'manual' needs rounds")
    if mode != "manual" and rounds is not None:
        raise ValueError(f"{step}: rounds need execution_mode 'manual'")


def _check_pair_rounds(
    mode: str, rounds: Sequence[Any] | None, max_parallel_ops: int | None, step: str
) -> None:
    _check_qubit_rounds(mode, rounds, step)
    if mode == "manual" and max_parallel_ops is not None:
        raise ValueError(
            f"{step}: max_parallel_ops only caps automatic groups; remove it with manual rounds"
        )


class ConfigureAll(ExecutionStep):
    """Configure every box of the targeted MUXes once."""

    type: ClassVar[str] = "ConfigureAll"

    step_id: str | None = Field(default=None, pattern=STEP_ID_PATTERN)
    mux_ids: list[int] | None = None
    call: TaskCall | None = None

    @field_validator("call")
    @classmethod
    def _configure_all(cls, value: TaskCall | None) -> TaskCall | None:
        if value is not None and value.name != "ConfigureAll":
            raise ValueError(
                f"a ConfigureAll step's call must name ConfigureAll, got {value.name!r}"
            )
        return value


class BringUp(ExecutionStep):
    """Initial characterization: spectroscopy and chevron per MUX and qubit.

    ``tasks`` defaults to the bring-up task calls; ``execution_mode`` applies to MUX targets.
    """

    type: ClassVar[str] = "BringUp"

    step_id: str | None = Field(default=None, pattern=STEP_ID_PATTERN)
    tasks: list[TaskCall] | None = None
    execution_mode: OneQubitExecutionMode = "parallel_by_mux"

    _normalize_tasks = field_validator("tasks", mode="before")(_calls)


class _OneQubitStep(ExecutionStep):
    step_id: str | None = Field(default=None, pattern=STEP_ID_PATTERN)
    execution_mode: OneQubitStepExecutionMode = "parallel_by_round"
    rounds: list[list[str]] | None = None
    tasks: list[TaskCall] | None = None
    configure: bool = False

    _normalize_tasks = field_validator("tasks", mode="before")(_calls)

    @model_validator(mode="after")
    def _rounds(self) -> _OneQubitStep:
        _check_qubit_rounds(self.execution_mode, self.rounds, self.type)
        return self


class OneQubitCheck(_OneQubitStep):
    """Coarse one-qubit characterization; ``tasks`` defaults to Rabi, HPI and PI pulses."""

    type: ClassVar[str] = "OneQubitCheck"


class OneQubitFineTune(_OneQubitStep):
    """Fine one-qubit calibration and benchmarking; ``tasks`` defaults to the full list."""

    type: ClassVar[str] = "OneQubitFineTune"


class CustomOneQubit(ExecutionStep):
    """The given task calls, in order, on every candidate qubit."""

    type: ClassVar[str] = "CustomOneQubit"

    step_name: str = Field(default="custom_one_qubit", pattern=STEP_ID_PATTERN)
    tasks: list[TaskCall] = Field(min_length=1)
    execution_mode: OneQubitStepExecutionMode = "parallel_by_round"
    rounds: list[list[str]] | None = None
    continue_on_failure: bool = False

    _normalize_tasks = field_validator("tasks", mode="before")(_calls)

    @model_validator(mode="after")
    def _rounds(self) -> CustomOneQubit:
        _check_qubit_rounds(self.execution_mode, self.rounds, self.step_name)
        return self


class _FilterReference(ExecutionStep):
    step: str | None = Field(default=None, pattern=STEP_ID_PATTERN)
    call_id: str | None = Field(default=None, pattern=CALL_ID_PATTERN)

    @model_validator(mode="after")
    def _call_needs_step(self) -> _FilterReference:
        if self.call_id is not None and self.step is None:
            raise ValueError(f"{self.type}: call_id requires step")
        return self


class FilterByStatus(_FilterReference):
    """Keep only the qubits whose referenced step or call succeeded."""

    type: ClassVar[str] = "FilterByStatus"


class FilterByMetric(_FilterReference):
    """Keep only the qubits whose metric meets ``threshold`` (``metric >= threshold``)."""

    type: ClassVar[str] = "FilterByMetric"

    metric: str = Field(min_length=1)
    threshold: float


class GenerateCRSchedule(ExecutionStep):
    """Plan parallel cross-resonance groups for the candidate qubits."""

    type: ClassVar[str] = "GenerateCRSchedule"

    max_parallel_ops: int = Field(default=DEFAULT_MAX_PARALLEL_OPS, ge=1, le=100)
    inverse: bool = False


def _pair_rounds(value: Any) -> Any:
    if value is None:
        return None
    return [[tuple(pair) for pair in round_] for round_ in value]


class _TwoQubitStep(ExecutionStep):
    execution_mode: TwoQubitExecutionMode = "automatic"
    rounds: list[list[tuple[str, str]]] | None = None
    max_parallel_ops: int | None = Field(default=None, ge=1, le=100)

    _normalize_rounds = field_validator("rounds", mode="before")(_pair_rounds)

    def _check(self, step: str) -> None:
        _check_pair_rounds(self.execution_mode, self.rounds, self.max_parallel_ops, step)


class TwoQubitCalibration(_TwoQubitStep):
    """Full coupling calibration; ``tasks`` defaults to the full two-qubit list.

    ``execution_mode="automatic"`` (the default) runs an earlier ``GenerateCRSchedule`` or
    groups the candidates itself, capped by ``max_parallel_ops``; ``"manual"`` runs the
    directed ``(control, target)`` pairs of ``rounds`` exactly as written.
    """

    type: ClassVar[str] = "TwoQubitCalibration"

    step_id: str | None = Field(default=None, pattern=STEP_ID_PATTERN)
    tasks: list[TaskCall] | None = None

    _normalize_tasks = field_validator("tasks", mode="before")(_calls)

    @model_validator(mode="after")
    def _rounds(self) -> TwoQubitCalibration:
        self._check(self.type)
        return self


class CustomTwoQubit(_TwoQubitStep):
    """The given task calls, in order, on every candidate coupling; modes as
    :class:`TwoQubitCalibration`."""

    type: ClassVar[str] = "CustomTwoQubit"

    step_name: str = Field(default="custom_two_qubit", pattern=STEP_ID_PATTERN)
    tasks: list[TaskCall] = Field(min_length=1)
    continue_on_failure: bool = False

    _normalize_tasks = field_validator("tasks", mode="before")(_calls)

    @model_validator(mode="after")
    def _rounds(self) -> CustomTwoQubit:
        self._check(self.step_name)
        return self


CalibrationStepDefinition = ExecutionStep
"""Earlier name of :class:`ExecutionStep`, kept for existing imports and ``isinstance`` checks."""

STEP_TYPES: dict[str, type[ExecutionStep]] = {
    cls.type: cls
    for cls in (
        ConfigureAll,
        BringUp,
        OneQubitCheck,
        OneQubitFineTune,
        CustomOneQubit,
        FilterByStatus,
        FilterByMetric,
        GenerateCRSchedule,
        TwoQubitCalibration,
        CustomTwoQubit,
    )
}
"""Every built-in step definition by its spec ``type``."""
