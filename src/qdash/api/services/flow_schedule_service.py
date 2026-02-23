"""Service for flow scheduling operations."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import httpx
from croniter import croniter
from fastapi import HTTPException
from prefect import get_client
from prefect.client.schemas.filters import (
    DeploymentFilter,
    FlowRunFilter,
    FlowRunFilterState,
    FlowRunFilterStateType,
    StateType,
)
from qdash.api.schemas.flow import (
    DeleteScheduleResponse,
    FlowScheduleSummary,
    ListFlowSchedulesResponse,
    ScheduleFlowRequest,
    ScheduleFlowResponse,
    UpdateScheduleRequest,
    UpdateScheduleResponse,
)

if TYPE_CHECKING:
    from qdash.repository import MongoFlowRepository

logger = logging.getLogger("uvicorn.app")

DEPLOYMENT_SERVICE_URL = os.getenv("DEPLOYMENT_SERVICE_URL", "http://deployment-service:8001")
DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)


class FlowScheduleService:
    """Service for flow schedule management (cron and one-time)."""

    def __init__(
        self,
        flow_repository: MongoFlowRepository,
    ) -> None:
        """Initialize the service with a flow repository."""
        self._flow_repo = flow_repository

    async def schedule_flow(
        self,
        name: str,
        request: ScheduleFlowRequest,
        username: str,
        project_id: str,
    ) -> ScheduleFlowResponse:
        """Schedule a Flow execution with cron or one-time schedule.

        Parameters
        ----------
        name : str
            Flow name.
        request : ScheduleFlowRequest
            Schedule request.
        username : str
            The username.
        project_id : str
            The project ID.

        Returns
        -------
        ScheduleFlowResponse
            Schedule response with schedule_id and details.

        """
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

        flow = self._flow_repo.find_by_user_and_name(username, name, project_id)
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
                detail=(
                    f"Flow '{name}' deployment not found in Prefect."
                    f" Please re-save the flow. Error: {e!s}"
                ),
            )

        # Merge parameters
        parameters: dict[str, Any] = {
            "username": username,
            "chip_id": flow.chip_id,
            **flow.default_parameters,
            **request.parameters,
            "flow_name": name,
            "project_id": project_id,
        }
        if "tags" not in parameters and flow.tags:
            parameters["tags"] = flow.tags

        logger.info(f"Scheduling flow '{name}' with parameters: {parameters}")

        if request.cron:
            return await self._schedule_cron(name, request, flow.deployment_id, parameters)

        if request.scheduled_time:
            return await self._schedule_one_time(name, request, flow.deployment_id, parameters)

        raise HTTPException(status_code=500, detail="Unexpected error in schedule creation")

    async def list_all_schedules(
        self,
        username: str,
        project_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> ListFlowSchedulesResponse:
        """List all Flow schedules for the current project.

        Parameters
        ----------
        username : str
            The username.
        project_id : str
            The project ID.
        limit : int
            Maximum number of schedules (max 100).
        offset : int
            Number to skip.

        Returns
        -------
        ListFlowSchedulesResponse
            List of all flow schedules.

        """
        limit = min(limit, 100)
        flows = self._flow_repo.list_by_user(username, project_id)

        all_schedules: list[FlowScheduleSummary] = []

        async with get_client() as client:
            for flow in flows:
                if not flow.deployment_id:
                    continue

                # Get cron schedule
                try:
                    deployment = await client.read_deployment(flow.deployment_id)
                    if deployment.schedule and hasattr(deployment.schedule, "cron"):
                        all_schedules.append(
                            FlowScheduleSummary(
                                schedule_id=flow.deployment_id,
                                flow_name=flow.name,
                                schedule_type="cron",
                                cron=deployment.schedule.cron,
                                next_run=None,
                                active=deployment.is_schedule_active,
                                created_at=deployment.created or datetime.now(timezone.utc),
                            )
                        )
                except Exception as e:
                    logger.warning(f"Failed to read deployment schedule for {flow.name}: {e}")

                # Get one-time scheduled runs
                try:
                    state_filter = FlowRunFilterStateType(any_=[StateType.SCHEDULED])
                    flow_runs = await client.read_flow_runs(
                        deployment_filter=DeploymentFilter(
                            id={"any_": [uuid.UUID(flow.deployment_id)]}
                        ),
                        flow_run_filter=FlowRunFilter(state=FlowRunFilterState(type=state_filter)),
                        limit=limit,
                    )

                    now = datetime.now(timezone.utc)
                    for flow_run in flow_runs:
                        if (
                            flow_run.next_scheduled_start_time
                            and flow_run.next_scheduled_start_time > now
                        ):
                            all_schedules.append(
                                FlowScheduleSummary(
                                    schedule_id=str(flow_run.id),
                                    flow_name=flow.name,
                                    schedule_type="one-time",
                                    cron=None,
                                    next_run=flow_run.next_scheduled_start_time,
                                    active=True,
                                    created_at=flow_run.created or datetime.now(timezone.utc),
                                )
                            )
                except Exception as e:
                    logger.warning(f"Failed to read scheduled flow runs for {flow.name}: {e}")

        all_schedules.sort(
            key=lambda x: (
                x.next_run is None,
                x.next_run or datetime.min.replace(tzinfo=timezone.utc),
            )
        )

        paginated_schedules = all_schedules[offset : offset + limit]
        return ListFlowSchedulesResponse(schedules=paginated_schedules)

    async def list_flow_schedules(
        self,
        name: str,
        username: str,
        project_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> ListFlowSchedulesResponse:
        """List all schedules for a specific Flow.

        Parameters
        ----------
        name : str
            Flow name.
        username : str
            The username.
        project_id : str
            The project ID.
        limit : int
            Maximum number (max 100).
        offset : int
            Number to skip.

        Returns
        -------
        ListFlowSchedulesResponse
            List of schedules for the flow.

        """
        limit = min(limit, 100)

        flow = self._flow_repo.find_by_user_and_name(username, name, project_id)
        if not flow:
            raise HTTPException(status_code=404, detail=f"Flow '{name}' not found")

        if not flow.deployment_id:
            return ListFlowSchedulesResponse(schedules=[])

        schedules: list[FlowScheduleSummary] = []

        async with get_client() as client:
            try:
                deployment = await client.read_deployment(flow.deployment_id)
                if deployment.schedule and hasattr(deployment.schedule, "cron"):
                    schedules.append(
                        FlowScheduleSummary(
                            schedule_id=flow.deployment_id,
                            flow_name=name,
                            schedule_type="cron",
                            cron=deployment.schedule.cron,
                            next_run=None,
                            active=deployment.is_schedule_active,
                            created_at=deployment.created or datetime.now(timezone.utc),
                        )
                    )
            except Exception as e:
                logger.warning(f"Failed to read deployment schedule: {e}")

            try:
                state_filter = FlowRunFilterStateType(any_=[StateType.SCHEDULED])
                flow_runs = await client.read_flow_runs(
                    deployment_filter=DeploymentFilter(
                        id={"any_": [uuid.UUID(flow.deployment_id)]}
                    ),
                    flow_run_filter=FlowRunFilter(state=FlowRunFilterState(type=state_filter)),
                    limit=limit,
                    offset=offset,
                )

                now = datetime.now(timezone.utc)
                for flow_run in flow_runs:
                    if (
                        flow_run.next_scheduled_start_time
                        and flow_run.next_scheduled_start_time > now
                    ):
                        schedules.append(
                            FlowScheduleSummary(
                                schedule_id=str(flow_run.id),
                                flow_name=name,
                                schedule_type="one-time",
                                cron=None,
                                next_run=flow_run.next_scheduled_start_time,
                                active=True,
                                created_at=flow_run.created or datetime.now(timezone.utc),
                            )
                        )
            except Exception as e:
                logger.warning(f"Failed to read scheduled flow runs: {e}")

        return ListFlowSchedulesResponse(schedules=schedules)

    async def update_schedule(
        self,
        schedule_id: str,
        request: UpdateScheduleRequest,
        username: str,
        project_id: str,
    ) -> UpdateScheduleResponse:
        """Update a Flow schedule (cron schedules only).

        Parameters
        ----------
        schedule_id : str
            Schedule ID (deployment_id).
        request : UpdateScheduleRequest
            Update request.
        username : str
            The username.
        project_id : str
            The project ID.

        Returns
        -------
        UpdateScheduleResponse
            Success message.

        """
        async with get_client() as client:
            try:
                flow = self._flow_repo.find_one(
                    {"project_id": project_id, "deployment_id": schedule_id, "username": username}
                )
                if not flow:
                    raise HTTPException(
                        status_code=403,
                        detail="You don't have permission to update this schedule",
                    )

                deployment = await client.read_deployment(schedule_id)

                schedule_to_update = deployment.schedule
                if request.cron:
                    from prefect.client.schemas.schedules import CronSchedule

                    self._validate_cron(request.cron)
                    schedule_to_update = CronSchedule(cron=request.cron, timezone=request.timezone)

                await client.update_deployment(
                    deployment=deployment,
                    schedule=schedule_to_update,
                    is_schedule_active=request.active,
                )

                logger.info(f"Updated schedule: {schedule_id}")
                return UpdateScheduleResponse(
                    message="Schedule updated successfully",
                    schedule_id=schedule_id,
                )

            except Exception as e:
                logger.error(f"Failed to update schedule: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to update schedule: {e}")

    async def delete_schedule(
        self,
        schedule_id: str,
        username: str,
        project_id: str,
    ) -> DeleteScheduleResponse:
        """Delete a Flow schedule (cron or one-time).

        Parameters
        ----------
        schedule_id : str
            Schedule ID (deployment_id for cron, flow_run_id for one-time).
        username : str
            The username.
        project_id : str
            The project ID.

        Returns
        -------
        DeleteScheduleResponse
            Response with schedule type information.

        """
        async with get_client() as client:
            # Try as deployment ID (cron schedule)
            try:
                _ = await client.read_deployment(schedule_id)

                flow = self._flow_repo.find_one(
                    {"project_id": project_id, "deployment_id": schedule_id, "username": username}
                )
                if not flow:
                    raise HTTPException(
                        status_code=403,
                        detail="You don't have permission to delete this schedule",
                    )

                deployment = await client.read_deployment(schedule_id)
                await client.update_deployment(
                    deployment=deployment,
                    schedule=None,
                    is_schedule_active=False,
                )

                logger.info(f"Deleted cron schedule: {schedule_id}")
                return DeleteScheduleResponse(
                    message="Cron schedule deleted successfully",
                    schedule_id=schedule_id,
                    schedule_type="cron",
                )

            except HTTPException:
                raise
            except Exception as e:
                logger.debug(f"Not a deployment ID, trying as flow_run_id: {e}")

            # Try as flow_run_id (one-time schedule)
            try:
                flow_run_id = uuid.UUID(schedule_id)
                flow_run = await client.read_flow_run(flow_run_id)

                if flow_run.deployment_id:
                    flow = self._flow_repo.find_one(
                        {
                            "project_id": project_id,
                            "deployment_id": str(flow_run.deployment_id),
                            "username": username,
                        }
                    )
                    if not flow:
                        raise HTTPException(
                            status_code=403,
                            detail="You don't have permission to delete this schedule",
                        )

                await client.delete_flow_run(flow_run_id)
                logger.info(f"Deleted one-time schedule: {schedule_id}")
                return DeleteScheduleResponse(
                    message="One-time schedule deleted successfully",
                    schedule_id=schedule_id,
                    schedule_type="one-time",
                )

            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid schedule_id format")
            except Exception as e:
                logger.error(f"Failed to delete schedule: {e}")
                raise HTTPException(status_code=404, detail="Schedule not found")

    # --- Private helpers ---

    async def _schedule_cron(
        self,
        name: str,
        request: ScheduleFlowRequest,
        deployment_id: str,
        parameters: dict[str, Any],
    ) -> ScheduleFlowResponse:
        """Handle cron schedule creation."""
        self._validate_cron(request.cron)

        try:
            await self._http_post_with_retry(
                f"{DEPLOYMENT_SERVICE_URL}/set-schedule",
                {
                    "deployment_id": deployment_id,
                    "cron": request.cron,
                    "timezone": request.timezone,
                    "active": request.active,
                    "parameters": parameters,
                },
            )
            logger.info(f"Set cron schedule for flow '{name}': {request.cron}")

            next_run: datetime | None = None
            try:
                current_time = datetime.now(timezone.utc)
                cron_iter = croniter(request.cron or "", current_time)
                next_run = cron_iter.get_next(datetime)
            except Exception as e:
                logger.warning(f"Failed to calculate next run time: {e}")

            return ScheduleFlowResponse(
                schedule_id=deployment_id,
                flow_name=name,
                schedule_type="cron",
                cron=request.cron,
                next_run=next_run,
                active=request.active,
                message=f"Cron schedule set successfully for flow '{name}'",
            )

        except httpx.HTTPStatusError as e:
            error_detail = e.response.text if hasattr(e.response, "text") else str(e)
            logger.error(f"Failed to set cron schedule: {error_detail}")
            raise HTTPException(
                status_code=e.response.status_code if hasattr(e, "response") else 500,
                detail=f"Failed to set cron schedule: {error_detail}",
            )

    async def _schedule_one_time(
        self,
        name: str,
        request: ScheduleFlowRequest,
        deployment_id: str,
        parameters: dict[str, Any],
    ) -> ScheduleFlowResponse:
        """Handle one-time schedule creation."""
        scheduled_dt = self._parse_scheduled_time(request.scheduled_time)

        # Update request.scheduled_time with timezone-aware ISO format
        request.scheduled_time = scheduled_dt.isoformat()

        try:
            data = await self._http_post_with_retry(
                f"{DEPLOYMENT_SERVICE_URL}/create-scheduled-run",
                {
                    "deployment_id": deployment_id,
                    "scheduled_time": request.scheduled_time,
                    "parameters": parameters,
                },
            )
            flow_run_id = data["flow_run_id"]
            logger.info(f"Created one-time schedule for flow '{name}': {request.scheduled_time}")

            return ScheduleFlowResponse(
                schedule_id=flow_run_id,
                flow_name=name,
                schedule_type="one-time",
                cron=None,
                next_run=scheduled_dt,
                active=True,
                message=f"One-time schedule created successfully for flow '{name}'",
            )

        except httpx.HTTPStatusError as e:
            error_detail = e.response.text if hasattr(e.response, "text") else str(e)
            logger.error(f"Failed to create one-time schedule: {error_detail}")
            raise HTTPException(
                status_code=e.response.status_code if hasattr(e, "response") else 500,
                detail=f"Failed to create one-time schedule: {error_detail}",
            )

    @staticmethod
    def _validate_cron(cron: str | None) -> None:
        """Validate a cron expression."""
        if not cron:
            return
        try:
            croniter(cron)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid cron expression '{cron}': {e!s}",
            )

    @staticmethod
    def _parse_scheduled_time(scheduled_time_str: str | None) -> datetime:
        """Parse and validate a scheduled time string.

        Returns a timezone-aware datetime in the future.
        """
        if not scheduled_time_str:
            raise HTTPException(status_code=400, detail="scheduled_time is required")

        try:
            jst = ZoneInfo("Asia/Tokyo")

            has_timezone = "Z" in scheduled_time_str or (
                "+" in scheduled_time_str[10:]
                or (scheduled_time_str.count("-") > 2 and "-" in scheduled_time_str[19:])
            )

            if not has_timezone:
                naive_dt = datetime.fromisoformat(scheduled_time_str)
                scheduled_dt = naive_dt.replace(tzinfo=jst)
            else:
                scheduled_dt = datetime.fromisoformat(scheduled_time_str.replace("Z", "+00:00"))

            now = datetime.now(timezone.utc)
            if scheduled_dt <= now:
                raise HTTPException(
                    status_code=400,
                    detail=f"Scheduled time must be in the future. Provided: {scheduled_time_str} "
                    f"(interpreted as {scheduled_dt.isoformat()}), Current UTC: {now.isoformat()}",
                )

            return scheduled_dt

        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid scheduled_time format: {e!s}",
            )

    @staticmethod
    async def _http_post_with_retry(
        url: str,
        json_data: dict[str, Any],
        *,
        max_retries: int = 3,
        timeout: httpx.Timeout | float = DEFAULT_TIMEOUT,
    ) -> dict[str, Any]:
        """Make HTTP POST request with retry logic."""
        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=timeout) as client:
            for attempt in range(max_retries):
                try:
                    response = await client.post(url, json=json_data)
                    response.raise_for_status()
                    result: dict[str, Any] = response.json()
                    return result
                except (httpx.TimeoutException, httpx.ConnectError) as e:  # noqa: PERF203
                    last_error = e
                    if attempt < max_retries - 1:
                        wait_time = 2**attempt
                        logger.warning(
                            f"Attempt {attempt + 1} failed, retrying in {wait_time}s: {e}"
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"All {max_retries} attempts failed: {e}")

        raise HTTPException(
            status_code=500,
            detail=f"Request failed after {max_retries} attempts: {last_error}",
        )
