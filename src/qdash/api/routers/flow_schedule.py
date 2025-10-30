"""API router for Flow scheduling (cron and one-time schedules)."""

import uuid
from datetime import datetime
from logging import getLogger
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from prefect import get_client
from prefect.client.schemas.filters import (
    DeploymentFilter,
    FlowRunFilter,
    FlowRunFilterState,
    FlowRunFilterStateType,
    StateType,
)
from qdash.api.lib.auth import get_current_active_user
from qdash.api.schemas.auth import User
from qdash.api.schemas.flow import (
    FlowScheduleSummary,
    ListFlowSchedulesResponse,
    ScheduleFlowRequest,
    ScheduleFlowResponse,
    UpdateScheduleRequest,
)
from qdash.dbmodel.flow import FlowDocument

router = APIRouter()
logger = getLogger("uvicorn.app")

# Deployment service URL
DEPLOYMENT_SERVICE_URL = "http://deployment-service:8001"


@router.post(
    "/flow/{name}/schedule",
    response_model=ScheduleFlowResponse,
    summary="Schedule a Flow execution (cron or one-time)",
    operation_id="schedule_flow",
)
async def schedule_flow(
    name: str,
    request: ScheduleFlowRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> ScheduleFlowResponse:
    """Schedule a Flow execution with cron or one-time schedule.

    Args:
    ----
        name: Flow name
        request: Schedule request (must provide either cron or scheduled_time)
        current_user: Current authenticated user

    Returns:
    -------
        Schedule response with schedule_id and details

    """
    username = current_user.username

    # Validate request
    if not request.cron and not request.scheduled_time:
        raise HTTPException(
            status_code=400,
            detail="Either 'cron' or 'scheduled_time' must be provided",
        )
    if request.cron and request.scheduled_time:
        raise HTTPException(
            status_code=400,
            detail="Cannot provide both 'cron' and 'scheduled_time'",
        )

    # Find flow
    flow = FlowDocument.find_by_user_and_name(username, name)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{name}' not found")

    if not flow.deployment_id:
        raise HTTPException(
            status_code=400,
            detail=f"Flow '{name}' has no deployment. Please re-save the flow.",
        )

    # Verify deployment exists in Prefect
    try:
        async with get_client() as prefect_client:
            await prefect_client.read_deployment(flow.deployment_id)
            logger.info(f"Verified deployment {flow.deployment_id} exists in Prefect")
    except Exception as e:
        logger.error(f"Deployment {flow.deployment_id} not found in Prefect: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Flow '{name}' deployment not found in Prefect. Please re-save the flow. Error: {str(e)}",
        )

    # Merge parameters
    parameters: dict[str, Any] = {
        **flow.default_parameters,
        **request.parameters,
        "flow_name": name,
    }

    # Handle cron schedule
    if request.cron:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{DEPLOYMENT_SERVICE_URL}/set-schedule",
                    json={
                        "deployment_id": flow.deployment_id,
                        "cron": request.cron,
                        "timezone": request.timezone,
                        "active": request.active,
                        "parameters": parameters,
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

                logger.info(f"Set cron schedule for flow '{name}': {request.cron}")

                # Get next run time from Prefect
                async with get_client() as prefect_client:
                    deployment = await prefect_client.read_deployment(flow.deployment_id)
                    next_run = None
                    if deployment.schedule:
                        # Calculate next run (simplified - Prefect handles this internally)
                        next_run = datetime.now().isoformat()

                return ScheduleFlowResponse(
                    schedule_id=flow.deployment_id,
                    flow_name=name,
                    schedule_type="cron",
                    cron=request.cron,
                    next_run=next_run,
                    active=request.active,
                    message=f"Cron schedule set successfully for flow '{name}'",
                )

        except httpx.HTTPStatusError as e:
            # Get detailed error from deployment service
            error_detail = e.response.text if hasattr(e.response, "text") else str(e)
            logger.error(f"Failed to set cron schedule: {error_detail}")
            raise HTTPException(
                status_code=e.response.status_code if hasattr(e, "response") else 500,
                detail=f"Failed to set cron schedule: {error_detail}",
            )
        except httpx.HTTPError as e:
            logger.error(f"Failed to set cron schedule (network error): {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to set cron schedule (network error): {e}",
            )

    # Handle one-time schedule
    if request.scheduled_time:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{DEPLOYMENT_SERVICE_URL}/create-scheduled-run",
                    json={
                        "deployment_id": flow.deployment_id,
                        "scheduled_time": request.scheduled_time,
                        "parameters": parameters,
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

                flow_run_id = data["flow_run_id"]
                logger.info(f"Created one-time schedule for flow '{name}': {request.scheduled_time}")

                return ScheduleFlowResponse(
                    schedule_id=flow_run_id,
                    flow_name=name,
                    schedule_type="one-time",
                    cron=None,
                    next_run=request.scheduled_time,
                    active=True,
                    message=f"One-time schedule created successfully for flow '{name}'",
                )

        except httpx.HTTPStatusError as e:
            # Get detailed error from deployment service
            error_detail = e.response.text if hasattr(e.response, "text") else str(e)
            logger.error(f"Failed to create one-time schedule: {error_detail}")
            raise HTTPException(
                status_code=e.response.status_code if hasattr(e, "response") else 500,
                detail=f"Failed to create one-time schedule: {error_detail}",
            )
        except httpx.HTTPError as e:
            logger.error(f"Failed to create one-time schedule (network error): {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create one-time schedule (network error): {e}",
            )

    raise HTTPException(status_code=500, detail="Unexpected error in schedule creation")


@router.get(
    "/flow/{name}/schedules",
    response_model=ListFlowSchedulesResponse,
    summary="List schedules for a specific Flow",
    operation_id="list_flow_schedules",
)
async def list_flow_schedules(
    name: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> ListFlowSchedulesResponse:
    """List all schedules (cron and one-time) for a specific Flow.

    Args:
    ----
        name: Flow name
        current_user: Current authenticated user

    Returns:
    -------
        List of schedules for the flow

    """
    username = current_user.username

    # Find flow
    flow = FlowDocument.find_by_user_and_name(username, name)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{name}' not found")

    if not flow.deployment_id:
        return ListFlowSchedulesResponse(schedules=[])

    schedules: list[FlowScheduleSummary] = []

    async with get_client() as client:
        # Get cron schedule from deployment (show all, including inactive)
        try:
            deployment = await client.read_deployment(flow.deployment_id)
            # Show all schedules that exist (active and inactive)
            if deployment.schedule and hasattr(deployment.schedule, "cron"):
                schedules.append(
                    FlowScheduleSummary(
                        schedule_id=flow.deployment_id,
                        flow_name=name,
                        schedule_type="cron",
                        cron=deployment.schedule.cron,
                        next_run=None,  # Prefect calculates this internally
                        active=deployment.is_schedule_active,
                        created_at=deployment.created.isoformat() if deployment.created else "",
                    )
                )
        except Exception as e:
            logger.warning(f"Failed to read deployment schedule: {e}")

        # Get one-time scheduled runs (future only)
        try:
            from datetime import datetime, timezone

            state_filter = FlowRunFilterStateType(any_=[StateType.SCHEDULED])
            flow_runs = await client.read_flow_runs(
                deployment_filter=DeploymentFilter(id={"any_": [uuid.UUID(flow.deployment_id)]}),
                flow_run_filter=FlowRunFilter(state=FlowRunFilterState(type=state_filter)),
                limit=20,  # Limit to 20 most recent scheduled runs
            )

            now = datetime.now(timezone.utc)
            for flow_run in flow_runs:
                # Only show future scheduled runs
                if flow_run.next_scheduled_start_time and flow_run.next_scheduled_start_time > now:
                    schedules.append(
                        FlowScheduleSummary(
                            schedule_id=str(flow_run.id),
                            flow_name=name,
                            schedule_type="one-time",
                            cron=None,
                            next_run=flow_run.next_scheduled_start_time.isoformat(),
                            active=True,
                            created_at=flow_run.created.isoformat() if flow_run.created else "",
                        )
                    )
        except Exception as e:
            logger.warning(f"Failed to read scheduled flow runs: {e}")

    return ListFlowSchedulesResponse(schedules=schedules)


@router.get(
    "/flow-schedules",
    response_model=ListFlowSchedulesResponse,
    summary="List all Flow schedules for current user",
    operation_id="list_all_flow_schedules",
)
async def list_all_flow_schedules(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> ListFlowSchedulesResponse:
    """List all Flow schedules (cron and one-time) for the current user.

    Args:
    ----
        current_user: Current authenticated user

    Returns:
    -------
        List of all flow schedules

    """
    username = current_user.username
    flows = FlowDocument.list_by_user(username)

    all_schedules: list[FlowScheduleSummary] = []

    async with get_client() as client:
        for flow in flows:
            if not flow.deployment_id:
                continue

            # Get cron schedule (show all, including inactive)
            try:
                deployment = await client.read_deployment(flow.deployment_id)
                # Show all schedules that exist (active and inactive)
                if deployment.schedule and hasattr(deployment.schedule, "cron"):
                    all_schedules.append(
                        FlowScheduleSummary(
                            schedule_id=flow.deployment_id,
                            flow_name=flow.name,
                            schedule_type="cron",
                            cron=deployment.schedule.cron,
                            next_run=None,
                            active=deployment.is_schedule_active,
                            created_at=deployment.created.isoformat() if deployment.created else "",
                        )
                    )
            except Exception as e:
                logger.warning(f"Failed to read deployment schedule for {flow.name}: {e}")

            # Get one-time scheduled runs (future only)
            try:
                from datetime import datetime, timezone

                state_filter = FlowRunFilterStateType(any_=[StateType.SCHEDULED])
                flow_runs = await client.read_flow_runs(
                    deployment_filter=DeploymentFilter(id={"any_": [uuid.UUID(flow.deployment_id)]}),
                    flow_run_filter=FlowRunFilter(state=FlowRunFilterState(type=state_filter)),
                    limit=20,  # Limit per deployment
                )

                now = datetime.now(timezone.utc)
                for flow_run in flow_runs:
                    # Only show future scheduled runs
                    if flow_run.next_scheduled_start_time and flow_run.next_scheduled_start_time > now:
                        all_schedules.append(
                            FlowScheduleSummary(
                                schedule_id=str(flow_run.id),
                                flow_name=flow.name,
                                schedule_type="one-time",
                                cron=None,
                                next_run=flow_run.next_scheduled_start_time.isoformat(),
                                active=True,
                                created_at=flow_run.created.isoformat() if flow_run.created else "",
                            )
                        )
            except Exception as e:
                logger.warning(f"Failed to read scheduled flow runs for {flow.name}: {e}")

    # Sort by next_run time
    all_schedules.sort(key=lambda x: x.next_run or "")

    return ListFlowSchedulesResponse(schedules=all_schedules)


@router.delete(
    "/flow-schedule/{schedule_id}",
    summary="Delete a Flow schedule",
    operation_id="delete_flow_schedule",
)
async def delete_flow_schedule(
    schedule_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict[str, str]:
    """Delete a Flow schedule (cron or one-time).

    For cron schedules: Deactivates the schedule on the deployment.
    For one-time schedules: Deletes the scheduled flow run.

    Args:
    ----
        schedule_id: Schedule ID (deployment_id for cron, flow_run_id for one-time)
        current_user: Current authenticated user

    Returns:
    -------
        Success message

    """
    username = current_user.username

    async with get_client() as client:
        # Try as deployment ID (cron schedule)
        try:
            _ = await client.read_deployment(schedule_id)

            # Verify ownership
            flow = FlowDocument.find_one({"deployment_id": schedule_id, "username": username}).run()
            if not flow:
                raise HTTPException(
                    status_code=403,
                    detail="You don't have permission to delete this schedule",
                )

            # Remove schedule completely
            deployment = await client.read_deployment(schedule_id)

            await client.update_deployment(
                deployment=deployment,
                schedule=None,  # Remove the schedule
                is_schedule_active=False,
            )

            logger.info(f"Deleted cron schedule: {schedule_id}")
            return {"message": "Cron schedule deleted successfully"}

        except Exception:
            pass

        # Try as flow_run_id (one-time schedule)
        try:
            flow_run_id = uuid.UUID(schedule_id)
            flow_run = await client.read_flow_run(flow_run_id)

            # Verify ownership through deployment
            if flow_run.deployment_id:
                flow = FlowDocument.find_one({"deployment_id": str(flow_run.deployment_id), "username": username}).run()
                if not flow:
                    raise HTTPException(
                        status_code=403,
                        detail="You don't have permission to delete this schedule",
                    )

            await client.delete_flow_run(flow_run_id)
            logger.info(f"Deleted one-time schedule: {schedule_id}")
            return {"message": "One-time schedule deleted successfully"}

        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid schedule_id format")
        except Exception as e:
            logger.error(f"Failed to delete schedule: {e}")
            raise HTTPException(status_code=404, detail="Schedule not found")


@router.patch(
    "/flow-schedule/{schedule_id}",
    response_model=dict[str, str],
    summary="Update a Flow schedule",
    operation_id="update_flow_schedule",
)
async def update_flow_schedule(
    schedule_id: str,
    request: UpdateScheduleRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict[str, str]:
    """Update a Flow schedule (cron schedules only).

    Can update: active status, cron expression, parameters.

    Args:
    ----
        schedule_id: Schedule ID (deployment_id)
        request: Update request
        current_user: Current authenticated user

    Returns:
    -------
        Success message

    """
    username = current_user.username

    async with get_client() as client:
        try:
            # Verify ownership
            flow = FlowDocument.find_one({"deployment_id": schedule_id, "username": username}).run()
            if not flow:
                raise HTTPException(
                    status_code=403,
                    detail="You don't have permission to update this schedule",
                )

            # Read deployment for update
            deployment = await client.read_deployment(schedule_id)

            # Prepare schedule if cron is provided
            schedule_to_update = deployment.schedule
            if request.cron:
                from prefect.client.schemas.schedules import CronSchedule

                schedule_to_update = CronSchedule(cron=request.cron, timezone="Asia/Tokyo")

            # Update deployment directly without creating new Deployment object
            await client.update_deployment(
                deployment=deployment,
                schedule=schedule_to_update,
                is_schedule_active=request.active,
            )

            logger.info(f"Updated schedule: {schedule_id}")
            return {"message": "Schedule updated successfully"}

        except Exception as e:
            logger.error(f"Failed to update schedule: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to update schedule: {e}")
