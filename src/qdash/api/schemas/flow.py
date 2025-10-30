"""API schemas for user-defined flows."""

from typing import Any, ClassVar

from pydantic import BaseModel, Field


class SaveFlowRequest(BaseModel):
    """Request to save a Flow."""

    name: str = Field(..., description="Flow name (alphanumeric + underscore only)")
    description: str = Field(default="", description="Flow description")
    code: str = Field(..., description="Python code content")
    flow_function_name: str | None = Field(
        None, description="Entry point function name (defaults to same as name if not provided)"
    )
    chip_id: str = Field(..., description="Target chip ID")
    default_parameters: dict[str, Any] = Field(default_factory=dict, description="Default execution parameters")
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")

    model_config: ClassVar[dict] = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "my_adaptive_calibration",
                    "description": "Adaptive calibration with convergence check",
                    "code": "from prefect import flow\n\n@flow\ndef my_adaptive_calibration():\n    pass",
                    "flow_function_name": "my_adaptive_calibration",
                    "chip_id": "64Qv3",
                    "default_parameters": {"qids": ["32"], "max_iterations": 10},
                    "tags": ["adaptive", "calibration"],
                }
            ]
        }
    }


class SaveFlowResponse(BaseModel):
    """Response after saving a flow."""

    name: str = Field(..., description="Flow name")
    file_path: str = Field(..., description="Path to saved file")
    message: str = Field(..., description="Success message")


class FlowSummary(BaseModel):
    """Summary of a Flow for listing."""

    name: str = Field(..., description="Flow name")
    description: str = Field(..., description="Flow description")
    chip_id: str = Field(..., description="Target chip ID")
    flow_function_name: str = Field(..., description="Entry point function name")
    created_at: str = Field(..., description="Creation timestamp (ISO format)")
    updated_at: str = Field(..., description="Last update timestamp (ISO format)")
    tags: list[str] = Field(..., description="Tags")


class ListFlowsResponse(BaseModel):
    """Response for listing flows."""

    flows: list[FlowSummary] = Field(..., description="List of flow summaries")


class GetFlowResponse(BaseModel):
    """Response for getting flow details."""

    name: str = Field(..., description="Flow name")
    description: str = Field(..., description="Flow description")
    code: str = Field(..., description="Python code content")
    flow_function_name: str = Field(..., description="Entry point function name")
    chip_id: str = Field(..., description="Target chip ID")
    default_parameters: dict[str, Any] = Field(..., description="Default parameters")
    file_path: str = Field(..., description="Path to file")
    created_at: str = Field(..., description="Creation timestamp (ISO format)")
    updated_at: str = Field(..., description="Last update timestamp (ISO format)")
    tags: list[str] = Field(..., description="Tags")


class ExecuteFlowRequest(BaseModel):
    """Request to execute a Flow."""

    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Execution parameters (overrides default_parameters)"
    )

    model_config: ClassVar[dict] = {
        "json_schema_extra": {"examples": [{"parameters": {"qids": ["32", "38"], "max_iterations": 5}}]}
    }


class ExecuteFlowResponse(BaseModel):
    """Response after executing a flow."""

    execution_id: str = Field(..., description="Execution ID")
    flow_run_url: str = Field(..., description="Prefect flow run URL")
    qdash_ui_url: str = Field(..., description="QDash UI URL for execution")
    message: str = Field(..., description="Success message")


class ScheduleFlowRequest(BaseModel):
    """Request to schedule a Flow execution."""

    cron: str | None = Field(None, description="Cron expression (e.g., '0 2 * * *' for daily at 2am JST)")
    scheduled_time: str | None = Field(None, description="One-time execution time (ISO format, JST)")
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Execution parameters (overrides default_parameters)"
    )
    active: bool = Field(True, description="Whether the schedule is active")
    timezone: str = Field("Asia/Tokyo", description="Timezone for schedule")

    model_config: ClassVar[dict] = {
        "json_schema_extra": {
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
    }


class ScheduleFlowResponse(BaseModel):
    """Response after scheduling a flow."""

    schedule_id: str = Field(..., description="Schedule ID (deployment ID for cron, flow_run_id for one-time)")
    flow_name: str = Field(..., description="Flow name")
    schedule_type: str = Field(..., description="Schedule type: 'cron' or 'one-time'")
    cron: str | None = Field(None, description="Cron expression (for cron schedules)")
    next_run: str | None = Field(None, description="Next scheduled run time (ISO format)")
    active: bool = Field(..., description="Whether the schedule is active")
    message: str = Field(..., description="Success message")


class FlowScheduleSummary(BaseModel):
    """Summary of a scheduled Flow."""

    schedule_id: str = Field(..., description="Schedule ID")
    flow_name: str = Field(..., description="Flow name")
    schedule_type: str = Field(..., description="Schedule type: 'cron' or 'one-time'")
    cron: str | None = Field(None, description="Cron expression")
    next_run: str | None = Field(None, description="Next scheduled run time")
    active: bool = Field(..., description="Whether the schedule is active")
    created_at: str = Field(..., description="Schedule creation time")


class ListFlowSchedulesResponse(BaseModel):
    """Response for listing flow schedules."""

    schedules: list[FlowScheduleSummary] = Field(..., description="List of flow schedules")


class UpdateScheduleRequest(BaseModel):
    """Request to update a schedule."""

    active: bool = Field(..., description="Whether the schedule is active")
    cron: str | None = Field(None, description="Updated cron expression (optional)")
    parameters: dict[str, Any] | None = Field(None, description="Updated parameters (optional)")
