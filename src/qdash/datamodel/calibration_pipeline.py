"""Declarative calibration pipeline specification.

A pipeline spec is what an agent (or a user) writes to run a calibration
without authoring a Python flow: targets, an ordered list of steps, and run
parameters. Every step maps onto one of the Step classes in
``qdash.workflow.service.steps``; the spec cannot reference anything else, so
the handshake between the API (which validates and dispatches) and the worker
(which builds the Step objects) is this module alone.

The module stays free of workflow imports so the API process, which has no
Prefect runtime, can validate a spec. ``STEP_CATALOG`` therefore restates each
Step class's ``requires`` / ``provides``; ``tests/qdash/workflow`` asserts the
two agree.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# Default task lists
# ---------------------------------------------------------------------------
# These are the standard task sequences the workflow templates build on.
# ``qdash.workflow.service.tasks`` re-exports them; keep the single copy here so
# both the worker and the API resolve a step's effective task list identically.

BRINGUP_TASKS: list[str] = [
    "CheckResonatorSpectroscopy",  # MUX-level: estimates readout_frequency
    "CheckQubitSpectroscopy",  # coarse_qubit_frequency, anharmonicity, coarse_control_amplitude
    "CheckControlAmplitude",  # Refine coarse_control_amplitude from spectroscopy-derived seed
    "CheckAdaptiveChevron",
]

CHECK_1Q_TASKS: list[str] = [
    "CheckRabi",
    "CheckRabi",
    "CreateHPIPulse",
    "CheckHPIPulse",
    "CheckRabi",
    "CreateHPIPulse",
    "CheckHPIPulse",
    "CheckT1",
    "CheckT2Echo",
    "CheckRamsey",
]

FULL_1Q_TASKS_AFTER_CHECK: list[str] = [
    "CheckRabi",
    "CreateHPIPulse",
    "CheckHPIPulse",
    "CreatePIPulse",
    "CheckPIPulse",
    "CreateDRAGHPIPulse",
    "CheckDRAGHPIPulse",
    "CreateDRAGPIPulse",
    "CheckDRAGPIPulse",
    "ReadoutClassification",
    "CheckT1Average",
    "CheckT2EchoAverage",
    "Check1QGateCoherenceLimit",
    "RandomizedBenchmarking",
    "X90InterleavedRandomizedBenchmarking",
]

FULL_1Q_TASKS: list[str] = CHECK_1Q_TASKS + FULL_1Q_TASKS_AFTER_CHECK

FULL_2Q_TASKS: list[str] = [
    "CheckCrossResonance",
    "CreateZX90",
    "CheckZX90",
    "CheckBellState",
    "CheckBellStateTomography",
    "Check2QGateCoherenceLimit",
    "ZX90InterleavedRandomizedBenchmarking",
]

ONE_QUBIT_MODES: tuple[str, ...] = (
    "synchronized",
    "scheduled",
    "simultaneous_spectroscopy",
    "serial",
)
OneQubitMode = Literal["synchronized", "scheduled", "simultaneous_spectroscopy", "serial"]

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


class ConfigureAllStep(_StepBase):
    """Configure every box of the targeted MUXes once."""

    type: Literal["ConfigureAll"]
    mux_ids: list[int] | None = Field(
        default=None, description="MUXes to configure; defaults to the targets' MUXes."
    )


class BringUpStep(_StepBase):
    """Initial characterization: resonator and qubit spectroscopy, chevron."""

    type: Literal["BringUp"]
    tasks: list[str] | None = Field(
        default=None, description="Qubit tasks to run; defaults to BRINGUP_TASKS."
    )


class OneQubitCheckStep(_StepBase):
    """Coarse one-qubit characterization (Rabi, HPI, T1, T2, Ramsey)."""

    type: Literal["OneQubitCheck"]
    mode: OneQubitMode = "synchronized"
    tasks: list[str] | None = Field(
        default=None, description="Qubit tasks to run; defaults to CHECK_1Q_TASKS."
    )
    configure: bool = Field(default=False, description="Run Configure before the first task.")


class OneQubitFineTuneStep(_StepBase):
    """Fine one-qubit calibration (DRAG, readout classification, benchmarking)."""

    type: Literal["OneQubitFineTune"]
    mode: OneQubitMode = "synchronized"
    tasks: list[str] | None = Field(
        default=None, description="Qubit tasks to run; defaults to FULL_1Q_TASKS_AFTER_CHECK."
    )
    configure: bool = Field(default=False, description="Run Configure before the first task.")


class CustomOneQubitStep(_StepBase):
    """Any sequence of qubit tasks on the current candidate qubits."""

    type: Literal["CustomOneQubit"]
    step_name: str = Field(
        default="custom_one_qubit",
        pattern=r"^[a-z][a-z0-9_]{0,63}$",
        description="Name shown for this step; unique within the pipeline.",
    )
    tasks: list[str] = Field(min_length=1, description="Qubit tasks to run, in order.")
    mode: OneQubitMode = "synchronized"


class FilterByStatusStep(_StepBase):
    """Keep only the qubits whose latest one-qubit step succeeded."""

    type: Literal["FilterByStatus"]


class FilterByMetricStep(_StepBase):
    """Keep only the qubits whose metric from the latest one-qubit step meets the threshold."""

    type: Literal["FilterByMetric"]
    metric: str = Field(min_length=1, description='Metric name, e.g. "x90_fidelity" or "t1".')
    threshold: float = Field(description="Qubits with metric >= threshold are kept.")


class GenerateCRScheduleStep(_StepBase):
    """Plan parallel cross-resonance groups for the candidate qubits."""

    type: Literal["GenerateCRSchedule"]
    max_parallel_ops: int = Field(default=10, ge=1, le=100)
    inverse: bool = Field(
        default=False,
        description="Reverse CR direction: control has the higher design frequency.",
    )


class TwoQubitCalibrationStep(_StepBase):
    """Full coupling calibration on the scheduled pairs."""

    type: Literal["TwoQubitCalibration"]
    tasks: list[str] | None = Field(
        default=None, description="Coupling tasks to run; defaults to FULL_2Q_TASKS."
    )
    max_parallel_ops: int = Field(default=10, ge=1, le=100)


class CustomTwoQubitStep(_StepBase):
    """Any sequence of coupling tasks on the candidate couplings."""

    type: Literal["CustomTwoQubit"]
    step_name: str = Field(
        default="custom_two_qubit",
        pattern=r"^[a-z][a-z0-9_]{0,63}$",
        description="Name shown for this step; unique within the pipeline.",
    )
    tasks: list[str] = Field(min_length=1, description="Coupling tasks to run, in order.")
    max_parallel_ops: int = Field(default=10, ge=1, le=100)


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
    requires: frozenset[str] = frozenset()
    provides: frozenset[str] = frozenset()
    task_scope: TaskScope | None = Field(
        default=None, description="task_type its tasks must have; None for steps without tasks."
    )
    default_tasks: tuple[str, ...] = ()


# Keys every pipeline starts with, as in ``Pipeline._validate``.
INITIAL_CONTEXT_KEYS: frozenset[str] = frozenset({"candidate_qids", "candidate_couplings"})

STEP_CATALOG: dict[str, StepCatalogEntry] = {
    entry.type: entry
    for entry in (
        StepCatalogEntry(
            type="ConfigureAll",
            kind="calibration",
            description="Configure every box of the targeted MUXes once.",
            provides=frozenset({"configure_all"}),
        ),
        StepCatalogEntry(
            type="BringUp",
            kind="calibration",
            description="Initial characterization: spectroscopy and chevron per MUX and qubit.",
            provides=frozenset({"bringup"}),
            task_scope="qubit",
            default_tasks=tuple(BRINGUP_TASKS),
        ),
        StepCatalogEntry(
            type="OneQubitCheck",
            kind="calibration",
            description="Coarse one-qubit characterization.",
            provides=frozenset({"one_qubit_check", "candidate_qids"}),
            task_scope="qubit",
            default_tasks=tuple(CHECK_1Q_TASKS),
        ),
        StepCatalogEntry(
            type="OneQubitFineTune",
            kind="calibration",
            description="Fine one-qubit calibration and benchmarking.",
            provides=frozenset({"one_qubit_fine_tune", "candidate_qids"}),
            task_scope="qubit",
            default_tasks=tuple(FULL_1Q_TASKS_AFTER_CHECK),
        ),
        StepCatalogEntry(
            type="CustomOneQubit",
            kind="calibration",
            description="Any sequence of qubit tasks on the current candidates.",
            provides=frozenset({"candidate_qids"}),  # plus its own step_name
            task_scope="qubit",
        ),
        StepCatalogEntry(
            type="FilterByStatus",
            kind="transform",
            description="Keep the qubits whose latest one-qubit step succeeded.",
            requires=frozenset({"one_qubit_check", "one_qubit_fine_tune"}),
            provides=frozenset({"candidate_qids"}),
        ),
        StepCatalogEntry(
            type="FilterByMetric",
            kind="transform",
            description="Keep the qubits whose metric meets a threshold.",
            requires=frozenset({"one_qubit_check", "one_qubit_fine_tune"}),
            provides=frozenset({"candidate_qids"}),
        ),
        StepCatalogEntry(
            type="GenerateCRSchedule",
            kind="transform",
            description="Plan parallel cross-resonance groups for the candidate qubits.",
            requires=frozenset({"candidate_qids"}),
            provides=frozenset({"candidate_couplings"}),
        ),
        StepCatalogEntry(
            type="TwoQubitCalibration",
            kind="calibration",
            description="Full coupling calibration on the scheduled pairs.",
            requires=frozenset({"candidate_qids"}),
            provides=frozenset({"two_qubit", "candidate_couplings"}),
            task_scope="coupling",
            default_tasks=tuple(FULL_2Q_TASKS),
        ),
        StepCatalogEntry(
            type="CustomTwoQubit",
            kind="calibration",
            description="Any sequence of coupling tasks on the candidate couplings.",
            requires=frozenset({"candidate_qids"}),
            provides=frozenset({"candidate_couplings"}),  # plus its own step_name
            task_scope="coupling",
        ),
    )
}


def step_tasks(step: PipelineStep) -> list[str]:
    """The tasks a step will run: its own list, or the catalog default."""
    entry = STEP_CATALOG[step.type]
    own = getattr(step, "tasks", None)
    if own is not None:
        return list(own)
    return list(entry.default_tasks)


def step_provides(step: PipelineStep) -> frozenset[str]:
    """Context keys the step makes available, including a custom step's own name."""
    provided = set(STEP_CATALOG[step.type].provides)
    step_name = getattr(step, "step_name", None)
    if step_name:
        provided.add(step_name)
    return frozenset(provided)


# ---------------------------------------------------------------------------
# Spec
# ---------------------------------------------------------------------------


class CalibrationPipelineSpec(BaseModel):
    """A complete, runnable calibration pipeline."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        default="pipeline",
        pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$",
        description="Display name of the execution.",
    )
    targets: PipelineTargets
    steps: list[PipelineStep] = Field(min_length=1, max_length=32)
    task_run_parameters: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Run parameter overrides keyed by task name, then parameter name.",
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

    def all_tasks(self) -> list[str]:
        """Every task the pipeline runs, in order, with repeats."""
        return [task for step in self.steps for task in step_tasks(step)]


def validate_step_chain(steps: list[PipelineStep]) -> list[str]:
    """Check step order the way ``Pipeline._validate`` does, plus name uniqueness.

    A step whose ``requires`` lists several keys needs at least one of them
    (FilterByStatus accepts either one-qubit step), matching the worker's rule.
    Returns human-readable problems; empty means the chain is sound.
    """
    errors: list[str] = []
    available: set[str] = set(INITIAL_CONTEXT_KEYS)
    seen_names: set[str] = set()
    for index, step in enumerate(steps, start=1):
        entry = STEP_CATALOG[step.type]
        if entry.requires and not (entry.requires & available):
            wanted = " or ".join(sorted(entry.requires))
            errors.append(
                f"step {index} ({step.type}) needs {wanted} from an earlier step, "
                f"but only {', '.join(sorted(available))} are available"
            )
        step_name = getattr(step, "step_name", None)
        if step_name:
            if step_name in seen_names:
                errors.append(f"step {index} ({step.type}) reuses step_name {step_name!r}")
            seen_names.add(step_name)
        available |= step_provides(step)
    return errors


def pipeline_spec_json_schema() -> dict[str, Any]:
    """JSON schema of the spec, for tool definitions and the catalog endpoint."""
    return CalibrationPipelineSpec.model_json_schema()
