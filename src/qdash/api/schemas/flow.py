"""API schemas for user-defined flows."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from qdash.datamodel.flow_targets import FlowTargetOverride, TargetMode


class SaveFlowRequest(BaseModel):
    """Request to save a Flow."""

    name: str = Field(..., description="Flow name (alphanumeric + underscore only)")
    description: str = Field(default="", description="Flow description")
    code: str = Field(..., description="Python code content")
    flow_function_name: str | None = Field(
        None, description="Entry point function name (defaults to same as name if not provided)"
    )
    chip_id: str = Field(..., description="Target chip ID")
    default_parameters: dict[str, Any] = Field(
        default_factory=dict, description="Default execution parameters"
    )
    default_run_parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Default run parameters applied to all tasks (e.g., interval, shots)",
    )
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")
    folder: str | None = Field(
        default=None,
        description=(
            'Folder path inside the creator\'s space, e.g. "daily/t1"; "" is the root.'
            " Omitted keeps an existing flow's folder (a new flow goes to the root)."
        ),
    )
    create_only: bool = Field(
        default=False,
        description=(
            "Create a new flow only. When a flow or flow file with this name already exists"
            " in the project, the request fails with 409 and changes nothing."
            " False (the default) creates the flow or overwrites an existing one."
        ),
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "my_adaptive_calibration",
                    "description": "Adaptive calibration with convergence check",
                    "code": "from prefect import flow\n\n@flow\ndef my_adaptive_calibration():\n    pass",
                    "flow_function_name": "my_adaptive_calibration",
                    "chip_id": "64Qv3",
                    "default_parameters": {"qids": ["32"], "max_iterations": 10},
                    "tags": ["adaptive", "calibration"],
                    "folder": "adaptive",
                }
            ]
        }
    )


class SaveFlowResponse(BaseModel):
    """Response after saving a flow."""

    name: str = Field(..., description="Flow name")
    file_path: str = Field(..., description="Path to saved file")
    message: str = Field(..., description="Success message")


class FlowSummary(BaseModel):
    """Summary of a Flow for listing."""

    name: str = Field(..., description="Flow name")
    created_by: str = Field(..., description="Username of the flow creator")
    description: str = Field(..., description="Flow description")
    chip_id: str = Field(..., description="Target chip ID")
    flow_function_name: str = Field(..., description="Entry point function name")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    tags: list[str] = Field(..., description="Tags")
    folder: str = Field(
        "", description='Folder path inside the creator\'s space, e.g. "daily/t1" (empty = root)'
    )
    file_exists: bool = Field(True, description="Whether the flow source file exists")


class ListFlowsResponse(BaseModel):
    """Response for listing flows."""

    flows: list[FlowSummary] = Field(..., description="List of flow summaries")


def _default_target_modes() -> list[TargetMode]:
    return ["mux_ids", "qids"]


class GetFlowResponse(BaseModel):
    """Response for getting flow details."""

    target_defaults: FlowTargetOverride | None = Field(
        None, description="Statically resolved source targets; null when dynamic or ambiguous"
    )
    target_modes: list[TargetMode] = Field(
        default_factory=_default_target_modes,
        description="Target override types this flow accepts for one execution",
    )
    name: str = Field(..., description="Flow name")
    created_by: str = Field(..., description="Username of the flow creator")
    description: str = Field(..., description="Flow description")
    code: str = Field(..., description="Python code content")
    flow_function_name: str = Field(..., description="Entry point function name")
    chip_id: str = Field(..., description="Target chip ID")
    default_parameters: dict[str, Any] = Field(..., description="Default parameters")
    default_run_parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Default run parameters applied to all tasks",
    )
    file_path: str = Field(..., description="Path to file")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    tags: list[str] = Field(..., description="Tags")
    folder: str = Field(
        "", description='Folder path inside the creator\'s space, e.g. "daily/t1" (empty = root)'
    )


class ExecutionPlanIssue(BaseModel):
    """One problem that stops a step's manual rounds from running."""

    round: int | None = Field(None, description="1-based round; null for the whole step")
    targets: list[str] = Field(
        default_factory=list, description="Qubit IDs or control-target pairs involved"
    )
    message: str


class ExecutionPlanRound(BaseModel):
    """One manual round exactly as the source writes it."""

    number: int = Field(..., description="1-based position; rounds run in this order")
    targets: list[str] = Field(
        ..., description="Qubit IDs, or control-target pairs such as 0-1, in source order"
    )


class ExecutionPlanStep(BaseModel):
    """One step of a CalibService run, as stated in the saved source."""

    index: int = Field(..., description="1-based position within its run")
    type: str = Field(..., description="Step class, e.g. CustomOneQubit")
    name: str = Field(..., description="Step name and step_id")
    scope: Literal["qubit", "coupling", "none"] = Field(
        ..., description="What one target of the step is"
    )
    execution_mode: str | None = None
    schedule: Literal["manual", "automatic", "none"] = Field(
        ...,
        description=(
            "manual: the exact rounds of the source, checked before execution. "
            "automatic: groups are formed by the scheduler at run time. "
            "none: the step does not schedule targets."
        ),
    )
    rounds: list[ExecutionPlanRound] = Field(default_factory=list)
    tasks: list[str] | None = Field(
        None, description="Task names in call order; null when not stated literally"
    )
    summary: str = Field(..., description="How the step's targets wait for each other")
    issues: list[ExecutionPlanIssue] = Field(default_factory=list)
    unchecked: list[str] = Field(
        default_factory=list,
        description="Checks that could not run here; the worker runs them before the step",
    )


class ExecutionPlanRun(BaseModel):
    """One CalibService.run call of the entrypoint."""

    targets: FlowTargetOverride | None = Field(
        None, description="Literal targets of the call; null when computed at run time"
    )
    steps: list[ExecutionPlanStep]


class FlowExecutionPlanResponse(BaseModel):
    """What the saved source of a flow states about its execution, without running it."""

    flow_name: str
    chip_id: str
    source_updated_at: datetime = Field(
        ..., description="Version of the saved source the plan was read from"
    )
    status: Literal["resolved", "unresolved", "invalid"] = Field(
        ...,
        description=(
            "resolved: every run and step was read from literals. unresolved: the source "
            "decides its steps at run time; reason says why. invalid: manual rounds that "
            "cannot run were found; execution would fail before measuring."
        ),
    )
    reason: str | None = Field(None, description="Why the plan is unresolved")
    runs: list[ExecutionPlanRun] = Field(default_factory=list)
    issues: list[ExecutionPlanIssue] = Field(
        default_factory=list,
        description="Problems of manual steps found outside a resolved plan",
    )
    has_manual_rounds: bool = Field(
        False, description="Whether the source writes execution_mode='manual' on a step"
    )
    target_override_allowed: bool = True
    target_override_reason: str | None = None


class MoveFlowRequest(BaseModel):
    """Request to move a Flow to another folder of its creator's space."""

    folder: str = Field(
        ..., description='Target folder path, e.g. "daily/t1"; "" moves the flow to the root'
    )


class MoveFlowResponse(BaseModel):
    """Response after moving a flow."""

    name: str = Field(..., description="Flow name")
    folder: str = Field(..., description="The folder the flow now sits in")
    message: str = Field(..., description="Success message")


class ExecuteFlowRequest(BaseModel):
    """Request to execute a Flow."""

    target_override: FlowTargetOverride | None = Field(
        None,
        description="Targets for this run, overriding direct CalibService and pipeline targets",
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Execution parameters (overrides default_parameters)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"parameters": {"qids": ["32", "38"], "max_iterations": 5}}]
        }
    )


class ExecuteFlowResponse(BaseModel):
    """Response after executing a flow."""

    execution_id: str = Field(
        ...,
        description=(
            "QDash execution ID (falls back to the Prefect flow run ID"
            " when no execution row could be pre-created)"
        ),
    )
    flow_run_id: str = Field(..., description="Prefect flow run ID")
    flow_run_url: str = Field(..., description="Prefect flow run URL")
    qdash_ui_url: str = Field(..., description="QDash UI URL for execution")
    message: str = Field(..., description="Success message")


class ScheduleFlowRequest(BaseModel):
    """Request to schedule a Flow execution."""

    cron: str | None = Field(
        None, description="Cron expression (e.g., '0 2 * * *' for daily at 2am JST)"
    )
    scheduled_time: str | None = Field(
        None, description="One-time execution time (ISO format, JST)"
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Execution parameters (overrides default_parameters)"
    )
    active: bool = Field(True, description="Whether the schedule is active")
    timezone: str = Field("Asia/Tokyo", description="Timezone for schedule")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "cron": "0 2 * * *",
                    "parameters": {"qids": ["32"], "max_iterations": 10},
                    "active": True,
                    "timezone": "Asia/Tokyo",
                },
                {
                    "scheduled_time": "2025-11-01T02:00:00+09:00",
                    "parameters": {"qids": ["32"]},
                    "active": True,
                },
            ]
        }
    )


class ScheduleFlowResponse(BaseModel):
    """Response after scheduling a flow."""

    schedule_id: str = Field(
        ..., description="Schedule ID (deployment ID for cron, flow_run_id for one-time)"
    )
    flow_name: str = Field(..., description="Flow name")
    schedule_type: str = Field(..., description="Schedule type: 'cron' or 'one-time'")
    cron: str | None = Field(None, description="Cron expression (for cron schedules)")
    next_run: datetime | None = Field(None, description="Next scheduled run time")
    active: bool = Field(..., description="Whether the schedule is active")
    message: str = Field(..., description="Success message")


class FlowScheduleSummary(BaseModel):
    """Summary of a scheduled Flow."""

    schedule_id: str = Field(..., description="Schedule ID")
    flow_name: str = Field(..., description="Flow name")
    schedule_type: str = Field(..., description="Schedule type: 'cron' or 'one-time'")
    cron: str | None = Field(None, description="Cron expression")
    next_run: datetime | None = Field(None, description="Next scheduled run time")
    active: bool = Field(..., description="Whether the schedule is active")
    created_at: datetime = Field(..., description="Schedule creation time")
    chip_id: str | None = Field(None, description="Target chip ID of the schedule, when known")


class ListFlowSchedulesResponse(BaseModel):
    """Response for listing flow schedules."""

    schedules: list[FlowScheduleSummary] = Field(..., description="List of flow schedules")


class UpdateScheduleRequest(BaseModel):
    """Request to update a schedule."""

    active: bool = Field(..., description="Whether the schedule is active")
    cron: str | None = Field(None, description="Updated cron expression (optional)")
    parameters: dict[str, Any] | None = Field(None, description="Updated parameters (optional)")
    timezone: str = Field(default="Asia/Tokyo", description="Timezone for cron schedule")


class DeleteScheduleResponse(BaseModel):
    """Response for deleting a schedule."""

    message: str = Field(..., description="Success message")
    schedule_id: str = Field(..., description="Deleted schedule ID")
    schedule_type: str = Field(..., description="Type of deleted schedule (cron or one-time)")


class UpdateScheduleResponse(BaseModel):
    """Response for updating a schedule."""

    message: str = Field(..., description="Success message")
    schedule_id: str = Field(..., description="Updated schedule ID")


class FlowTemplate(BaseModel):
    """Flow template metadata."""

    id: str = Field(..., description="Template ID")
    name: str = Field(..., description="Template name")
    description: str = Field(..., description="Template description")
    category: str = Field(..., description="Template category")
    backend: str = Field(..., description="Backend the template's tasks run on, e.g. qubex or fake")
    filename: str = Field(..., description="Python filename")
    function_name: str = Field(..., description="Flow function name")


class FlowTemplateWithCode(FlowTemplate):
    """Flow template with code content."""

    code: str = Field(..., description="Python code content")


# =============================================================================
# Importable Modules (for editor sidebar)
# =============================================================================


class ImportableFunction(BaseModel):
    """A function that can be imported and used in user flows."""

    name: str = Field(..., description="Function name")
    description: str = Field(..., description="Function description (from docstring)")
    signature: str = Field(..., description="Function signature")
    module: str = Field(..., description="Module path for import")
    example: str | None = Field(None, description="Usage example")


class ImportableClass(BaseModel):
    """A class that can be imported and used in user flows."""

    name: str = Field(..., description="Class name")
    description: str = Field(..., description="Class description (from docstring)")
    module: str = Field(..., description="Module path for import")
    methods: list[str] = Field(default_factory=list, description="Key methods")


class ImportableModule(BaseModel):
    """A module category containing importable items."""

    name: str = Field(..., description="Module category name")
    description: str = Field(..., description="Module category description")
    import_path: str = Field(..., description="Python import path")
    functions: list[ImportableFunction] = Field(
        default_factory=list, description="Available functions"
    )
    classes: list[ImportableClass] = Field(default_factory=list, description="Available classes")


class ListImportableModulesResponse(BaseModel):
    """Response for listing importable modules."""

    modules: list[ImportableModule] = Field(..., description="List of importable modules")
