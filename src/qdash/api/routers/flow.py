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
from zoneinfo import ZoneInfo

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
from qdash.api.lib.project import ProjectContext, get_project_context
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
from qdash.common.paths import SERVICE_DIR, TEMPLATES_DIR, USER_FLOWS_DIR
from qdash.config import get_settings
from qdash.repository import MongoFlowRepository

router = APIRouter()
logger = getLogger("uvicorn.app")

# Base directory for user flows (shared volume between API and Workflow containers)
USER_FLOWS_BASE_DIR = USER_FLOWS_DIR

# Deployment service URL (Deployment service container - internal Docker network)
DEPLOYMENT_SERVICE_URL = os.getenv("DEPLOYMENT_SERVICE_URL", "http://deployment-service:8001")

# Path to templates directory
TEMPLATES_METADATA_FILE = TEMPLATES_DIR / "templates.json"

# Default HTTP client configuration
DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)


async def _http_post_with_retry(
    url: str,
    json_data: dict[str, Any],
    *,
    max_retries: int = 3,
    timeout: httpx.Timeout | float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Make HTTP POST request with retry logic.

    Args:
        url: Target URL
        json_data: JSON payload
        max_retries: Maximum retry attempts (default: 3)
        timeout: Request timeout configuration

    Returns:
        Response JSON as dictionary

    Raises:
        HTTPException: If all retries fail or non-retryable error occurs

    """
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
                    wait_time = 2**attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.warning(f"Attempt {attempt + 1} failed, retrying in {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All {max_retries} attempts failed: {e}")

    # All retries exhausted
    raise HTTPException(
        status_code=500,
        detail=f"Request failed after {max_retries} attempts: {last_error}",
    )


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
                if (
                    isinstance(decorator, ast.Name)
                    and decorator.id == "flow"
                    or (
                        isinstance(decorator, ast.Call)
                        and isinstance(decorator.func, ast.Name)
                        and decorator.func.id == "flow"
                    )
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
    file_path: str,
    flow_function_name: str,
    deployment_name: str,
    old_deployment_id: str | None = None,
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
            deployment_id = str(data["deployment_id"])
            logger.info(f"Successfully registered deployment: {deployment_id}")
            return deployment_id
    except httpx.HTTPStatusError as e:
        logger.error(
            f"HTTP error during deployment registration: {e.response.status_code} - {e.response.text}"
        )
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
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
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

    username = ctx.user.username

    # Get user directory
    user_dir = get_user_flows_dir(username)
    file_path = user_dir / f"{request.name}.py"

    # Check if flow already exists (to get old deployment_id)
    flow_repo = MongoFlowRepository()
    existing_flow = flow_repo.find_by_user_and_name(username, request.name, ctx.project_id)
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
            check=False,
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
            logger.info(
                f"[TRACE] save_flow default_run_parameters={request.default_run_parameters}"
            )
            flow_repo.update_flow(
                flow=existing_flow,
                description=request.description,
                chip_id=request.chip_id,
                flow_function_name=request.flow_function_name,
                default_parameters=request.default_parameters,
                default_run_parameters=request.default_run_parameters,
                file_path=file_path_str,
                deployment_id=deployment_id,
                tags=request.tags,
            )
            logger.info(f"Updated flow '{request.name}' for user '{username}'")
            message = f"Flow '{request.name}' updated successfully"
        else:
            # Create new flow
            flow_repo.create_flow(
                project_id=ctx.project_id,
                name=request.name,
                username=username,
                chip_id=request.chip_id,
                description=request.description,
                flow_function_name=request.flow_function_name,
                default_parameters=request.default_parameters,
                file_path=file_path_str,
                deployment_id=deployment_id,
                tags=request.tags,
                default_run_parameters=request.default_run_parameters,
            )
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
    "/flows",
    response_model=ListFlowsResponse,
    summary="List all flows",
    operation_id="listFlows",
)
async def list_flows(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> ListFlowsResponse:
    """List all Flows for the current project.

    Returns metadata only (no code content for performance).
    """
    username = ctx.user.username
    project_id = ctx.project_id

    try:
        flow_repo = MongoFlowRepository()
        flows = flow_repo.list_by_user(username, project_id)
        logger.info(f"Listed {len(flows)} flows for user '{username}'")

        from qdash.api.schemas.flow import FlowSummary

        flow_summaries = [
            FlowSummary(
                name=flow.name,
                description=flow.description,
                chip_id=flow.chip_id,
                flow_function_name=flow.flow_function_name,
                created_at=flow.created_at,
                updated_at=flow.updated_at,
                tags=flow.tags,
            )
            for flow in flows
        ]

        return ListFlowsResponse(flows=flow_summaries)

    except Exception as e:
        logger.error(f"Failed to list flows: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list flows: {e}")


# ============================================================================
# Flow Templates Endpoints (static paths - before /flow/{name})
# ============================================================================


@router.get(
    "/flows/templates",
    response_model=list[FlowTemplate],
    summary="List all flow templates",
    operation_id="listFlowTemplates",
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
    "/flows/templates/{template_id}",
    response_model=FlowTemplateWithCode,
    summary="Get a flow template",
    operation_id="getFlowTemplate",
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
# Flow Helper Files Endpoints (static paths - before /flow/{name})
# ============================================================================

# Base directory for flow helper modules
FLOW_HELPERS_DIR = SERVICE_DIR


@router.get(
    "/flows/helpers",
    response_model=list[str],
    summary="List flow helper files",
    operation_id="listFlowHelperFiles",
)
async def list_flow_helper_files() -> list[str]:
    """List all Python files in the qdash.workflow.service module.

    Returns list of filenames that users can view for reference.
    """
    try:
        if not FLOW_HELPERS_DIR.exists():
            logger.warning(f"Flow helpers directory not found: {FLOW_HELPERS_DIR}")
            return []

        files = [
            f.name
            for f in FLOW_HELPERS_DIR.iterdir()
            if f.is_file() and f.suffix == ".py" and not f.name.startswith("_")
        ]
        # Add __init__.py explicitly as it's useful
        if (FLOW_HELPERS_DIR / "__init__.py").exists():
            files.insert(0, "__init__.py")

        # Sort with __init__.py first, then alphabetically
        files = sorted(set(files), key=lambda x: (x != "__init__.py", x))

        logger.info(f"Listed {len(files)} flow helper files")
        return files

    except Exception as e:
        logger.error(f"Failed to list flow helper files: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list flow helper files: {e}")


@router.get(
    "/flows/helpers/{filename}",
    response_model=str,
    summary="Get flow helper file content",
    operation_id="getFlowHelperFile",
)
async def get_flow_helper_file(filename: str) -> str:
    """Get the content of a flow helper file.

    Args:
        filename: Name of the Python file (e.g., "session.py")

    Returns:
        File content as string
    """
    # Validate filename to prevent directory traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    if not filename.endswith(".py"):
        raise HTTPException(status_code=400, detail="Only Python files are allowed")

    file_path = FLOW_HELPERS_DIR / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")

    try:
        content = file_path.read_text(encoding="utf-8")
        logger.info(f"Read flow helper file: {filename}")
        return content

    except Exception as e:
        logger.error(f"Failed to read flow helper file {filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read file: {e}")


# ============================================================================
# Flow Schedules Endpoints (static paths - before /flow/{name})
# ============================================================================


@router.get(
    "/flows/schedules",
    response_model=ListFlowSchedulesResponse,
    summary="List all flow schedules for current user",
    operation_id="listAllFlowSchedules",
)
async def list_all_flow_schedules(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    limit: int = 50,
    offset: int = 0,
) -> ListFlowSchedulesResponse:
    """List all Flow schedules (cron and one-time) for the current project.

    Args:
    ----
        ctx: Project context with user and project information
        limit: Maximum number of schedules to return (max 100)
        offset: Number of schedules to skip

    Returns:
    -------
        List of all flow schedules

    """
    limit = min(limit, 100)
    username = ctx.user.username
    project_id = ctx.project_id
    flow_repo = MongoFlowRepository()
    flows = flow_repo.list_by_user(username, project_id)

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
                            created_at=deployment.created or datetime.now(timezone.utc),
                        )
                    )
            except Exception as e:
                logger.warning(f"Failed to read deployment schedule for {flow.name}: {e}")

            # Get one-time scheduled runs (future only)
            try:
                state_filter = FlowRunFilterStateType(any_=[StateType.SCHEDULED])
                flow_runs = await client.read_flow_runs(
                    deployment_filter=DeploymentFilter(
                        id={"any_": [uuid.UUID(flow.deployment_id)]}
                    ),
                    flow_run_filter=FlowRunFilter(state=FlowRunFilterState(type=state_filter)),
                    limit=limit,  # Use pagination limit
                )

                now = datetime.now(timezone.utc)
                for flow_run in flow_runs:
                    # Only show future scheduled runs
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

    # Sort by next_run time (None values at the end)
    all_schedules.sort(
        key=lambda x: (x.next_run is None, x.next_run or datetime.min.replace(tzinfo=timezone.utc))
    )

    # Apply offset and limit to sorted results
    paginated_schedules = all_schedules[offset : offset + limit]

    return ListFlowSchedulesResponse(schedules=paginated_schedules)


@router.delete(
    "/flows/schedules/{schedule_id}",
    response_model=DeleteScheduleResponse,
    summary="Delete a flow schedule",
    operation_id="deleteFlowSchedule",
)
async def delete_flow_schedule(
    schedule_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
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
        ctx: Project context with user and project information

    Returns:
    -------
        Standardized response with schedule type information

    """
    username = ctx.user.username
    project_id = ctx.project_id
    flow_repo = MongoFlowRepository()

    async with get_client() as client:
        # Try as deployment ID (cron schedule)
        try:
            _ = await client.read_deployment(schedule_id)

            # Verify ownership
            flow = flow_repo.find_one(
                {"project_id": project_id, "deployment_id": schedule_id, "username": username}
            )
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
                flow = flow_repo.find_one(
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


@router.patch(
    "/flows/schedules/{schedule_id}",
    response_model=UpdateScheduleResponse,
    summary="Update a flow schedule",
    operation_id="updateFlowSchedule",
)
async def update_flow_schedule(
    schedule_id: str,
    request: UpdateScheduleRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> UpdateScheduleResponse:
    """Update a Flow schedule (cron schedules only).

    Can update: active status, cron expression, parameters.

    Args:
    ----
        schedule_id: Schedule ID (deployment_id)
        request: Update request
        ctx: Project context with user and project information

    Returns:
    -------
        Success message

    """
    username = ctx.user.username
    project_id = ctx.project_id
    flow_repo = MongoFlowRepository()

    async with get_client() as client:
        try:
            # Verify ownership
            flow = flow_repo.find_one(
                {"project_id": project_id, "deployment_id": schedule_id, "username": username}
            )
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
                        detail=f"Invalid cron expression '{request.cron}': {e!s}",
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
) -> GetFlowResponse:
    """Get Flow details including code content.

    Steps:
    1. Find metadata in MongoDB
    2. Read code from file
    3. Return combined data
    """
    username = ctx.user.username
    project_id = ctx.project_id
    flow_repo = MongoFlowRepository()

    # Find flow in database
    flow = flow_repo.find_by_user_and_name(username, name, project_id)
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

    logger.info(f"[TRACE] get_flow default_run_parameters={flow.default_run_parameters}")
    return GetFlowResponse(
        name=flow.name,
        description=flow.description,
        code=code,
        flow_function_name=flow.flow_function_name,
        chip_id=flow.chip_id,
        default_parameters=flow.default_parameters,
        default_run_parameters=flow.default_run_parameters,
        file_path=flow.file_path,
        created_at=flow.created_at,
        updated_at=flow.updated_at,
        tags=flow.tags,
    )


@router.post(
    "/flows/{name}/execute",
    response_model=ExecuteFlowResponse,
    summary="Execute a flow",
    operation_id="executeFlow",
)
async def execute_flow(
    name: str,
    request: ExecuteFlowRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> ExecuteFlowResponse:
    """Execute a Flow via Prefect deployment.

    Steps:
    1. Find flow metadata in MongoDB
    2. Merge request parameters with default_parameters
    3. Create flow run via Prefect Client
    4. Return execution_id and URLs
    """
    from prefect import get_client

    username = ctx.user.username
    project_id = ctx.project_id
    settings = get_settings()
    flow_repo = MongoFlowRepository()

    # Find flow in database
    flow = flow_repo.find_by_user_and_name(username, name, project_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{name}' not found")

    if not flow.deployment_id:
        raise HTTPException(
            status_code=400,
            detail=f"Flow '{name}' has no deployment. Please re-save the flow to register a deployment.",
        )

    # Merge parameters (request overrides defaults)
    # Add flow_name, project_id, and tags for multi-tenancy support
    parameters: dict[str, Any] = {
        **flow.default_parameters,
        **request.parameters,
        "flow_name": name,  # Add flow name for display purposes
        "project_id": project_id,  # Add project_id for multi-tenancy
    }
    # Pass flow tags if not already overridden by request parameters
    if "tags" not in parameters and flow.tags:
        parameters["tags"] = flow.tags

    logger.info(
        f"Executing flow '{name}' (deployment={flow.deployment_id}) with parameters: {parameters}"
    )

    # Create flow run via Prefect Client
    try:
        async with get_client() as client:
            flow_run = await client.create_flow_run_from_deployment(
                deployment_id=flow.deployment_id,
                parameters=parameters,
            )

            execution_id = str(flow_run.id)
            # Construct URLs
            flow_run_url = (
                f"http://localhost:{settings.prefect_port}/flow-runs/flow-run/{execution_id}"
            )
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
    "/flows/{name}",
    summary="Delete a flow",
    operation_id="deleteFlow",
)
async def delete_flow(
    name: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> dict[str, str]:
    """Delete a Flow.

    Steps:
    1. Delete Prefect deployment
    2. Delete file from user_flows/{username}/{name}.py
    3. Delete metadata from MongoDB
    """
    username = ctx.user.username
    project_id = ctx.project_id
    flow_repo = MongoFlowRepository()

    # Find flow in database
    flow = flow_repo.find_by_user_and_name(username, name, project_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{name}' not found")

    # Delete Prefect deployment
    if flow.deployment_id:
        try:
            async with get_client() as client:
                await client.delete_deployment(flow.deployment_id)
                logger.info(f"Deleted Prefect deployment: {flow.deployment_id}")
        except Exception as e:
            # Log but don't fail - deployment might already be deleted
            logger.warning(f"Failed to delete Prefect deployment (may not exist): {e}")

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
        flow_repo.delete_by_user_and_name(username, name, project_id)
        logger.info(f"Deleted flow '{name}' from database")
    except Exception as e:
        logger.error(f"Failed to delete flow from database: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete flow metadata: {e}")

    return {"message": f"Flow '{name}' deleted successfully"}


@router.post(
    "/flows/{name}/schedule",
    response_model=ScheduleFlowResponse,
    summary="Schedule a flow execution (cron or one-time)",
    operation_id="scheduleFlow",
)
async def schedule_flow(
    name: str,
    request: ScheduleFlowRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> ScheduleFlowResponse:
    """Schedule a Flow execution with cron or one-time schedule.

    Args:
    ----
        name: Flow name
        request: Schedule request (must provide either cron or scheduled_time)
        ctx: Project context with user and project information

    Returns:
    -------
        Schedule response with schedule_id and details

    """
    username = ctx.user.username
    flow_repo = MongoFlowRepository()

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

    project_id = ctx.project_id

    # Find flow
    flow = flow_repo.find_by_user_and_name(username, name, project_id)
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
            detail=f"Flow '{name}' deployment not found in Prefect. Please re-save the flow. Error: {e!s}",
        )

    # Merge parameters - include username, chip_id, and project_id from flow metadata
    parameters: dict[str, Any] = {
        "username": username,
        "chip_id": flow.chip_id,
        **flow.default_parameters,
        **request.parameters,
        "flow_name": name,
        "project_id": ctx.project_id,  # Add project_id for multi-tenancy
    }
    # Pass flow tags if not already overridden by request parameters
    if "tags" not in parameters and flow.tags:
        parameters["tags"] = flow.tags

    logger.info(f"Scheduling flow '{name}' with parameters: {parameters}")

    # Handle cron schedule
    if request.cron:
        # Validate cron expression
        try:
            croniter(request.cron)  # Will raise ValueError if invalid
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid cron expression '{request.cron}': {e!s}",
            )

        try:
            await _http_post_with_retry(
                f"{DEPLOYMENT_SERVICE_URL}/set-schedule",
                {
                    "deployment_id": flow.deployment_id,
                    "cron": request.cron,
                    "timezone": request.timezone,
                    "active": request.active,
                    "parameters": parameters,
                },
            )
            logger.info(f"Set cron schedule for flow '{name}': {request.cron}")

            # Calculate next run time from cron expression
            next_run: datetime | None = None
            try:
                current_time = datetime.now(timezone.utc)
                cron_iter = croniter(request.cron, current_time)
                next_run = cron_iter.get_next(datetime)
            except Exception as e:
                logger.warning(f"Failed to calculate next run time: {e}")

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
            error_detail = e.response.text if hasattr(e.response, "text") else str(e)
            logger.error(f"Failed to set cron schedule: {error_detail}")
            raise HTTPException(
                status_code=e.response.status_code if hasattr(e, "response") else 500,
                detail=f"Failed to set cron schedule: {error_detail}",
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
                "+" in scheduled_time_str[10:]
                or (scheduled_time_str.count("-") > 2 and "-" in scheduled_time_str[19:])
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
                detail=f"Invalid scheduled_time format: {e!s}",
            )

        try:
            data = await _http_post_with_retry(
                f"{DEPLOYMENT_SERVICE_URL}/create-scheduled-run",
                {
                    "deployment_id": flow.deployment_id,
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

    raise HTTPException(status_code=500, detail="Unexpected error in schedule creation")


@router.get(
    "/flows/{name}/schedules",
    response_model=ListFlowSchedulesResponse,
    summary="List schedules for a specific flow",
    operation_id="listFlowSchedules",
)
async def list_flow_schedules(
    name: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    limit: int = 50,  # Default 50, max 100
    offset: int = 0,
) -> ListFlowSchedulesResponse:
    """List all schedules (cron and one-time) for a specific Flow.

    Args:
    ----
        name: Flow name
        ctx: Project context with user and project information
        limit: Maximum number of schedules to return (max 100)
        offset: Number of schedules to skip

    Returns:
    -------
        List of schedules for the flow

    """
    # Enforce max limit
    limit = min(limit, 100)
    username = ctx.user.username
    project_id = ctx.project_id
    flow_repo = MongoFlowRepository()

    # Find flow
    flow = flow_repo.find_by_user_and_name(username, name, project_id)
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
                        created_at=deployment.created or datetime.now(timezone.utc),
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
                            next_run=flow_run.next_scheduled_start_time,
                            active=True,
                            created_at=flow_run.created or datetime.now(timezone.utc),
                        )
                    )
        except Exception as e:
            logger.warning(f"Failed to read scheduled flow runs: {e}")

    return ListFlowSchedulesResponse(schedules=schedules)
