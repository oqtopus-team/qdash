"""API schemas for declarative calibration pipelines."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from qdash.api.schemas.flow import ExecuteFlowResponse

_SPEC_EXAMPLE: dict[str, Any] = {
    "name": "coarse-then-coherence",
    "targets": {"qids": ["0", "1"]},
    "steps": [
        {"type": "OneQubitCheck", "mode": "scheduled"},
        {"type": "FilterByStatus"},
        {
            "type": "CustomOneQubit",
            "step_name": "coherence",
            "tasks": ["CheckT1", "CheckT2Echo"],
            "mode": "scheduled",
        },
    ],
    "default_run_parameters": {"shots": 1024},
}


class PipelineProblem(BaseModel):
    """One reason a spec cannot run as written."""

    path: str = Field(description='Where in the spec, e.g. "steps[2].tasks[0]" or "targets.qids".')
    message: str


class ResolvedPipelineStep(BaseModel):
    """A step as it will run: effective tasks filled in from the catalog defaults."""

    index: int = Field(description="1-based position in the pipeline.")
    type: str
    name: str = Field(description="Step name as it appears in execution history.")
    kind: str = Field(description='"calibration" runs hardware; "transform" only filters.')
    tasks: list[str] = Field(description="Tasks the step runs, in order; empty for transforms.")


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
    """Whether the spec can run, and what it would do."""

    valid: bool
    problems: list[PipelineProblem] = Field(default_factory=list)
    backend_name: str
    spec: dict[str, Any] | None = Field(
        default=None, description="The normalized spec, when it parsed; defaults filled in."
    )
    targets: ResolvedPipelineTargets | None = None
    steps: list[ResolvedPipelineStep] = Field(default_factory=list)
    task_run_count: int = Field(default=0, description="Task runs per target qubit or coupling.")


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
    default_tasks: list[str]


class PipelineCatalogResponse(BaseModel):
    """Everything needed to write a spec for this project."""

    backend_name: str
    step_types: list[PipelineStepTypeInfo]
    one_qubit_modes: list[str]
    tasks: dict[str, list[str]] = Field(
        description='Available task names by task_type ("qubit", "coupling", ...).'
    )
    spec_schema: dict[str, Any] = Field(description="JSON schema of CalibrationPipelineSpec.")
    example: dict[str, Any] = Field(default_factory=lambda: dict(_SPEC_EXAMPLE))
