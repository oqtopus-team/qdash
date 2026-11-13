"""Declarative calibration pipeline specification, version 2.

A pipeline spec is what an agent (or a user) writes to run a calibration
without authoring a Python flow: targets, an ordered list of steps, and the
settings of every task call. Every step maps onto one of the Step classes in
``qdash.workflow.service.steps``; the spec cannot reference anything else, so
the handshake between the API (which validates and dispatches) and the worker
(which builds the Step objects) is this module alone.

Version 2 lists :class:`~qdash.datamodel.task_call.TaskCall` entries instead of
task names, so one step can run the same task several times with different
settings. Each calibration step has a ``step_id`` unique within the pipeline and
each call a ``call_id`` unique within its step; filters reference them to select
exactly one step or call. :func:`migrate_pipeline_spec` converts a version 1 spec.

The module stays free of workflow imports so the API process, which has no
Prefect runtime, can validate a spec. ``STEP_CATALOG`` therefore restates each
Step class's ``requires`` / ``provides``; ``tests/qdash/workflow`` asserts the
two agree.
"""

from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)

from qdash.common.manual_rounds import (
    PairRounds,
    QubitRounds,
    pair_rounds_for_mode,
    qubit_rounds_for_mode,
)

# Runtime imports: Pydantic validates execution_mode against these Literals.
from qdash.datamodel.one_qubit_execution_mode import OneQubitStepExecutionMode  # noqa: TC001
from qdash.datamodel.task_call import (
    CALL_ID_PATTERN,
    TaskCall,
    TaskSettings,
    calls_json,
    normalize_calls,
    plan_digest,
)
from qdash.datamodel.task_settings import task_parameters_from_run_parameters
from qdash.datamodel.two_qubit_execution_mode import TwoQubitExecutionMode  # noqa: TC001

SPEC_VERSION = 2

STEP_ID_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"

# ---------------------------------------------------------------------------
# Default task calls
# ---------------------------------------------------------------------------
# These are the standard call sequences the workflow templates build on.
# ``qdash.workflow.service.tasks`` re-exports them; keep the single copy here so
# both the worker and the API resolve a step's effective calls identically.

BRINGUP_TASKS: list[TaskCall] = [
    TaskCall(name="CheckResonatorSpectroscopy"),  # MUX-level: estimates readout_frequency
    TaskCall(name="CheckQubitSpectroscopy"),  # coarse_qubit_frequency, coarse_control_amplitude
    TaskCall(name="CheckControlAmplitude"),  # Refine coarse_control_amplitude from the seed
    TaskCall(name="CheckAdaptiveChevron"),
]

# Coarse one-qubit calibration: Rabi, then the HPI and PI pulses. DRAG pulses
# and coherence checks are their own steps so a pipeline can filter first.
CHECK_1Q_TASKS: list[TaskCall] = [
    TaskCall(name="CheckRabi"),
    TaskCall(name="CreateHPIPulse"),
    TaskCall(name="CreatePIPulse"),
]

FULL_1Q_TASKS_AFTER_CHECK: list[TaskCall] = [
    TaskCall(name="CheckRabi"),
    TaskCall(name="CreateHPIPulse"),
    TaskCall(name="CheckHPIPulse"),
    TaskCall(name="CreatePIPulse"),
    TaskCall(name="CheckPIPulse"),
    TaskCall(name="CreateDRAGHPIPulse"),
    TaskCall(name="CheckDRAGHPIPulse"),
    TaskCall(name="CreateDRAGPIPulse"),
    TaskCall(name="CheckDRAGPIPulse"),
    TaskCall(name="ReadoutClassification"),
    TaskCall(name="CheckT1Average"),
    TaskCall(name="CheckT2EchoAverage"),
    TaskCall(name="Check1QGateCoherenceLimit"),
    TaskCall(name="RandomizedBenchmarking"),
    TaskCall(name="X90InterleavedRandomizedBenchmarking"),
]

# The check pass and the full pass both run Rabi and the HPI/PI pulse creation,
# so one list holding both names every occurrence of those tasks.
_REPEATED_IN_FULL_1Q = {
    "CheckRabi": ("rabi_check", "rabi"),
    "CreateHPIPulse": ("hpi_pulse_check", "hpi_pulse"),
    "CreatePIPulse": ("pi_pulse_check", "pi_pulse"),
}
FULL_1Q_TASKS: list[TaskCall] = [
    *(
        TaskCall(name=call.name, call_id=_REPEATED_IN_FULL_1Q[call.name][0])
        for call in CHECK_1Q_TASKS
    ),
    *(
        TaskCall(name=call.name, call_id=_REPEATED_IN_FULL_1Q[call.name][1])
        if call.name in _REPEATED_IN_FULL_1Q
        else call
        for call in FULL_1Q_TASKS_AFTER_CHECK
    ),
]

FULL_2Q_TASKS: list[TaskCall] = [
    TaskCall(name="CheckCrossResonance"),
    TaskCall(name="CreateZX90"),
    TaskCall(name="CheckZX90"),
    TaskCall(name="CheckBellState"),
    TaskCall(name="CheckBellStateTomography"),
    TaskCall(name="Check2QGateCoherenceLimit"),
    TaskCall(name="ZX90InterleavedRandomizedBenchmarking"),
]

CONFIGURE_CALL = TaskCall(name="Configure")

CONFIGURE_ALL_CALL = TaskCall(name="ConfigureAll")


def configure_all_call(call: TaskCall | None) -> TaskCall:
    """The single call a ConfigureAll step runs, with its call_id filled in.

    ``None`` means the default call without settings of its own. An explicit call
    must name the ConfigureAll task; its ``run.mux_ids`` is replaced at run time
    by the step's MUXes, which come from the step's ``mux_ids`` or its targets.
    """
    chosen = CONFIGURE_ALL_CALL if call is None else call
    if chosen.name != CONFIGURE_ALL_CALL.name:
        raise ValueError(
            f"a ConfigureAll step's call must name {CONFIGURE_ALL_CALL.name}, got {chosen.name!r}"
        )
    return chosen.model_copy(update={"call_id": chosen.resolved_call_id})


def calls_with_configure(
    calls: Sequence[Any], *, configure: bool, where: str = "tasks"
) -> tuple[TaskCall, ...]:
    """A one-qubit step's calls, with the Configure call ``configure=True`` prepends.

    The prepended call has call_id ``Configure``. A step that also lists a
    Configure call, or another call with that call_id, is rejected rather than
    renamed, so a call_id never depends on the ``configure`` flag. Paths in the
    error refer to the step's own ``tasks`` list.
    """
    own = normalize_calls(calls, where=where)
    if not configure:
        return own
    implicit = CONFIGURE_CALL.model_copy(update={"call_id": CONFIGURE_CALL.name})
    conflicts = [
        f"{where}[{index}]"
        for index, call in enumerate(own)
        if call.name == implicit.name or call.resolved_call_id == implicit.call_id
    ]
    if conflicts:
        raise ValueError(
            f"configure=True already runs Configure first with call_id {implicit.call_id!r}; "
            f"remove configure or the conflicting call at {', '.join(conflicts)}"
        )
    return (implicit, *own)


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------


class PipelineTargets(BaseModel):
    """Which qubits the pipeline starts from: explicit qids or whole MUXes."""

    model_config = ConfigDict(extra="forbid")

    qids: list[str] | None = Field(
        default=None, description='Qubit ids as QDash lists them, e.g. ["0", "1"].'
    )
    mux_ids: list[int] | None = Field(
        default=None, description="MUX ids; every qubit of each MUX is a target."
    )
    exclude_qids: list[str] = Field(
        default_factory=list, description="Qubits to leave out of the MUX targets."
    )

    @model_validator(mode="after")
    def _exactly_one_kind(self) -> PipelineTargets:
        has_qids = bool(self.qids)
        has_mux = bool(self.mux_ids)
        if has_qids == has_mux:
            raise ValueError(
                "targets need exactly one of qids or mux_ids, and it must not be empty"
            )
        if has_qids and self.exclude_qids:
            raise ValueError("exclude_qids only applies to mux_ids targets")
        if self.qids is not None and len(set(self.qids)) != len(self.qids):
            raise ValueError("qids contains duplicates")
        if self.mux_ids is not None and len(set(self.mux_ids)) != len(self.mux_ids):
            raise ValueError("mux_ids contains duplicates")
        return self


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


class _StepBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _calls_or_none(value: Any) -> Any:
    if value is None:
        return None
    return list(normalize_calls(value))


def _calls(value: Any) -> Any:
    return list(normalize_calls(value))


_EXECUTION_MODE_DESCRIPTION = (
    "Where and when the step's targets run; every target runs the step's full task list. "
    "parallel_by_round: the scheduler selects rounds of qubits from different MUXes and "
    "the next round starts after every qubit of the current round finishes. "
    "parallel_by_mux: MUXes run in parallel and the qubits of one MUX run one after "
    "another, each MUX advancing independently. sequential: one MUX and one qubit at a time. "
    "simultaneous_spectroscopy: experimental batch spectroscopy. "
    "manual: run the rounds listed in `rounds` exactly as written."
)
_QUBIT_ROUNDS_DESCRIPTION = (
    "Required with execution_mode manual and rejected otherwise: the rounds in run order, "
    'each a list of qubit IDs, e.g. [["0", "8"], ["1", "9"]]. The qubits of a round run in '
    "parallel and the next round starts after all of them finish. A qubit appears in one "
    "round only, the qubits of a round use different MUXes, and the rounds must name exactly "
    "the step's current qubits; nothing is regrouped, reordered or dropped."
)
_PAIR_ROUNDS_DESCRIPTION = (
    "Required with execution_mode manual and rejected otherwise: the rounds in run order, "
    'each a list of directed [control, target] pairs, e.g. [[["0", "1"], ["4", "5"]], '
    '[["8", "9"]]]. Each pair must be a chip coupling in that direction, the pairs of a round '
    "may not share a qubit, a MUX or a modeled readout/control module, and both qubits of "
    "every pair must be current candidates. Rounds are never regrouped, reversed or split."
)
_TWO_QUBIT_MODE_DESCRIPTION = (
    "automatic (default): run an earlier GenerateCRSchedule/SetCRSchedule schedule or generate "
    "one from the candidate qubits. manual: run the pairs listed in `rounds` exactly as written."
)
_MAX_PARALLEL_OPS_DESCRIPTION = (
    "Pairs per automatically generated CR group. Rejected with execution_mode manual."
)

QubitIdPair = Annotated[list[str], Field(min_length=2, max_length=2)]


def _check_qubit_rounds(step: Any) -> Any:
    qubit_rounds_for_mode(step.execution_mode, step.rounds, step=step_name(step))
    return step


def _check_pair_rounds(step: Any) -> Any:
    explicit_cap = step.max_parallel_ops if "max_parallel_ops" in step.model_fields_set else None
    pair_rounds_for_mode(step.execution_mode, step.rounds, explicit_cap, step=step_name(step))
    return step


def _check_configure_call(step: Any) -> Any:
    # Resolve the complete call list here so a conflicting implicit Configure
    # call is a validation problem of this step, not an error at plan time.
    step_calls(step)
    return step


_STEP_ID_DESCRIPTION = (
    "Identifier of this step, unique within the pipeline; filters reference it. "
    "Defaults to the step's name. Set it when a pipeline runs the same step type twice."
)
_TASKS_DESCRIPTION = (
    "Task calls to run on every target, in order. A task may appear more than once "
    "when each occurrence has its own call_id."
)
_CONTINUE_DESCRIPTION = (
    "Run a target's later calls after one of its calls fails. A call's on_failure "
    "overrides this for that call."
)


class ConfigureAllStep(_StepBase):
    """Configure every box of the targeted MUXes once."""

    type: Literal["ConfigureAll"]
    step_id: str | None = Field(default=None, pattern=STEP_ID_PATTERN)
    mux_ids: list[int] | None = Field(
        default=None, description="MUXes to configure; defaults to the targets' MUXes."
    )
    # Omitted from dumps when unset so a spec without it keeps its plan digest.
    call: TaskCall | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description=(
            "Settings of the ConfigureAll call, e.g. "
            '{"name": "ConfigureAll", "run": {"configuration_mode": "ge-ef-cr"}}. '
            "Its name must be ConfigureAll. The step's mux_ids, or the targets' MUXes, "
            "replace any run.mux_ids. Defaults to a call without settings of its own."
        ),
    )

    @field_validator("call")
    @classmethod
    def _check_call(cls, value: TaskCall | None) -> TaskCall | None:
        """Reject a call that names another task, as a problem at ``steps[i].call``."""
        if value is not None:
            configure_all_call(value)
        return value


class BringUpStep(_StepBase):
    """Initial characterization: resonator and qubit spectroscopy, chevron."""

    type: Literal["BringUp"]
    step_id: str | None = Field(
        default=None, pattern=STEP_ID_PATTERN, description=_STEP_ID_DESCRIPTION
    )
    tasks: list[TaskCall] | None = Field(
        default=None, description=_TASKS_DESCRIPTION + " Defaults to BRINGUP_TASKS."
    )

    _normalize_tasks = field_validator("tasks", mode="before")(_calls_or_none)


class OneQubitCheckStep(_StepBase):
    """Coarse one-qubit characterization (Rabi, HPI, PI pulses)."""

    type: Literal["OneQubitCheck"]
    step_id: str | None = Field(
        default=None, pattern=STEP_ID_PATTERN, description=_STEP_ID_DESCRIPTION
    )
    execution_mode: OneQubitStepExecutionMode = Field(
        default="parallel_by_round", description=_EXECUTION_MODE_DESCRIPTION
    )
    # Omitted from dumps when unset so specs without it keep their plan digest.
    rounds: list[list[str]] | None = Field(
        default=None, exclude_if=lambda value: value is None, description=_QUBIT_ROUNDS_DESCRIPTION
    )
    tasks: list[TaskCall] | None = Field(
        default=None, description=_TASKS_DESCRIPTION + " Defaults to CHECK_1Q_TASKS."
    )
    configure: bool = Field(default=False, description="Run Configure before the first task.")

    _normalize_tasks = field_validator("tasks", mode="before")(_calls_or_none)
    _check_configure = model_validator(mode="after")(_check_configure_call)
    _check_rounds = model_validator(mode="after")(_check_qubit_rounds)


class OneQubitFineTuneStep(_StepBase):
    """Fine one-qubit calibration (DRAG, readout classification, benchmarking)."""

    type: Literal["OneQubitFineTune"]
    step_id: str | None = Field(
        default=None, pattern=STEP_ID_PATTERN, description=_STEP_ID_DESCRIPTION
    )
    execution_mode: OneQubitStepExecutionMode = Field(
        default="parallel_by_round", description=_EXECUTION_MODE_DESCRIPTION
    )
    # Omitted from dumps when unset so specs without it keep their plan digest.
    rounds: list[list[str]] | None = Field(
        default=None, exclude_if=lambda value: value is None, description=_QUBIT_ROUNDS_DESCRIPTION
    )
    tasks: list[TaskCall] | None = Field(
        default=None,
        description=_TASKS_DESCRIPTION + " Defaults to FULL_1Q_TASKS_AFTER_CHECK.",
    )
    configure: bool = Field(default=False, description="Run Configure before the first task.")

    _normalize_tasks = field_validator("tasks", mode="before")(_calls_or_none)
    _check_configure = model_validator(mode="after")(_check_configure_call)
    _check_rounds = model_validator(mode="after")(_check_qubit_rounds)


class CustomOneQubitStep(_StepBase):
    """Any sequence of qubit task calls on the current candidate qubits."""

    type: Literal["CustomOneQubit"]
    step_name: str = Field(
        default="custom_one_qubit",
        pattern=STEP_ID_PATTERN,
        description="Name and step_id of this step; unique within the pipeline.",
    )
    tasks: list[TaskCall] = Field(min_length=1, description=_TASKS_DESCRIPTION)
    execution_mode: OneQubitStepExecutionMode = Field(
        default="parallel_by_round", description=_EXECUTION_MODE_DESCRIPTION
    )
    # Omitted from dumps when unset so specs without it keep their plan digest.
    rounds: list[list[str]] | None = Field(
        default=None, exclude_if=lambda value: value is None, description=_QUBIT_ROUNDS_DESCRIPTION
    )
    continue_on_failure: bool = Field(default=False, description=_CONTINUE_DESCRIPTION)

    _normalize_tasks = field_validator("tasks", mode="before")(_calls)
    _check_rounds = model_validator(mode="after")(_check_qubit_rounds)


class _FilterReference(_StepBase):
    step: str | None = Field(
        default=None,
        pattern=STEP_ID_PATTERN,
        description=(
            "step_id of an earlier one-qubit step to read. Omitted: the latest of "
            "OneQubitFineTune and OneQubitCheck, as in version 1."
        ),
    )
    call_id: str | None = Field(
        default=None,
        pattern=CALL_ID_PATTERN,
        description="call_id within `step` to read; requires `step`.",
    )


class FilterByStatusStep(_FilterReference):
    """Keep only the qubits whose referenced step or call succeeded."""

    type: Literal["FilterByStatus"]


class FilterByMetricStep(_FilterReference):
    """Keep only the qubits whose metric from the referenced step or call meets the threshold."""

    type: Literal["FilterByMetric"]
    metric: str = Field(
        min_length=1,
        description=(
            'Metric name, e.g. "x90_fidelity". With call_id it is an output '
            'parameter of that call, e.g. "t2_star".'
        ),
    )
    threshold: float = Field(description="Qubits with metric >= threshold are kept.")


class GenerateCRScheduleStep(_StepBase):
    """Plan parallel cross-resonance groups for the candidate qubits."""

    type: Literal["GenerateCRSchedule"]
    max_parallel_ops: int = Field(default=10, ge=1, le=100)
    inverse: bool = Field(
        default=False,
        description="Reverse CR direction: control has the higher design frequency.",
    )


class _TwoQubitModeStep(_StepBase):
    """Two-qubit steps with an execution_mode; adds no fields."""

    @model_serializer(mode="wrap")
    def _drop_manual_cap(self, handler: SerializerFunctionWrapHandler) -> Any:
        """Leave max_parallel_ops out of a manual step's dump so the dump validates again."""
        data = handler(self)
        if isinstance(data, dict) and getattr(self, "execution_mode", None) == "manual":
            data.pop("max_parallel_ops", None)
        return data


class TwoQubitCalibrationStep(_TwoQubitModeStep):
    """Full coupling calibration on the scheduled pairs."""

    type: Literal["TwoQubitCalibration"]
    step_id: str | None = Field(
        default=None, pattern=STEP_ID_PATTERN, description=_STEP_ID_DESCRIPTION
    )
    tasks: list[TaskCall] | None = Field(
        default=None, description=_TASKS_DESCRIPTION + " Defaults to FULL_2Q_TASKS."
    )
    # Omitted from dumps at their defaults so existing specs keep their plan digest.
    execution_mode: TwoQubitExecutionMode = Field(
        default="automatic",
        exclude_if=lambda value: value == "automatic",
        description=_TWO_QUBIT_MODE_DESCRIPTION,
    )
    rounds: list[list[QubitIdPair]] | None = Field(
        default=None, exclude_if=lambda value: value is None, description=_PAIR_ROUNDS_DESCRIPTION
    )
    max_parallel_ops: int = Field(
        default=10, ge=1, le=100, description=_MAX_PARALLEL_OPS_DESCRIPTION
    )

    _normalize_tasks = field_validator("tasks", mode="before")(_calls_or_none)
    _check_rounds = model_validator(mode="after")(_check_pair_rounds)


class CustomTwoQubitStep(_TwoQubitModeStep):
    """Any sequence of coupling task calls on the candidate couplings."""

    type: Literal["CustomTwoQubit"]
    step_name: str = Field(
        default="custom_two_qubit",
        pattern=STEP_ID_PATTERN,
        description="Name and step_id of this step; unique within the pipeline.",
    )
    tasks: list[TaskCall] = Field(min_length=1, description=_TASKS_DESCRIPTION)
    # Omitted from dumps at their defaults so existing specs keep their plan digest.
    execution_mode: TwoQubitExecutionMode = Field(
        default="automatic",
        exclude_if=lambda value: value == "automatic",
        description=_TWO_QUBIT_MODE_DESCRIPTION,
    )
    rounds: list[list[QubitIdPair]] | None = Field(
        default=None, exclude_if=lambda value: value is None, description=_PAIR_ROUNDS_DESCRIPTION
    )
    max_parallel_ops: int = Field(
        default=10, ge=1, le=100, description=_MAX_PARALLEL_OPS_DESCRIPTION
    )
    continue_on_failure: bool = Field(default=False, description=_CONTINUE_DESCRIPTION)

    _normalize_tasks = field_validator("tasks", mode="before")(_calls)
    _check_rounds = model_validator(mode="after")(_check_pair_rounds)


PipelineStep = Annotated[
    ConfigureAllStep
    | BringUpStep
    | OneQubitCheckStep
    | OneQubitFineTuneStep
    | CustomOneQubitStep
    | FilterByStatusStep
    | FilterByMetricStep
    | GenerateCRScheduleStep
    | TwoQubitCalibrationStep
    | CustomTwoQubitStep,
    Field(discriminator="type"),
]

TaskScope = Literal["qubit", "coupling"]


class StepCatalogEntry(BaseModel):
    """What the validator knows about one step type without importing it."""

    model_config = ConfigDict(frozen=True)

    type: str
    kind: Literal["calibration", "transform"]
    description: str
    name: str = Field(description="Default step name, and step_id when none is set.")
    requires: frozenset[str] = frozenset()
    provides: frozenset[str] = frozenset()
    task_scope: TaskScope | None = Field(
        default=None, description="task_type its tasks must have; None for steps without tasks."
    )
    default_tasks: tuple[TaskCall, ...] = ()
    one_qubit_result: bool = Field(
        default=False, description="Whether filters can read this step's per-qubit result."
    )
    step_metrics: tuple[str, ...] = Field(
        default=(), description="Metrics the step derives per qubit, for FilterByMetric."
    )


# Keys every pipeline starts with, as in ``Pipeline._validate``.
INITIAL_CONTEXT_KEYS: frozenset[str] = frozenset({"candidate_qids", "candidate_couplings"})

ONE_QUBIT_CHECK_METRICS: tuple[str, ...] = ("t1_average", "t2_echo_average")
ONE_QUBIT_FINE_TUNE_METRICS: tuple[str, ...] = (
    "x90_fidelity",
    "rb_fidelity",
    "t1_average",
    "t2_echo_average",
    "one_qubit_gate_coherence_limit",
)
BRINGUP_METRICS: tuple[str, ...] = (
    "readout_frequency",
    "readout_amplitude",
    "coarse_qubit_frequency",
    "qubit_frequency",
)

STEP_CATALOG: dict[str, StepCatalogEntry] = {
    entry.type: entry
    for entry in (
        StepCatalogEntry(
            type="ConfigureAll",
            kind="calibration",
            name="configure_all",
            description="Configure every box of the targeted MUXes once.",
            provides=frozenset({"configure_all"}),
        ),
        StepCatalogEntry(
            type="BringUp",
            kind="calibration",
            name="bringup",
            description="Initial characterization: spectroscopy and chevron per MUX and qubit.",
            provides=frozenset({"bringup"}),
            task_scope="qubit",
            default_tasks=tuple(BRINGUP_TASKS),
            one_qubit_result=True,
            step_metrics=BRINGUP_METRICS,
        ),
        StepCatalogEntry(
            type="OneQubitCheck",
            kind="calibration",
            name="one_qubit_check",
            description="Coarse one-qubit characterization.",
            provides=frozenset({"one_qubit_check", "candidate_qids"}),
            task_scope="qubit",
            default_tasks=tuple(CHECK_1Q_TASKS),
            one_qubit_result=True,
            step_metrics=ONE_QUBIT_CHECK_METRICS,
        ),
        StepCatalogEntry(
            type="OneQubitFineTune",
            kind="calibration",
            name="one_qubit_fine_tune",
            description="Fine one-qubit calibration and benchmarking.",
            provides=frozenset({"one_qubit_fine_tune", "candidate_qids"}),
            task_scope="qubit",
            default_tasks=tuple(FULL_1Q_TASKS_AFTER_CHECK),
            one_qubit_result=True,
            step_metrics=ONE_QUBIT_FINE_TUNE_METRICS,
        ),
        StepCatalogEntry(
            type="CustomOneQubit",
            kind="calibration",
            name="custom_one_qubit",
            description="Any sequence of qubit task calls on the current candidates.",
            provides=frozenset({"candidate_qids"}),  # plus its own step_name
            task_scope="qubit",
            one_qubit_result=True,
        ),
        StepCatalogEntry(
            type="FilterByStatus",
            kind="transform",
            name="filter_by_status",
            description="Keep the qubits whose referenced step or call succeeded.",
            requires=frozenset({"one_qubit_check", "one_qubit_fine_tune"}),
            provides=frozenset({"candidate_qids"}),
        ),
        StepCatalogEntry(
            type="FilterByMetric",
            kind="transform",
            name="filter_by_metric",
            description="Keep the qubits whose metric from the referenced step or call meets a "
            "threshold.",
            requires=frozenset({"one_qubit_check", "one_qubit_fine_tune"}),
            provides=frozenset({"candidate_qids"}),
        ),
        StepCatalogEntry(
            type="GenerateCRSchedule",
            kind="transform",
            name="generate_cr_schedule",
            description="Plan parallel cross-resonance groups for the candidate qubits.",
            requires=frozenset({"candidate_qids"}),
            provides=frozenset({"candidate_couplings"}),
        ),
        StepCatalogEntry(
            type="TwoQubitCalibration",
            kind="calibration",
            name="two_qubit_calibration",
            description="Full coupling calibration on the scheduled pairs.",
            requires=frozenset({"candidate_qids"}),
            provides=frozenset({"two_qubit", "candidate_couplings"}),
            task_scope="coupling",
            default_tasks=tuple(FULL_2Q_TASKS),
        ),
        StepCatalogEntry(
            type="CustomTwoQubit",
            kind="calibration",
            name="custom_two_qubit",
            description="Any sequence of coupling task calls on the candidate couplings.",
            requires=frozenset({"candidate_qids"}),
            provides=frozenset({"candidate_couplings"}),  # plus its own step_name
            task_scope="coupling",
        ),
    )
}


def step_name(step: PipelineStep) -> str:
    """The step's name in execution history: its step_id, step_name, or catalog name."""
    if isinstance(step, FilterByMetricStep):
        return f"filter_by_{step.metric}"
    own = getattr(step, "step_name", None) or getattr(step, "step_id", None)
    return str(own) if own else STEP_CATALOG[step.type].name


def step_id(step: PipelineStep) -> str | None:
    """The plan-scoped identifier of a calibration step; None for transforms."""
    if STEP_CATALOG[step.type].kind != "calibration":
        return None
    return step_name(step)


def step_calls(step: PipelineStep) -> list[TaskCall]:
    """The calls a step will run on every target, with call ids filled in."""
    if isinstance(step, ConfigureAllStep):
        return [configure_all_call(step.call)]
    entry = STEP_CATALOG[step.type]
    if entry.task_scope is None:
        return []
    own = getattr(step, "tasks", None)
    calls = list(own) if own is not None else list(entry.default_tasks)
    return list(calls_with_configure(calls, configure=bool(getattr(step, "configure", False))))


def step_tasks(step: PipelineStep) -> list[str]:
    """Task names a step runs, in call order and with repeats."""
    return [call.name for call in step_calls(step)]


def step_provides(step: PipelineStep) -> frozenset[str]:
    """Context keys the step makes available, including its own step_id."""
    provided = set(STEP_CATALOG[step.type].provides)
    own_id = step_id(step)
    if own_id:
        provided.add(own_id)
    return frozenset(provided)


def step_manual_rounds(
    step: PipelineStep,
) -> tuple[Literal["qubit"], QubitRounds] | tuple[Literal["coupling"], PairRounds] | None:
    """The parsed rounds of a manual step with its task scope; None for other steps."""
    if getattr(step, "execution_mode", None) != "manual":
        return None
    name = step_name(step)
    if isinstance(step, CustomTwoQubitStep | TwoQubitCalibrationStep):
        pairs = pair_rounds_for_mode("manual", step.rounds, None, step=name)
        assert pairs is not None
        return "coupling", pairs
    qubits = qubit_rounds_for_mode("manual", getattr(step, "rounds", None), step=name)
    assert qubits is not None
    return "qubit", qubits


def step_continue_on_failure(step: PipelineStep) -> bool:
    """The step-level failure default its calls inherit."""
    return bool(getattr(step, "continue_on_failure", False))


# ---------------------------------------------------------------------------
# Spec
# ---------------------------------------------------------------------------


class CalibrationPipelineSpec(BaseModel):
    """A complete, runnable calibration pipeline."""

    model_config = ConfigDict(extra="forbid")

    spec_version: Literal[2] = Field(
        description="Spec format version. Convert a version 1 spec with migrate_pipeline_spec.",
    )
    name: str = Field(
        default="pipeline",
        pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$",
        description="Display name of the execution.",
    )
    targets: PipelineTargets
    steps: list[PipelineStep] = Field(min_length=1, max_length=32)
    # Deprecated in the schema only: pydantic's ``deprecated=`` would also warn on
    # every attribute read inside QDash. Validation reports it through
    # pipeline_warnings instead.
    task_parameters: dict[str, TaskSettings] = Field(
        default_factory=dict,
        description=(
            "Deprecated: set run, input and update_calibration_parameters on each "
            "task call instead. Common per-task defaults keyed by task name; every "
            "call of the task starts from them and a call's own settings take "
            "precedence. Still accepted and applied."
        ),
        json_schema_extra={"deprecated": True},
    )
    default_run_parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Run parameters applied to every task, e.g. shots or interval.",
    )
    tags: list[str] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def _structure(self) -> CalibrationPipelineSpec:
        errors = validate_step_chain(self.steps)
        if errors:
            raise ValueError("; ".join(errors))
        return self

    def all_calls(self) -> list[tuple[PipelineStep, TaskCall]]:
        """Every (step, call) the pipeline runs per target, in order."""
        return [(step, call) for step in self.steps for call in step_calls(step)]

    def all_tasks(self) -> list[str]:
        """Every task name the pipeline runs, in order, with repeats."""
        return [call.name for _, call in self.all_calls()]

    def canonical_task_parameters(self) -> dict[str, dict[str, Any]]:
        """``task_parameters`` in the canonical entry form the worker merges."""
        return {name: settings.settings() for name, settings in self.task_parameters.items()}

    def plan(self) -> dict[str, Any]:
        """The validated plan: step ids, types and resolved calls, for history."""
        return {
            "spec_version": SPEC_VERSION,
            "name": self.name,
            "steps": [
                {
                    "index": index,
                    "step_id": step_id(step),
                    "name": step_name(step),
                    "type": step.type,
                    "kind": STEP_CATALOG[step.type].kind,
                    "calls": calls_json(step_calls(step)),
                }
                for index, step in enumerate(self.steps, start=1)
            ],
        }

    def plan_digest(self) -> str:
        """A stable version identifier of the full spec, as validated."""
        return plan_digest(self.model_dump(mode="json"))


def _reference_errors(
    index: int,
    step: FilterByStatusStep | FilterByMetricStep,
    earlier: Mapping[str, PipelineStep],
) -> list[str]:
    label = f"step {index} ({step.type})"
    if step.call_id is not None and step.step is None:
        return [f"{label} sets call_id {step.call_id!r} without the step it belongs to"]
    if step.step is None:
        return []
    target = earlier.get(step.step)
    if target is None:
        known = ", ".join(sorted(earlier)) or "none"
        return [f"{label} references step {step.step!r}, which is not an earlier step ({known})"]
    entry = STEP_CATALOG[target.type]
    if not entry.one_qubit_result:
        return [f"{label} references step {step.step!r}, a {target.type} without qubit results"]
    if step.call_id is not None:
        call_ids = [call.resolved_call_id for call in step_calls(target)]
        if step.call_id not in call_ids:
            return [
                f"{label} references call {step.call_id!r}, which step {step.step!r} does not "
                f"run ({', '.join(call_ids)})"
            ]
        return []
    if isinstance(step, FilterByMetricStep) and step.metric not in entry.step_metrics:
        derived = ", ".join(entry.step_metrics) or "none"
        return [
            f"{label} reads metric {step.metric!r} from step {step.step!r}, whose step-level "
            f"metrics are {derived}; set call_id to read an output parameter of one call"
        ]
    return []


def validate_step_chain(steps: Sequence[PipelineStep]) -> list[str]:
    """Check step order the way ``Pipeline._validate`` does, plus identity rules.

    A step whose ``requires`` lists several keys needs at least one of them
    (FilterByStatus accepts either one-qubit step), matching the worker's rule.
    A filter that references a step needs that step earlier instead. Calibration
    step ids must be unique. Returns human-readable problems; empty means sound.
    """
    errors: list[str] = []
    available: set[str] = set(INITIAL_CONTEXT_KEYS)
    seen_ids: dict[str, int] = {}
    earlier: dict[str, PipelineStep] = {}
    for index, step in enumerate(steps, start=1):
        entry = STEP_CATALOG[step.type]
        if isinstance(step, FilterByStatusStep | FilterByMetricStep) and (
            step.step is not None or step.call_id is not None
        ):
            errors.extend(_reference_errors(index, step, earlier))
        elif entry.requires and not (entry.requires & available):
            wanted = " or ".join(sorted(entry.requires))
            errors.append(
                f"step {index} ({step.type}) needs {wanted} from an earlier step, "
                f"but only {', '.join(sorted(available))} are available"
            )
        own_id = step_id(step)
        if own_id:
            if own_id in seen_ids:
                errors.append(
                    f"step {index} ({step.type}) reuses step_id {own_id!r} of step "
                    f"{seen_ids[own_id]}; set a unique step_id (or step_name) on repeated steps"
                )
            else:
                seen_ids[own_id] = index
                earlier[own_id] = step
        available |= step_provides(step)
    return errors


def pipeline_warnings(spec: CalibrationPipelineSpec) -> list[tuple[str, str]]:
    """Valid but probably unintended or deprecated choices, as (path, message) pairs.

    A non-empty ``task_parameters`` is deprecated in favor of settings on each call.

    A ``run.mux_ids`` for ConfigureAll, on a step's call or in ``task_parameters``,
    is replaced by the step's MUXes at run time, so it has no effect.

    A filter without a step reference reads the latest built-in one-qubit step
    (OneQubitFineTune, else OneQubitCheck), as in version 1; custom one-qubit
    steps between that step and the filter are not read.
    """
    found: list[tuple[str, str]] = []
    if spec.task_parameters:
        found.append(
            (
                "task_parameters",
                "task_parameters is deprecated; it still applies, but set run, input and "
                "update_calibration_parameters on each call of "
                f"{', '.join(sorted(spec.task_parameters))} instead "
                "(default_run_parameters for run values every task shares)",
            )
        )
    found.extend(_ignored_mux_ids_warnings(spec))
    custom_since_builtin: list[str] = []
    for index, step in enumerate(spec.steps):
        if isinstance(step, OneQubitCheckStep | OneQubitFineTuneStep):
            custom_since_builtin = []
        elif isinstance(step, CustomOneQubitStep | BringUpStep):
            custom_since_builtin.append(step_name(step))
        elif isinstance(step, FilterByStatusStep | FilterByMetricStep) and step.step is None:
            if custom_since_builtin:
                found.append(
                    (
                        f"steps[{index}]",
                        f"{step.type} has no step reference, so it reads the latest "
                        "OneQubitFineTune/OneQubitCheck result and ignores "
                        f"{', '.join(custom_since_builtin)}; set step to choose explicitly",
                    )
                )
    return found


def _ignored_mux_ids_warnings(spec: CalibrationPipelineSpec) -> list[tuple[str, str]]:
    """Warnings for ConfigureAll ``run.mux_ids`` values that the step replaces."""
    message = (
        "ConfigureAll runs on the step's mux_ids, or the targets' MUXes when unset, "
        "and replaces this value; set mux_ids on the ConfigureAll step instead"
    )
    found: list[tuple[str, str]] = []
    defaults = spec.task_parameters.get(CONFIGURE_ALL_CALL.name)
    has_configure_all = any(isinstance(step, ConfigureAllStep) for step in spec.steps)
    if has_configure_all and defaults is not None and "mux_ids" in (defaults.run or {}):
        found.append((f"task_parameters.{CONFIGURE_ALL_CALL.name}.run.mux_ids", message))
    for index, step in enumerate(spec.steps):
        if isinstance(step, ConfigureAllStep) and step.call is not None:
            if "mux_ids" in (step.call.run or {}):
                found.append((f"steps[{index}].call.run.mux_ids", message))
    return found


def pipeline_spec_json_schema() -> dict[str, Any]:
    """JSON schema of the spec, for tool definitions and the catalog endpoint."""
    return CalibrationPipelineSpec.model_json_schema()


# ---------------------------------------------------------------------------
# Migration from version 1
# ---------------------------------------------------------------------------


class SpecMigration(BaseModel):
    """The result of converting a spec to the current version."""

    from_version: int
    spec: dict[str, Any]
    notes: list[str] = Field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.from_version != SPEC_VERSION


_V1_CUSTOM_STEPS = frozenset({"CustomOneQubit", "CustomTwoQubit"})
_V1_TASK_STEPS = frozenset(
    {
        "BringUp",
        "OneQubitCheck",
        "OneQubitFineTune",
        "CustomOneQubit",
        "TwoQubitCalibration",
        "CustomTwoQubit",
    }
)


def _unique_id(base: str, taken: set[str]) -> str:
    """``base`` with the lowest ``_<n>`` suffix (n >= 2) not in ``taken``."""
    nth = 2
    while f"{base}_{nth}" in taken:
        nth += 1
    return f"{base}_{nth}"


def _migrate_task_list(tasks: Sequence[Any], where: str, notes: list[str]) -> list[dict[str, Any]]:
    counts = Counter(task for task in tasks if isinstance(task, str))
    # Ids already claimed: explicit call_ids and the default id (the task name)
    # of every task listed once, so a generated suffix never collides with them.
    taken: set[str] = {task for task, count in counts.items() if count == 1}
    for task in tasks:
        if isinstance(task, Mapping):
            claimed = task.get("call_id") or task.get("name")
            if isinstance(claimed, str):
                taken.add(claimed)
    assigned: dict[str, list[str]] = {}
    converted: list[dict[str, Any]] = []
    for task in tasks:
        if not isinstance(task, str):
            # Already a call; keep it so validation reports anything wrong with it.
            converted.append(dict(task) if isinstance(task, Mapping) else task)
            continue
        call: dict[str, Any] = {"name": task}
        if counts[task] > 1:
            call_id = task if task not in taken else _unique_id(task, taken)
            taken.add(call_id)
            assigned.setdefault(task, []).append(call_id)
            call["call_id"] = call_id
        converted.append(call)
    for task, ids in assigned.items():
        notes.append(
            f"{where}: {task!r} runs {len(ids)} times; assigned call_ids {', '.join(ids)}. "
            "Rename them to describe each call."
        )
    return converted


def _migrate_step_ids(steps: list[Any], notes: list[str]) -> None:
    """Give repeated built-in calibration steps unique step_ids.

    Version 1 allowed the same built-in step twice; version 2 identifies each
    calibration step by a unique step_id that defaults to the step's name. The
    first step keeps its default, later ones get ``<name>_2``, ... skipping ids a
    custom step's name or an explicit step_id already uses. Filters without a
    step reference still read the latest OneQubitFineTune/OneQubitCheck result,
    so renaming does not change what they read.
    """
    taken: set[str] = set()
    for step in steps:
        if not isinstance(step, Mapping) or step.get("type") not in STEP_CATALOG:
            continue
        entry = STEP_CATALOG[step["type"]]
        if entry.kind != "calibration":
            continue
        own = step.get("step_name") if step["type"] in _V1_CUSTOM_STEPS else step.get("step_id")
        if isinstance(own, str):
            taken.add(own)
        elif step["type"] in _V1_CUSTOM_STEPS:
            taken.add(entry.name)
    for index, step in enumerate(steps):
        if not isinstance(step, dict) or step.get("type") not in STEP_CATALOG:
            continue
        if step["type"] in _V1_CUSTOM_STEPS or step.get("step_id") is not None:
            continue
        entry = STEP_CATALOG[step["type"]]
        if entry.kind != "calibration":
            continue
        if entry.name not in taken:
            taken.add(entry.name)
            continue
        new_id = _unique_id(entry.name, taken)
        taken.add(new_id)
        step["step_id"] = new_id
        notes.append(
            f"steps[{index}]: {step['type']} repeats step_id {entry.name!r}; assigned "
            f"step_id {new_id!r}. Rename it to describe the step."
        )


def migrate_pipeline_spec(spec: Mapping[str, Any]) -> SpecMigration:
    """Convert a pipeline spec to version 2 without changing what it runs.

    Version 1 (no ``spec_version``) listed task names and kept run overrides in
    ``task_run_parameters`` keyed by task name. The conversion turns every name
    into a ``TaskCall`` (a task listed more than once in one step gets
    ``call_id`` values ``<Task>``, ``<Task>_2``, ..., skipping ids the step
    already uses), gives a repeated built-in calibration step a unique
    ``step_id`` (``<name>_2``, ...), and moves
    ``task_run_parameters`` into ``task_parameters`` with the same effect, since
    version 1 overrides applied to every occurrence of the task. A version 2 spec
    is returned unchanged. The function is pure and deterministic; it does not
    validate the result.
    """
    version = spec.get("spec_version", 1)
    if version == SPEC_VERSION:
        return SpecMigration(from_version=SPEC_VERSION, spec=copy.deepcopy(dict(spec)))
    if version != 1:
        raise ValueError(f"unknown spec_version {version!r}; this QDash reads 1 and 2")

    converted = copy.deepcopy(dict(spec))
    converted.pop("spec_version", None)
    notes: list[str] = []
    steps = converted.get("steps")
    if isinstance(steps, list):
        for index, step in enumerate(steps):
            if not isinstance(step, dict) or step.get("type") not in _V1_TASK_STEPS:
                continue
            tasks = step.get("tasks")
            if isinstance(tasks, list):
                step["tasks"] = _migrate_task_list(tasks, f"steps[{index}].tasks", notes)
        _migrate_step_ids(steps, notes)
    run_overrides = converted.pop("task_run_parameters", None)
    if run_overrides:
        canonical = task_parameters_from_run_parameters(run_overrides)
        task_parameters: dict[str, Any] = {}
        for name, entry in canonical.items():
            settings: dict[str, Any] = {"run": entry["run"]}
            if "update_calibration_parameters" in entry:
                settings["update_calibration_parameters"] = entry["update_calibration_parameters"]
            task_parameters[name] = settings
        converted["task_parameters"] = task_parameters
        notes.append("task_run_parameters moved to task_parameters.<task>.run")
    result = {"spec_version": SPEC_VERSION, **converted}
    return SpecMigration(from_version=1, spec=result, notes=notes)
