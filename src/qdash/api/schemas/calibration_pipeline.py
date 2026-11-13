"""API schemas for declarative calibration pipelines."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from qdash.api.schemas.flow import ExecuteFlowResponse
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

    qids: list[str] = Field(description="Explicit qids, or empty when targeting MUXes.")
    mux_ids: list[int] = Field(default_factory=list)
    exclude_qids: list[str] = Field(default_factory=list)


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
            "For a version 1 spec: the same pipeline converted to version 2. Review it, "
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


class ExecutePipelineRequest(ValidatePipelineRequest):
    """Validate, then dispatch the pipeline as one execution."""


class ExecutePipelineResponse(ExecuteFlowResponse):
    """Dispatch result plus the resolved plan that was started."""

    steps: list[ResolvedPipelineStep] = Field(default_factory=list)
    targets: ResolvedPipelineTargets | None = None


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
    spec_version: int = Field(description="The spec version this QDash accepts.")
    spec_schema: dict[str, Any] = Field(description="JSON schema of CalibrationPipelineSpec.")
    example: dict[str, Any] = Field(default_factory=lambda: dict(_SPEC_EXAMPLE))
