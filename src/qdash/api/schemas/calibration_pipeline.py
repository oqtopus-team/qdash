"""API schemas for declarative calibration pipelines."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - pydantic field type
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from qdash.api.schemas.flow import (
    CALIBRATION_SESSION_FIELD,
    IDEMPOTENCY_KEY_FIELD,
    ExecuteFlowResponse,
)
from qdash.datamodel.launch_origin import ReportedLaunchOrigin  # noqa: TC001 - pydantic field
from qdash.datamodel.task import TaskDocumentation  # noqa: TC001 - pydantic field type
from qdash.datamodel.task_call import TaskCall  # noqa: TC001 - pydantic field type

_SPEC_EXAMPLE: dict[str, Any] = {
    "spec_version": 2,
    "name": "coarse-then-two-pass-ramsey",
    "targets": {"qids": ["0", "1"]},
    "steps": [
        {"type": "OneQubitCheck", "execution_mode": "parallel_by_mux"},
        {"type": "FilterByStatus"},
        {
            "type": "CustomOneQubit",
            "step_name": "coherence",
            "execution_mode": "parallel_by_mux",
            "continue_on_failure": True,
            "tasks": [
                {"name": "CheckT1"},
                {
                    "name": "CheckRamsey",
                    "call_id": "ramsey_coarse",
                    "run": {"detuning": 0.001, "shots": 1024},
                },
                {
                    "name": "CheckRamsey",
                    "call_id": "ramsey_fine",
                    "run": {
                        "detuning": 0.0002,
                        "shots": 1024,
                        "time_range": {"value": [0, 50001, 500], "value_type": "np.arange"},
                    },
                },
            ],
        },
        {
            "type": "FilterByMetric",
            "step": "coherence",
            "call_id": "ramsey_fine",
            "metric": "t2_star",
            "threshold": 10.0,
        },
    ],
    "default_run_parameters": {"interval": 153600},
}


class PipelineProblem(BaseModel):
    """One reason a spec cannot run as written."""

    path: str = Field(description='Where in the spec, e.g. "steps[2].tasks[0]" or "targets.qids".')
    message: str


class RequestFieldError(BaseModel):
    """One field of the request body that failed schema validation."""

    loc: list[str | int] = Field(description="Where in the request, e.g. ['body', 'chip_id'].")
    msg: str
    type: str

    model_config = ConfigDict(extra="allow")


class PipelineProblemsDetail(BaseModel):
    """Why a calibration pipeline spec was refused, with every problem found."""

    message: str
    problems: list[PipelineProblem] = Field(default_factory=list)


class PipelinePlanUnprocessableResponse(BaseModel):
    """The 422 body of the stored-plan endpoints.

    ``detail`` is a list when the request body does not match its schema, an object with
    ``problems`` when the spec is not valid or its targets cannot be resolved, and a message
    when the request does not match the plan (another chip or backend) or its calibration
    session is on another chip.
    """

    detail: list[RequestFieldError] | PipelineProblemsDetail | str


class ResolvedTaskCall(BaseModel):
    """One call as it will run: identity and settings after per-task defaults."""

    call_id: str = Field(description="Identifier of the call within its step.")
    name: str = Field(description="Task name.")
    on_failure: str = Field(
        description='"stop" or "continue": what the target\'s later calls do if this one fails.'
    )
    settings: dict[str, Any] = Field(
        description=(
            "Effective call settings (run, input, and update_calibration_parameters when "
            "set): the call's own settings over the deprecated task_parameters. default_run_parameters "
            "and task declarations fill in the rest when the task runs."
        )
    )


class ResolvedPipelineStep(BaseModel):
    """A step as it will run: effective calls filled in from the catalog defaults."""

    index: int = Field(description="1-based position in the pipeline.")
    type: str
    name: str = Field(description="Step name as it appears in execution history.")
    step_id: str | None = Field(
        default=None, description="Plan-scoped id of a calibration step; filters reference it."
    )
    kind: str = Field(description='"calibration" runs hardware; "transform" only filters.')
    tasks: list[str] = Field(
        description="Task names in call order, with repeats; empty for transforms."
    )
    calls: list[ResolvedTaskCall] = Field(
        default_factory=list, description="The calls each target runs, in order."
    )
    reference: dict[str, Any] | None = Field(
        default=None,
        description="For filters: the step and call they read, or null for the default.",
    )


class ResolvedPipelineTargets(BaseModel):
    """The starting targets after chip lookup."""

    qids: list[str] = Field(
        description="Explicit qids, the qubits of the pairs, or empty when targeting MUXes."
    )
    mux_ids: list[int] = Field(default_factory=list)
    exclude_qids: list[str] = Field(default_factory=list)
    pairs: list[list[str]] = Field(
        default_factory=list,
        description="Directed [control, target] coupling pairs, or empty without pair targets.",
    )


class ValidatePipelineRequest(BaseModel):
    """A spec to check against the project, chip, and backend."""

    chip_id: str = Field(min_length=1)
    spec: dict[str, Any] = Field(
        description="CalibrationPipelineSpec as JSON; see GET /calibration-pipelines/catalog."
    )
    backend_name: str | None = Field(
        default=None, description="Defaults to the configured backend."
    )

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"chip_id": "64Qv3", "spec": _SPEC_EXAMPLE}]}
    )


class ValidatePipelineResponse(BaseModel):
    """Whether the spec can run, and what it would do.

    ``valid`` is true exactly when ``problems`` is empty. ``warnings`` never make
    a spec invalid; they point at choices that are allowed but probably unintended.
    """

    valid: bool
    problems: list[PipelineProblem] = Field(default_factory=list)
    warnings: list[PipelineProblem] = Field(
        default_factory=list, description="Allowed but probably unintended choices."
    )
    backend_name: str
    spec_version: int | None = Field(
        default=None, description="Version of the submitted spec, when it could be read."
    )
    spec: dict[str, Any] | None = Field(
        default=None, description="The normalized spec, when it parsed; defaults filled in."
    )
    migrated_spec: dict[str, Any] | None = Field(
        default=None,
        description=(
            "For a convertible version 1 spec: the same pipeline converted to version 2. "
            "Absent when a one-qubit step uses a removed mode setting or name. Review it, "
            "rename generated call_ids if you like, and submit it instead."
        ),
    )
    plan_digest: str | None = Field(
        default=None,
        description=(
            "Digest of the validated spec, stored as note.pipeline.spec_digest on each step "
            "execution. Task results carry the worker's resolved-plan digest "
            "(note.calibration_plan.digest) in invocation.plan_digest."
        ),
    )
    targets: ResolvedPipelineTargets | None = None
    steps: list[ResolvedPipelineStep] = Field(default_factory=list)
    task_run_count: int = Field(default=0, description="Task calls per target qubit or coupling.")


DECISION_ID_FIELD = (
    "With calibration_session_id: the decision of that session this run carries out, "
    "recorded before dispatch with an experiment. QDash checks it belongs to the "
    "session and records the link on the run; it grants nothing."
)


class ExecutePipelineRequest(ValidatePipelineRequest):
    """Dispatch one pipeline run with a separate execution for each step reached."""

    calibration_session_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description=CALIBRATION_SESSION_FIELD,
    )
    idempotency_key: str | None = Field(
        default=None, min_length=1, max_length=128, description=IDEMPOTENCY_KEY_FIELD
    )

    decision_id: str | None = Field(
        default=None, min_length=1, max_length=200, description=DECISION_ID_FIELD
    )

    reported_origin: ReportedLaunchOrigin | None = Field(
        default=None,
        description=(
            "How the caller says it started the run, such as an agent tool. QDash stores it as "
            "given and shows it as reported: it is not verified, does not link the run to an "
            "agent session, and grants nothing. The signed-in user stays responsible for the run."
        ),
    )

    @model_validator(mode="after")
    def validate_calibration_session(self) -> ExecutePipelineRequest:
        """A decision belongs to a session the request names."""
        if self.decision_id is not None and self.calibration_session_id is None:
            raise ValueError("decision_id needs calibration_session_id")
        return self


class CreatePipelinePlanRequest(ValidatePipelineRequest):
    """Store a validated spec as a plan that can be approved and run by reference."""

    idempotency_key: str = Field(
        min_length=1,
        max_length=128,
        description=(
            "Identity of this creation, such as the tool call that asks for it. While the plan "
            "it created is stored (until seven days after the plan expires), repeating it with "
            "the same request returns that plan, or reports it expired, and repeating it with "
            "another request is a conflict; it never changes or renews that plan. After the "
            "plan is deleted the key is free again: the same key then creates a new plan with "
            "a new plan_id and review_digest that needs its own approval."
        ),
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"chip_id": "64Qv3", "spec": _SPEC_EXAMPLE, "idempotency_key": "plan-request-1"}
            ]
        }
    )


class PipelinePlanResponse(BaseModel):
    """A stored plan and everything an approval of it covers.

    A plan starts nothing and grants nothing. ``review_digest`` is a full, versioned SHA-256
    of the review content: the normalized spec with every default task list written out,
    the qubits its targets resolve to when the run starts, the resolved calls of every step,
    and the run defaults. Running the plan names that digest, so the run is the plan that
    was reviewed. Filters and CR schedules still select from results while the run goes;
    calibration values, task code and hardware state are read when it runs.
    """

    plan_id: str = Field(description="Opaque ID of the plan.")
    chip_id: str
    backend_name: str
    created_by: str
    created_at: datetime
    expires_at: datetime = Field(
        description="After this the plan cannot be executed; create a new plan instead."
    )
    expired: bool
    review_version: int
    review_digest: str = Field(
        description=(
            "sha256:v<version>:<hex> of the review content; pass it as expected_review_digest. "
            "Not the spec's plan_digest."
        )
    )
    spec: dict[str, Any] = Field(description="The normalized spec with default task lists.")
    spec_digest: str | None = Field(
        default=None,
        description="The short spec digest /validate reports as plan_digest, for history.",
    )
    targets: ResolvedPipelineTargets | None = None
    target_qids: list[str] = Field(
        description="The qubits the targets resolve to when the run starts (MUXes expanded)."
    )
    steps: list[ResolvedPipelineStep] = Field(default_factory=list)
    warnings: list[PipelineProblem] = Field(default_factory=list)
    task_run_count: int = 0
    default_run_parameters: dict[str, Any] = Field(default_factory=dict)
    task_parameters: dict[str, Any] = Field(default_factory=dict)
    replayed: bool = Field(
        default=False,
        description="True when a repeated creation returned the plan it stored before.",
    )


class ExecutePipelinePlanRequest(BaseModel):
    """Run a stored plan exactly as it was reviewed."""

    chip_id: str = Field(min_length=1, description="Must be the plan's chip.")
    expected_review_digest: str = Field(
        pattern=r"^sha256:v[0-9]+:[0-9a-f]{64}$",
        description=(
            "The review digest the person approved. A plan with another digest, or one whose "
            "revalidated content no longer has it, is refused."
        ),
    )
    backend_name: str | None = Field(
        default=None, description="Must be the plan's backend when given."
    )
    calibration_session_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description=CALIBRATION_SESSION_FIELD,
    )
    idempotency_key: str | None = Field(
        default=None, min_length=1, max_length=128, description=IDEMPOTENCY_KEY_FIELD
    )
    # The same schema as ExecutePipelineRequest.decision_id, so generated clients share one
    # type for both fields and an existing caller's typed value stays valid for either.
    decision_id: str | None = Field(
        default=None, min_length=1, max_length=200, description=DECISION_ID_FIELD
    )
    reported_origin: ReportedLaunchOrigin | None = Field(
        default=None,
        description="As for POST /calibration-pipelines/execute: stored as reported.",
    )

    @model_validator(mode="after")
    def validate_calibration_session(self) -> ExecutePipelinePlanRequest:
        """A decision belongs to a session the request names."""
        if self.decision_id is not None and self.calibration_session_id is None:
            raise ValueError("decision_id needs calibration_session_id")
        return self


class ExecutePipelineResponse(ExecuteFlowResponse):
    """Dispatch result plus the resolved plan that was started."""

    steps: list[ResolvedPipelineStep] = Field(default_factory=list)
    targets: ResolvedPipelineTargets | None = None
    pipeline_run_id: str | None = Field(
        default=None, description="The run QDash recorded for the launch (calibration_run_id)"
    )
    decision_id: str | None = Field(
        default=None,
        description=(
            "The decision the recorded run carries out, as QDash linked it; null when the "
            "request named none. A client that sent a decision checks it is echoed here"
        ),
    )
    plan_id: str | None = Field(
        default=None,
        description=(
            "For a run of a stored plan: the plan it carries out. A client that ran a plan "
            "checks it and review_digest are echoed here"
        ),
    )
    review_digest: str | None = Field(
        default=None, description="For a run of a stored plan: the review digest it ran."
    )


class PipelineStepTypeInfo(BaseModel):
    """One step type an agent may use."""

    type: str
    kind: str
    description: str
    requires: list[str] = Field(description="Any one of these must come from an earlier step.")
    provides: list[str]
    task_scope: str | None = Field(description='"qubit" or "coupling" for steps that run tasks.')
    default_step_id: str | None = Field(
        default=None, description="step_id of a calibration step that sets none."
    )
    default_tasks: list[TaskCall] = Field(description="Calls the step runs without tasks.")
    step_metrics: list[str] = Field(
        default_factory=list, description="Metrics FilterByMetric can read from the step itself."
    )


class PipelineCatalogResponse(BaseModel):
    """Everything needed to write a spec for this project."""

    backend_name: str
    step_types: list[PipelineStepTypeInfo]
    one_qubit_execution_modes: list[str] = Field(
        description=(
            "Values OneQubitCheck, OneQubitFineTune and CustomOneQubit accept for "
            "execution_mode; manual requires rounds."
        )
    )
    two_qubit_execution_modes: list[str] = Field(
        description=(
            "Values TwoQubitCalibration and CustomTwoQubit accept for execution_mode; "
            "manual requires rounds."
        )
    )
    tasks: dict[str, list[str]] = Field(
        description='Available task names by task_type ("qubit", "coupling", ...).'
    )
    task_documentation: dict[str, TaskDocumentation] = Field(
        default_factory=dict,
        description=(
            "Guidance declared by available tasks, keyed by task name. Tasks that "
            "declare no documentation are omitted."
        ),
    )
    spec_version: int = Field(description="The spec version this QDash accepts.")
    spec_schema: dict[str, Any] = Field(description="JSON schema of CalibrationPipelineSpec.")
    example: dict[str, Any] = Field(default_factory=lambda: dict(_SPEC_EXAMPLE))
