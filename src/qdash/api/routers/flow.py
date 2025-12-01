"""API router for user-defined flows."""

import json
import re
from datetime import datetime
from logging import getLogger
from pathlib import Path
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from qdash.api.lib.auth import get_current_active_user
from qdash.api.schemas.auth import User
from qdash.api.schemas.flow import (
    ExecuteFlowRequest,
    ExecuteFlowResponse,
    FlowTemplate,
    FlowTemplateWithCode,
    GetFlowResponse,
    ListFlowsResponse,
    SaveFlowRequest,
    SaveFlowResponse,
)
from qdash.config import get_settings
from qdash.dbmodel.flow import FlowDocument

router = APIRouter()
logger = getLogger("uvicorn.app")

# Base directory for user flows (shared volume between API and Workflow containers)
USER_FLOWS_BASE_DIR = Path("/app/qdash/workflow/user_flows")

# Deployment service URL (Deployment service container - internal Docker network)
DEPLOYMENT_SERVICE_URL = "http://deployment-service:8001"

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
