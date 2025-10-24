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
