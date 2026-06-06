"""API router for user-defined flows and scheduling."""

import json
from collections.abc import Iterator
from logging import getLogger
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from qdash.api.dependencies import (
    get_flow_schedule_service,
    get_flow_service,
)
from qdash.api.lib.project import ProjectContext, get_project_context, get_project_context_editor
from qdash.api.schemas.flow import (
    DeleteScheduleResponse,
    ExecuteFlowRequest,
    ExecuteFlowResponse,
    FlowTemplate,
    FlowTemplateWithCode,
    GetFlowResponse,
    ListFlowSchedulesResponse,
    ListFlowsResponse,
    RunCodexAgentRequest,
    RunCodexAgentResponse,
    SaveFlowRequest,
    SaveFlowResponse,
    ScheduleFlowRequest,
    ScheduleFlowResponse,
    UpdateScheduleRequest,
    UpdateScheduleResponse,
)
from qdash.api.services.flow_schedule_service import FlowScheduleService
from qdash.api.services.flow_service import FlowService

router = APIRouter()
logger = getLogger("uvicorn.app")


# ============================================================================
# Static Path Endpoints (MUST be defined before /flow/{name} to avoid conflicts)
# ============================================================================


@router.post(
    "/flows",
    response_model=SaveFlowResponse,
    summary="Save a flow",
    operation_id="saveFlow",
)
async def save_flow(
    request: SaveFlowRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[FlowService, Depends(get_flow_service)],
) -> SaveFlowResponse:
    """Save a Flow to file system and MongoDB."""
    return await service.save_flow(request, ctx.user.username, ctx.project_id)


@router.get(
    "/flows",
    response_model=ListFlowsResponse,
    summary="List all flows",
    operation_id="listFlows",
)
async def list_flows(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[FlowService, Depends(get_flow_service)],
) -> ListFlowsResponse:
    """List all Flows for the current project."""
    return await service.list_flows(ctx.user.username, ctx.project_id)


# ============================================================================
# Flow Templates Endpoints (static paths - before /flow/{name})
# ============================================================================


@router.get(
    "/flows/templates",
    response_model=list[FlowTemplate],
    summary="List all flow templates",
    operation_id="listFlowTemplates",
)
async def list_flow_templates(
    service: Annotated[FlowService, Depends(get_flow_service)],
) -> list[FlowTemplate]:
    """List all available flow templates."""
    return await service.list_templates()


@router.get(
    "/flows/templates/{template_id}",
    response_model=FlowTemplateWithCode,
    summary="Get a flow template",
    operation_id="getFlowTemplate",
)
async def get_flow_template(
    template_id: str,
    service: Annotated[FlowService, Depends(get_flow_service)],
) -> FlowTemplateWithCode:
    """Get flow template details including code content."""
    return await service.get_template(template_id)


# ============================================================================
# Flow Helper Files Endpoints (static paths - before /flow/{name})
# ============================================================================


@router.get(
    "/flows/helpers",
    response_model=list[str],
    summary="List flow helper files",
    operation_id="listFlowHelperFiles",
)
async def list_flow_helper_files(
    service: Annotated[FlowService, Depends(get_flow_service)],
) -> list[str]:
    """List all Python files in the qdash.workflow.service module."""
    return await service.list_helper_files()


@router.get(
    "/flows/helpers/{filename}",
    response_model=str,
    summary="Get flow helper file content",
    operation_id="getFlowHelperFile",
)
async def get_flow_helper_file(
    filename: str,
    service: Annotated[FlowService, Depends(get_flow_service)],
) -> str:
    """Get the content of a flow helper file."""
    return await service.get_helper_file(filename)


# ============================================================================
# Flow Schedules Endpoints (static paths - before /flow/{name})
# ============================================================================


@router.get(
    "/flows/schedules",
    response_model=ListFlowSchedulesResponse,
    summary="List all flow schedules for current project",
    operation_id="listAllFlowSchedules",
)
async def list_all_flow_schedules(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    schedule_service: Annotated[FlowScheduleService, Depends(get_flow_schedule_service)],
    limit: int = 50,
    offset: int = 0,
) -> ListFlowSchedulesResponse:
    """List all Flow schedules (cron and one-time) for the current project."""
    return await schedule_service.list_all_schedules(
        ctx.user.username, ctx.project_id, limit=limit, offset=offset
    )


@router.delete(
    "/flows/schedules/{schedule_id}",
    response_model=DeleteScheduleResponse,
    summary="Delete a flow schedule",
    operation_id="deleteFlowSchedule",
)
async def delete_flow_schedule(
    schedule_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    schedule_service: Annotated[FlowScheduleService, Depends(get_flow_schedule_service)],
) -> DeleteScheduleResponse:
    """Delete a Flow schedule (cron or one-time)."""
    return await schedule_service.delete_schedule(schedule_id, ctx.user.username, ctx.project_id)


@router.patch(
    "/flows/schedules/{schedule_id}",
    response_model=UpdateScheduleResponse,
    summary="Update a flow schedule",
    operation_id="updateFlowSchedule",
)
async def update_flow_schedule(
    schedule_id: str,
    request: UpdateScheduleRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    schedule_service: Annotated[FlowScheduleService, Depends(get_flow_schedule_service)],
) -> UpdateScheduleResponse:
    """Update a Flow schedule (cron schedules only)."""
    return await schedule_service.update_schedule(
        schedule_id, request, ctx.user.username, ctx.project_id
    )


# ============================================================================
# Dynamic Path Endpoints (/flow/{name} - MUST be after static paths)
# ============================================================================


@router.get(
    "/flows/{name}",
    response_model=GetFlowResponse,
    summary="Get flow details",
    operation_id="getFlow",
)
async def get_flow(
    name: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[FlowService, Depends(get_flow_service)],
) -> GetFlowResponse:
    """Get Flow details including code content."""
    return await service.get_flow(name, ctx.user.username, ctx.project_id)


@router.post(
    "/flows/{name}/execute",
    response_model=ExecuteFlowResponse,
    summary="Execute a flow",
    operation_id="executeFlow",
)
async def execute_flow(
    name: str,
    request: ExecuteFlowRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[FlowService, Depends(get_flow_service)],
) -> ExecuteFlowResponse:
    """Execute a Flow via Prefect deployment."""
    return await service.execute_flow(name, request, ctx.user.username, ctx.project_id)


@router.post(
    "/flows/{name}/agent/codex",
    response_model=RunCodexAgentResponse,
    summary="Edit a flow with host Codex",
    operation_id="runCodexFlowAgent",
)
async def run_codex_flow_agent(
    name: str,
    request: RunCodexAgentRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[FlowService, Depends(get_flow_service)],
) -> RunCodexAgentResponse:
    """Run the host Codex CLI against a temporary copy of a flow."""
    return await service.run_codex_agent(name, request, ctx.project_id)


@router.post(
    "/flows/{name}/agent/codex/stream",
    summary="Stream host Codex flow editing events",
    operation_id="streamCodexFlowAgent",
    include_in_schema=False,
)
async def stream_codex_flow_agent(
    name: str,
    request: RunCodexAgentRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[FlowService, Depends(get_flow_service)],
) -> StreamingResponse:
    """Stream host Codex app-server events as server-sent events."""

    def event_stream() -> Iterator[str]:
        for event in service.stream_codex_agent_events(name, request, ctx.project_id):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.delete(
    "/flows/{name}",
    summary="Delete a flow",
    operation_id="deleteFlow",
)
async def delete_flow(
    name: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[FlowService, Depends(get_flow_service)],
) -> dict[str, str]:
    """Delete a Flow."""
    return await service.delete_flow(name, ctx.user.username, ctx.project_id)


@router.post(
    "/flows/{name}/schedule",
    response_model=ScheduleFlowResponse,
    summary="Schedule a flow execution (cron or one-time)",
    operation_id="scheduleFlow",
)
async def schedule_flow(
    name: str,
    request: ScheduleFlowRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    schedule_service: Annotated[FlowScheduleService, Depends(get_flow_schedule_service)],
) -> ScheduleFlowResponse:
    """Schedule a Flow execution with cron or one-time schedule."""
    return await schedule_service.schedule_flow(name, request, ctx.user.username, ctx.project_id)


@router.get(
    "/flows/{name}/schedules",
    response_model=ListFlowSchedulesResponse,
    summary="List schedules for a specific flow",
    operation_id="listFlowSchedules",
)
async def list_flow_schedules(
    name: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    schedule_service: Annotated[FlowScheduleService, Depends(get_flow_schedule_service)],
    limit: int = 50,
    offset: int = 0,
) -> ListFlowSchedulesResponse:
    """List all schedules (cron and one-time) for a specific Flow."""
    return await schedule_service.list_flow_schedules(
        name, ctx.user.username, ctx.project_id, limit=limit, offset=offset
    )
