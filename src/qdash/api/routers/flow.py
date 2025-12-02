"""API router for user-defined flows and scheduling."""

import asyncio
import json
import os
import re
import uuid
from datetime import datetime, timezone
from logging import getLogger
from pathlib import Path
from typing import Annotated, Any

import httpx
from croniter import croniter
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
    DeleteScheduleResponse,
    ExecuteFlowRequest,
    ExecuteFlowResponse,
    FlowScheduleSummary,
    FlowTemplate,
    FlowTemplateWithCode,
    GetFlowResponse,
    ListFlowSchedulesResponse,
    ListFlowsResponse,
    SaveFlowRequest,
    SaveFlowResponse,
    ScheduleFlowRequest,
    ScheduleFlowResponse,
    UpdateScheduleRequest,
    UpdateScheduleResponse,
)
from qdash.config import get_settings
from qdash.dbmodel.flow import FlowDocument
from zoneinfo import ZoneInfo

router = APIRouter()
logger = getLogger("uvicorn.app")

# Base directory for user flows (shared volume between API and Workflow containers)
USER_FLOWS_BASE_DIR = Path("/app/qdash/workflow/user_flows")

# Deployment service URL (Deployment service container - internal Docker network)
DEPLOYMENT_SERVICE_URL = os.getenv("DEPLOYMENT_SERVICE_URL", "http://deployment-service:8001")

# Path to templates directory
TEMPLATES_DIR = Path("/app/qdash/workflow/examples/templates")
TEMPLATES_METADATA_FILE = TEMPLATES_DIR / "templates.json"


def get_user_flows_dir(username: str) -> Path:
    """Get user's flows directory, create if not exists.

    Args:
    ----
        username: Username

    Returns:
    -------
        Path to user's flows directory

    """
    user_dir = USER_FLOWS_BASE_DIR / username
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def validate_flow_name(name: str) -> None:
    """Validate flow name (alphanumeric + underscore only).

    Args:
    ----
        name: Flow name to validate

    Raises:
    ------
        HTTPException: If name is invalid

    """
    if not re.match(r"^[a-zA-Z0-9_]+$", name):
        raise HTTPException(
            status_code=400,
            detail="Flow name must contain only alphanumeric characters and underscores",
        )


def validate_flow_code(code: str, expected_function_name: str) -> None:
    """Validate that Python code contains the expected @flow decorated function.

    Args:
    ----
        code: Python code content
        expected_function_name: Expected flow function name

    Raises:
    ------
        HTTPException: If validation fails

    """
    import ast

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Python syntax error in code: {e}",
        )

    # Find all function definitions with @flow decorator
    flow_functions = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Check if function has @flow decorator
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Name) and decorator.id == "flow":
                    flow_functions.append(node.name)
                elif (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Name)
                    and decorator.func.id == "flow"
                ):
                    flow_functions.append(node.name)

    if not flow_functions:
        raise HTTPException(
            status_code=400,
            detail="No @flow decorated function found in code. Please add @flow decorator to your flow function.",
        )

    if expected_function_name not in flow_functions:
        raise HTTPException(
            status_code=400,
            detail=f"Flow function '{expected_function_name}' not found in code. Found: {', '.join(flow_functions)}. "
            f"Please ensure your flow function name matches the flow name.",
        )


async def register_flow_deployment(
    file_path: str, flow_function_name: str, deployment_name: str, old_deployment_id: str | None = None
) -> str:
    """Register a flow as a Prefect deployment via Workflow service.

    Args:
    ----
        file_path: Absolute path to flow file
        flow_function_name: Name of the flow function
        deployment_name: Name for the deployment
        old_deployment_id: Optional existing deployment ID to delete

    Returns:
    -------
        Deployment ID

    Raises:
    ------
        HTTPException: If registration fails

    """
    try:
        logger.info(f"Registering deployment '{deployment_name}' at {DEPLOYMENT_SERVICE_URL}")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{DEPLOYMENT_SERVICE_URL}/register-deployment",
                json={
                    "file_path": file_path,
                    "flow_function_name": flow_function_name,
                    "deployment_name": deployment_name,
                    "old_deployment_id": old_deployment_id,
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            logger.info(f"Successfully registered deployment: {data['deployment_id']}")
            return data["deployment_id"]
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error during deployment registration: {e.response.status_code} - {e.response.text}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to register deployment: {e.response.status_code}: {e.response.text}",
        )
    except httpx.HTTPError as e:
        logger.error(f"Failed to register deployment: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to register deployment: {e}",
        )


@router.post(
    "/flow",
    response_model=SaveFlowResponse,
    summary="Save a Flow",
    operation_id="save_flow",
)
async def save_flow(
    request: SaveFlowRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SaveFlowResponse:
    """Save a Flow to file system and MongoDB.

    Steps:
    1. Validate flow name
    2. Validate flow code contains expected function
    3. Create user directory if not exists
    4. Write code to file: user_flows/{username}/{name}.py
    5. Upsert metadata to MongoDB
    6. Return file path and success message
    """
    validate_flow_name(request.name)

    # Default flow_function_name to name if not provided
    if request.flow_function_name is None:
        request.flow_function_name = request.name

    # Validate that code contains the expected flow function
    validate_flow_code(request.code, request.flow_function_name)

    username = current_user.username

    # Get user directory
    user_dir = get_user_flows_dir(username)
    file_path = user_dir / f"{request.name}.py"

    # Check if flow already exists (to get old deployment_id)
    existing_flow = FlowDocument.find_by_user_and_name(username, request.name)
    old_deployment_id = existing_flow.deployment_id if existing_flow else None

    # Write code to file
    try:
        file_path.write_text(request.code, encoding="utf-8")
        logger.info(f"Saved flow code to {file_path}")
    except Exception as e:
        logger.error(f"Failed to write flow file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save flow file: {e}")

    # Auto-format with ruff
    try:
        import subprocess

        result = subprocess.run(
            ["ruff", "format", str(file_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            logger.info(f"Auto-formatted flow code with ruff: {file_path}")
        else:
            logger.warning(f"Ruff format returned non-zero exit code: {result.stderr}")
    except subprocess.TimeoutExpired:
        logger.warning("Ruff format timeout - skipping auto-format")
    except FileNotFoundError:
        logger.warning("Ruff not found - skipping auto-format")
    except Exception as e:
        logger.warning(f"Failed to auto-format with ruff: {e} - skipping")

    # Register Prefect deployment
    try:
        deployment_name = f"{username}-{request.name}"
        deployment_id = await register_flow_deployment(
            file_path=str(file_path),
            flow_function_name=request.flow_function_name,
            deployment_name=deployment_name,
            old_deployment_id=old_deployment_id,
        )
        logger.info(f"Registered deployment: {deployment_id}")
    except Exception as e:
        logger.error(f"Failed to register deployment: {e}")
        # Clean up file if deployment registration failed
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=f"Failed to register deployment: {e}")

    # Upsert to MongoDB
    try:
        # Store absolute path for Docker environment consistency
        file_path_str = str(file_path)

        if existing_flow:
            # Update existing flow
            existing_flow.description = request.description
            existing_flow.chip_id = request.chip_id
            existing_flow.flow_function_name = request.flow_function_name
            existing_flow.default_parameters = request.default_parameters
            existing_flow.file_path = file_path_str
            existing_flow.deployment_id = deployment_id
            existing_flow.updated_at = datetime.now()
            existing_flow.tags = request.tags
            existing_flow.save()
            logger.info(f"Updated flow '{request.name}' for user '{username}'")
            message = f"Flow '{request.name}' updated successfully"
        else:
            # Create new flow
            flow_doc = FlowDocument(
                name=request.name,
                username=username,
                chip_id=request.chip_id,
                description=request.description,
                flow_function_name=request.flow_function_name,
                default_parameters=request.default_parameters,
                file_path=file_path_str,
                deployment_id=deployment_id,
                tags=request.tags,
            )
            flow_doc.insert()
            logger.info(f"Created new flow '{request.name}' for user '{username}'")
            message = f"Flow '{request.name}' created successfully"

    except Exception as e:
        logger.error(f"Failed to save flow to database: {e}")
        # Clean up file if database operation failed
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=f"Failed to save flow metadata: {e}")

    return SaveFlowResponse(
        name=request.name,
        file_path=file_path_str,
        message=message,
    )


@router.get(
    "/flow",
    response_model=ListFlowsResponse,
    summary="List Flows",
    operation_id="list_flows",
)
async def list_flows(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> ListFlowsResponse:
    """List all Flows for the current user.

    Returns metadata only (no code content for performance).
    """
    username = current_user.username

    try:
        flows = FlowDocument.list_by_user(username)
        logger.info(f"Listed {len(flows)} flows for user '{username}'")

        from qdash.api.schemas.flow import FlowSummary

        flow_summaries = [
            FlowSummary(
                name=flow.name,
                description=flow.description,
                chip_id=flow.chip_id,
                flow_function_name=flow.flow_function_name,
                created_at=flow.created_at.isoformat(),
                updated_at=flow.updated_at.isoformat(),
                tags=flow.tags,
            )
            for flow in flows
        ]

        return ListFlowsResponse(flows=flow_summaries)

    except Exception as e:
        logger.error(f"Failed to list flows: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list flows: {e}")


@router.get(
    "/flow/{name}",
    response_model=GetFlowResponse,
    summary="Get Flow details",
    operation_id="get_flow",
)
async def get_flow(
    name: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> GetFlowResponse:
    """Get Flow details including code content.

    Steps:
    1. Find metadata in MongoDB
    2. Read code from file
    3. Return combined data
    """
    username = current_user.username

    # Find flow in database
    flow = FlowDocument.find_by_user_and_name(username, name)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{name}' not found")

    # Read code from file
    file_path = Path(flow.file_path)
    if not file_path.exists():
        logger.error(f"Flow file not found: {file_path}")
        raise HTTPException(status_code=404, detail=f"Flow file not found: {file_path}")

    try:
        code = file_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to read flow file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read flow file: {e}")

    return GetFlowResponse(
        name=flow.name,
        description=flow.description,
        code=code,
        flow_function_name=flow.flow_function_name,
        chip_id=flow.chip_id,
        default_parameters=flow.default_parameters,
        file_path=flow.file_path,
        created_at=flow.created_at.isoformat(),
        updated_at=flow.updated_at.isoformat(),
        tags=flow.tags,
    )


@router.post(
    "/flow/{name}/execute",
    response_model=ExecuteFlowResponse,
    summary="Execute a Flow",
    operation_id="execute_flow",
)
async def execute_flow(
    name: str,
    request: ExecuteFlowRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> ExecuteFlowResponse:
    """Execute a Flow via Prefect deployment.

    Steps:
    1. Find flow metadata in MongoDB
    2. Merge request parameters with default_parameters
    3. Create flow run via Prefect Client
    4. Return execution_id and URLs
    """
    from prefect import get_client

    username = current_user.username
    settings = get_settings()

    # Find flow in database
    flow = FlowDocument.find_by_user_and_name(username, name)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{name}' not found")

    if not flow.deployment_id:
        raise HTTPException(
            status_code=400,
            detail=f"Flow '{name}' has no deployment. Please re-save the flow to register a deployment.",
        )

    # Merge parameters (request overrides defaults)
    # Add flow_name to parameters so it can be used for execution display name
    parameters: dict[str, Any] = {
        **flow.default_parameters,
        **request.parameters,
        "flow_name": name,  # Add flow name for display purposes
    }

    logger.info(f"Executing flow '{name}' (deployment={flow.deployment_id}) with parameters: {parameters}")

    # Create flow run via Prefect Client
    try:
        async with get_client() as client:
            flow_run = await client.create_flow_run_from_deployment(
                deployment_id=flow.deployment_id,
                parameters=parameters,
            )

            execution_id = str(flow_run.id)
            # Construct URLs
            flow_run_url = f"http://localhost:{settings.prefect_port}/flow-runs/flow-run/{execution_id}"
            qdash_ui_url = f"http://localhost:{settings.ui_port}/execution/{execution_id}"

            logger.info(f"Flow run created: {execution_id}")

            return ExecuteFlowResponse(
                execution_id=execution_id,
                flow_run_url=flow_run_url,
                qdash_ui_url=qdash_ui_url,
                message=f"Flow '{name}' execution started successfully",
            )

    except Exception as e:
        logger.error(f"Failed to execute flow: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to execute flow: {e}")


@router.delete(
    "/flow/{name}",
    summary="Delete a Flow",
    operation_id="delete_flow",
)
async def delete_flow(
    name: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict[str, str]:
    """Delete a Flow.

    Steps:
    1. Delete file from user_flows/{username}/{name}.py
    2. Delete metadata from MongoDB
    """
    username = current_user.username

    # Find flow in database
    flow = FlowDocument.find_by_user_and_name(username, name)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{name}' not found")

    # Delete file
    file_path = Path(flow.file_path)
    if file_path.exists():
        try:
            file_path.unlink()
            logger.info(f"Deleted flow file: {file_path}")
        except Exception as e:
            logger.error(f"Failed to delete flow file: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to delete flow file: {e}")

    # Delete from database
    try:
        FlowDocument.delete_by_user_and_name(username, name)
        logger.info(f"Deleted flow '{name}' from database")
    except Exception as e:
        logger.error(f"Failed to delete flow from database: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete flow metadata: {e}")

    return {"message": f"Flow '{name}' deleted successfully"}


# ============================================================================
# Flow Templates Endpoints
# ============================================================================


@router.get(
    "/flow-templates",
    response_model=list[FlowTemplate],
    summary="List Flow Templates",
    operation_id="list_flow_templates",
)
async def list_flow_templates() -> list[FlowTemplate]:
    """List all available flow templates.

    Returns metadata only (no code content for performance).
    """
    try:
        if not TEMPLATES_METADATA_FILE.exists():
            logger.error(f"Templates metadata file not found: {TEMPLATES_METADATA_FILE}")
            return []

        with open(TEMPLATES_METADATA_FILE, encoding="utf-8") as f:
            templates_data = json.load(f)

        templates = [FlowTemplate(**t) for t in templates_data]
        logger.info(f"Listed {len(templates)} flow templates")

        return templates

    except Exception as e:
        logger.error(f"Failed to list flow templates: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list flow templates: {e}")


@router.get(
    "/flow-templates/{template_id}",
    response_model=FlowTemplateWithCode,
    summary="Get Flow Template",
    operation_id="get_flow_template",
)
async def get_flow_template(template_id: str) -> FlowTemplateWithCode:
    """Get flow template details including code content.

    Steps:
    1. Find template metadata
    2. Read Python file content
    3. Return combined data
    """
    try:
        # Load metadata
        if not TEMPLATES_METADATA_FILE.exists():
            raise HTTPException(status_code=404, detail="Templates metadata file not found")

        with open(TEMPLATES_METADATA_FILE, encoding="utf-8") as f:
            templates_data = json.load(f)

        # Find template
        template_data = next((t for t in templates_data if t["id"] == template_id), None)
        if not template_data:
            raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")

        # Read code file
        code_file = TEMPLATES_DIR / template_data["filename"]
        if not code_file.exists():
            logger.error(f"Template file not found: {code_file}")
            raise HTTPException(status_code=404, detail=f"Template file not found: {code_file}")

        code = code_file.read_text(encoding="utf-8")

        return FlowTemplateWithCode(**template_data, code=code)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get flow template: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get flow template: {e}")


# ============================================================================
# Flow Scheduling Endpoints
# ============================================================================


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

    # Merge parameters - include username and chip_id from flow metadata
    parameters: dict[str, Any] = {
        "username": username,
        "chip_id": flow.chip_id,
        **flow.default_parameters,
        **request.parameters,
        "flow_name": name,
    }

    logger.info(f"Scheduling flow '{name}' with parameters: {parameters}")

    # Handle cron schedule
    if request.cron:
        # Validate cron expression
        try:
            croniter(request.cron)  # Will raise ValueError if invalid
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid cron expression '{request.cron}': {str(e)}",
            )

        try:
            # Configure httpx client with timeout and retry
            timeout_config = httpx.Timeout(
                connect=5.0,  # Connection timeout
                read=30.0,  # Read timeout
                write=10.0,  # Write timeout
                pool=5.0,  # Pool timeout
            )

            async with httpx.AsyncClient(timeout=timeout_config) as client:
                # Retry logic: try up to 3 times with exponential backoff
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        response = await client.post(
                            f"{DEPLOYMENT_SERVICE_URL}/set-schedule",
                            json={
                                "deployment_id": flow.deployment_id,
                                "cron": request.cron,
                                "timezone": request.timezone,
                                "active": request.active,
                                "parameters": parameters,
                            },
                        )
                        response.raise_for_status()
                        break  # Success, exit retry loop
                    except (httpx.TimeoutException, httpx.ConnectError) as e:
                        if attempt < max_retries - 1:
                            wait_time = 2**attempt  # Exponential backoff: 1s, 2s, 4s
                            logger.warning(f"Attempt {attempt + 1} failed, retrying in {wait_time}s: {e}")
                            await asyncio.sleep(wait_time)
                        else:
                            raise  # Final attempt failed
                    except httpx.HTTPStatusError:
                        raise  # Don't retry on 4xx/5xx errors
                response.raise_for_status()
                data = response.json()

                logger.info(f"Set cron schedule for flow '{name}': {request.cron}")

                # Calculate next run time from cron expression
                next_run = None
                try:
                    now = datetime.now(timezone.utc)
                    cron_iter = croniter(request.cron, now)
                    next_run_dt = cron_iter.get_next(datetime)
                    next_run = next_run_dt.isoformat()
                except Exception as e:
                    logger.warning(f"Failed to calculate next run time: {e}")
                    next_run = None

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
        # Validate scheduled_time is in the future
        try:
            scheduled_time_str = request.scheduled_time
            jst = ZoneInfo("Asia/Tokyo")

            # Check if timezone info is present
            # Formats with timezone: 2025-11-26T10:00:00+09:00, 2025-11-26T01:00:00Z
            # Formats without timezone: 2025-11-26T10:00, 2025-11-26T10:00:00
            has_timezone = "Z" in scheduled_time_str or (
                "+" in scheduled_time_str[10:] or (scheduled_time_str.count("-") > 2 and "-" in scheduled_time_str[19:])
            )

            if not has_timezone:
                # datetime-local format: YYYY-MM-DDTHH:mm or YYYY-MM-DDTHH:mm:ss
                # Assume JST (Asia/Tokyo)
                naive_dt = datetime.fromisoformat(scheduled_time_str)
                scheduled_dt = naive_dt.replace(tzinfo=jst)
                # Convert to ISO format with timezone for storage
                scheduled_time_str = scheduled_dt.isoformat()
            else:
                scheduled_dt = datetime.fromisoformat(scheduled_time_str.replace("Z", "+00:00"))

            now = datetime.now(timezone.utc)
            if scheduled_dt <= now:
                raise HTTPException(
                    status_code=400,
                    detail=f"Scheduled time must be in the future. Provided: {request.scheduled_time} (interpreted as {scheduled_dt.isoformat()}), Current UTC: {now.isoformat()}",
                )
            # Update request.scheduled_time with timezone-aware ISO format
            request.scheduled_time = scheduled_time_str
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid scheduled_time format: {str(e)}",
            )

        try:
            # Configure httpx client with timeout
            timeout_config = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)

            async with httpx.AsyncClient(timeout=timeout_config) as client:
                # Retry logic for one-time schedule creation
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        response = await client.post(
                            f"{DEPLOYMENT_SERVICE_URL}/create-scheduled-run",
                            json={
                                "deployment_id": flow.deployment_id,
                                "scheduled_time": request.scheduled_time,
                                "parameters": parameters,
                            },
                        )
                        response.raise_for_status()
                        data = response.json()
                        break  # Success
                    except (httpx.TimeoutException, httpx.ConnectError) as e:
                        if attempt < max_retries - 1:
                            wait_time = 2**attempt
                            logger.warning(f"Attempt {attempt + 1} failed, retrying in {wait_time}s: {e}")
                            await asyncio.sleep(wait_time)
                        else:
                            raise
                    except httpx.HTTPStatusError:
                        raise

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
    limit: int = 50,  # Default 50, max 100
    offset: int = 0,
) -> ListFlowSchedulesResponse:
    """List all schedules (cron and one-time) for a specific Flow.

    Args:
    ----
        name: Flow name
        current_user: Current authenticated user
        limit: Maximum number of schedules to return (max 100)
        offset: Number of schedules to skip

    Returns:
    -------
        List of schedules for the flow

    """
    # Enforce max limit
    limit = min(limit, 100)
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
            state_filter = FlowRunFilterStateType(any_=[StateType.SCHEDULED])
            flow_runs = await client.read_flow_runs(
                deployment_filter=DeploymentFilter(id={"any_": [uuid.UUID(flow.deployment_id)]}),
                flow_run_filter=FlowRunFilter(state=FlowRunFilterState(type=state_filter)),
                limit=limit,  # Use pagination limit
                offset=offset,
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
    limit: int = 50,
    offset: int = 0,
) -> ListFlowSchedulesResponse:
    """List all Flow schedules (cron and one-time) for the current user.

    Args:
    ----
        current_user: Current authenticated user
        limit: Maximum number of schedules to return (max 100)
        offset: Number of schedules to skip

    Returns:
    -------
        List of all flow schedules

    """
    limit = min(limit, 100)
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
                state_filter = FlowRunFilterStateType(any_=[StateType.SCHEDULED])
                flow_runs = await client.read_flow_runs(
                    deployment_filter=DeploymentFilter(id={"any_": [uuid.UUID(flow.deployment_id)]}),
                    flow_run_filter=FlowRunFilter(state=FlowRunFilterState(type=state_filter)),
                    limit=limit,  # Use pagination limit
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

    # Apply offset and limit to sorted results
    paginated_schedules = all_schedules[offset : offset + limit]

    return ListFlowSchedulesResponse(schedules=paginated_schedules)


@router.delete(
    "/flow-schedule/{schedule_id}",
    response_model=DeleteScheduleResponse,
    summary="Delete a Flow schedule",
    operation_id="delete_flow_schedule",
)
async def delete_flow_schedule(
    schedule_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> DeleteScheduleResponse:
    """Delete a Flow schedule (cron or one-time).

    Schedule ID Types:
    - **Cron schedules**: schedule_id is the deployment_id (UUID format)
    - **One-time schedules**: schedule_id is the flow_run_id (UUID format)

    The API automatically determines the type and handles accordingly:
    - Cron: Removes the schedule from the deployment (schedule=None)
    - One-time: Deletes the scheduled flow run

    Args:
    ----
        schedule_id: Schedule ID (deployment_id for cron, flow_run_id for one-time)
        current_user: Current authenticated user

    Returns:
    -------
        Standardized response with schedule type information

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
            return DeleteScheduleResponse(
                message="Cron schedule deleted successfully",
                schedule_id=schedule_id,
                schedule_type="cron",
            )

        except HTTPException:
            raise  # Re-raise permission errors
        except Exception as e:
            # Not a deployment ID (could be 404 or other Prefect error), try as flow_run_id
            logger.debug(f"Not a deployment ID, trying as flow_run_id: {e}")

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


@router.patch(
    "/flow-schedule/{schedule_id}",
    response_model=UpdateScheduleResponse,
    summary="Update a Flow schedule",
    operation_id="update_flow_schedule",
)
async def update_flow_schedule(
    schedule_id: str,
    request: UpdateScheduleRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> UpdateScheduleResponse:
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

                # Validate cron expression
                try:
                    croniter(request.cron)
                except ValueError as e:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid cron expression '{request.cron}': {str(e)}",
                    )

                # Use timezone from request (defaults to Asia/Tokyo in schema)
                schedule_to_update = CronSchedule(cron=request.cron, timezone=request.timezone)

            # Update deployment directly without creating new Deployment object
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
