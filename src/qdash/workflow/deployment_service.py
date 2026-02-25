"""Minimal HTTP service for registering Prefect deployments from user flows.

This service runs in the Workflow container and provides a single endpoint
to register user flows as Prefect deployments.

Compatible with Prefect 3.x.
"""

import os
import uuid as uuid_module
from logging import getLogger
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from prefect.client.orchestration import get_client
from pydantic import BaseModel
from qdash.workflow.paths import get_path_resolver

app = FastAPI(title="QDash Deployment Service")
logger = getLogger("uvicorn.app")

# Work pool name for user flows
WORK_POOL_NAME = "user-flows-pool"

# Log Prefect API URL on startup
PREFECT_API_URL = os.getenv("PREFECT_API_URL", "not set")
logger.info(f"Deployment Service starting with PREFECT_API_URL: {PREFECT_API_URL}")


class RegisterDeploymentRequest(BaseModel):
    """Request to register a deployment."""

    file_path: str
    flow_function_name: str
    deployment_name: str | None = None
    old_deployment_id: str | None = None


class RegisterDeploymentResponse(BaseModel):
    """Response from deployment registration."""

    deployment_id: str
    deployment_name: str


@app.post("/register-deployment", response_model=RegisterDeploymentResponse)
async def register_deployment(request: RegisterDeploymentRequest) -> RegisterDeploymentResponse:
    """Register a user flow as a Prefect deployment.

    Args:
    ----
        request: Registration request with file path and flow name

    Returns:
    -------
        Deployment ID and name

    """
    try:
        file_path = Path(request.file_path)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"Flow file not found: {file_path}")

        # Create deployment name
        deployment_name = request.deployment_name or request.flow_function_name

        logger.info(f"Creating deployment '{deployment_name}' from {file_path}")

        # Create entrypoint string: relative_path:function_name
        # Working directory is configured via QDASH_WORKFLOW_DIR
        working_dir = get_path_resolver().workflow_dir
        try:
            relative_path = file_path.relative_to(working_dir)
        except ValueError:
            # If file is not under working_dir, use absolute path
            relative_path = file_path

        entrypoint = f"{relative_path}:{request.flow_function_name}"

        logger.info(f"Using entrypoint: {entrypoint}")

        # Load flow to validate it exists
        import importlib.util

        spec = importlib.util.spec_from_file_location("temp_module", file_path)
        if spec is None or spec.loader is None:
            raise HTTPException(status_code=400, detail=f"Could not load module from {file_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if not hasattr(module, request.flow_function_name):
            raise HTTPException(
                status_code=400,
                detail=f"Flow function '{request.flow_function_name}' not found in {file_path}",
            )

        flow_obj = getattr(module, request.flow_function_name)

        # Delete old deployment if it exists
        if request.old_deployment_id:
            try:
                logger.info(f"Attempting to delete old deployment: {request.old_deployment_id}")
                async with get_client() as client:
                    await client.delete_deployment(request.old_deployment_id)
                    logger.info(f"Deleted old deployment: {request.old_deployment_id}")
            except Exception as e:
                logger.warning(
                    f"Failed to delete old deployment {request.old_deployment_id}: {type(e).__name__}: {e}"
                )

        # Register flow and create deployment using Prefect 3 client API
        logger.info(f"Creating deployment with work pool: {WORK_POOL_NAME}")
        async with get_client() as client:
            # Register the flow (returns existing if same name)
            flow_id = await client.create_flow(flow_obj)
            logger.info(f"Flow registered with ID: {flow_id}")

            # Create deployment via client API
            deployment_id = await client.create_deployment(
                flow_id=flow_id,
                name=deployment_name,
                work_pool_name=WORK_POOL_NAME,
                entrypoint=entrypoint,
                path=str(working_dir),
            )

        logger.info(f"Deployment created successfully: {deployment_id}")

        return RegisterDeploymentResponse(
            deployment_id=str(deployment_id),
            deployment_name=deployment_name,
        )

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except AttributeError as e:
        logger.error(f"Flow function not found: {e}")
        raise HTTPException(
            status_code=400, detail=f"Flow function '{request.flow_function_name}' not found"
        )
    except Exception as e:
        logger.error(f"Failed to register deployment: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health() -> dict[str, Any]:
    """Health check endpoint."""
    return {"status": "healthy"}


# ============================================================================
# Schedule Management Endpoints
# ============================================================================


class SetScheduleRequest(BaseModel):
    """Request to set a schedule on a deployment."""

    deployment_id: str
    cron: str
    timezone: str = "Asia/Tokyo"
    active: bool = True
    parameters: dict[str, Any] | None = None


class SetScheduleResponse(BaseModel):
    """Response from setting a schedule."""

    deployment_id: str
    cron: str
    active: bool
    message: str


class CreateScheduledRunRequest(BaseModel):
    """Request to create a scheduled flow run."""

    deployment_id: str
    scheduled_time: str  # ISO format
    parameters: dict[str, Any] | None = None


class CreateScheduledRunResponse(BaseModel):
    """Response from creating a scheduled run."""

    flow_run_id: str
    scheduled_time: str
    message: str


@app.post("/set-schedule", response_model=SetScheduleResponse)
async def set_schedule(request: SetScheduleRequest) -> SetScheduleResponse:
    """Set or update a cron schedule on a deployment.

    In Prefect 3, schedules are managed via dedicated schedule APIs
    rather than the deployment update API.

    Args:
    ----
        request: Schedule configuration request

    Returns:
    -------
        Schedule configuration response

    """
    from prefect.client.schemas.schedules import CronSchedule

    try:
        logger.info(f"Setting schedule for deployment {request.deployment_id}")
        logger.info(f"Cron: {request.cron}, Timezone: {request.timezone}, Active: {request.active}")

        cron_schedule = CronSchedule(cron=request.cron, timezone=request.timezone)
        deployment_id = uuid_module.UUID(request.deployment_id)

        async with get_client() as client:
            # Read existing deployment to verify it exists
            try:
                target_deployment = await client.read_deployment(deployment_id)
                logger.info(f"Found deployment: {target_deployment.name}")
            except Exception as e:
                logger.error(f"Failed to read deployment {request.deployment_id}: {e}")
                raise HTTPException(
                    status_code=404, detail=f"Deployment not found: {request.deployment_id}"
                )

            try:
                # Delete existing schedules first
                existing_schedules = await client.read_deployment_schedules(deployment_id)
                for existing in existing_schedules:
                    await client.delete_deployment_schedule(deployment_id, existing.id)
                    logger.info(f"Deleted existing schedule: {existing.id}")

                # Create new schedule
                await client.create_deployment_schedules(
                    deployment_id,
                    [(cron_schedule, request.active)],
                )
                logger.info("Successfully created deployment schedule")

                # Update parameters via direct API call if provided
                if request.parameters:
                    logger.info(f"Updating deployment parameters: {request.parameters}")
                    response = await client._client.patch(
                        f"/deployments/{request.deployment_id}",
                        json={"parameters": request.parameters},
                    )
                    response.raise_for_status()
                    logger.info("Successfully updated deployment parameters")
            except Exception as e:
                logger.error(f"Failed to update deployment: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to update deployment: {e!s}")

            logger.info(
                f"Set schedule on deployment {request.deployment_id}: cron={request.cron}, active={request.active}"
            )

            return SetScheduleResponse(
                deployment_id=request.deployment_id,
                cron=request.cron,
                active=request.active,
                message=f"Schedule set successfully on deployment {target_deployment.name}",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to set schedule (unexpected error): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e!s}")


@app.post("/create-scheduled-run", response_model=CreateScheduledRunResponse)
async def create_scheduled_run(request: CreateScheduledRunRequest) -> CreateScheduledRunResponse:
    """Create a one-time scheduled flow run.

    Args:
    ----
        request: Scheduled run request

    Returns:
    -------
        Scheduled run response with flow_run_id

    """
    from datetime import datetime

    from prefect.states import Scheduled

    try:
        logger.info(f"Creating scheduled run for deployment {request.deployment_id}")
        logger.info(f"Scheduled time: {request.scheduled_time}")

        try:
            scheduled_time = datetime.fromisoformat(request.scheduled_time)
            logger.info(f"Parsed scheduled time: {scheduled_time}")
        except Exception as e:
            logger.error(f"Failed to parse scheduled time: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid scheduled_time format: {e!s}")

        async with get_client() as client:
            try:
                flow_run = await client.create_flow_run_from_deployment(
                    deployment_id=request.deployment_id,
                    state=Scheduled(scheduled_time=scheduled_time),
                    parameters=request.parameters or {},
                )
                logger.info(f"Successfully created scheduled run {flow_run.id}")
            except Exception as e:
                logger.error(f"Failed to create flow run: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to create flow run: {e!s}")

            logger.info(f"Created scheduled run {flow_run.id} for {scheduled_time}")

            return CreateScheduledRunResponse(
                flow_run_id=str(flow_run.id),
                scheduled_time=request.scheduled_time,
                message=f"Flow run scheduled successfully for {scheduled_time}",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create scheduled run (unexpected error): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e!s}")
