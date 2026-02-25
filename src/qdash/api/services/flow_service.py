"""Service for flow CRUD and execution operations."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from fastapi import HTTPException
from prefect.client.orchestration import get_client
from qdash.api.schemas.flow import (
    ExecuteFlowRequest,
    ExecuteFlowResponse,
    FlowSummary,
    FlowTemplate,
    FlowTemplateWithCode,
    GetFlowResponse,
    ListFlowsResponse,
    SaveFlowRequest,
    SaveFlowResponse,
)
from qdash.common.paths import SERVICE_DIR, TEMPLATES_DIR, USER_FLOWS_DIR
from qdash.config import get_settings

if TYPE_CHECKING:
    from qdash.repository import MongoFlowRepository

logger = logging.getLogger("uvicorn.app")

DEPLOYMENT_SERVICE_URL = os.getenv("DEPLOYMENT_SERVICE_URL", "http://deployment-service:8001")
TEMPLATES_METADATA_FILE = TEMPLATES_DIR / "templates.json"
FLOW_HELPERS_DIR = SERVICE_DIR


class FlowService:
    """Service for flow CRUD operations and execution."""

    def __init__(
        self,
        flow_repository: MongoFlowRepository,
    ) -> None:
        """Initialize the service with a flow repository."""
        self._flow_repo = flow_repository
        self._user_flows_base_dir = USER_FLOWS_DIR

    async def save_flow(
        self,
        request: SaveFlowRequest,
        username: str,
        project_id: str,
    ) -> SaveFlowResponse:
        """Save a Flow to file system and MongoDB.

        Steps:
        1. Validate flow name
        2. Validate flow code contains expected function
        3. Write code to file
        4. Register Prefect deployment
        5. Upsert metadata to MongoDB

        Parameters
        ----------
        request : SaveFlowRequest
            The save flow request.
        username : str
            The username.
        project_id : str
            The project ID.

        Returns
        -------
        SaveFlowResponse
            Save result with name, file path, and message.

        """
        self._validate_flow_name(request.name)

        if request.flow_function_name is None:
            request.flow_function_name = request.name

        self._validate_flow_code(request.code, request.flow_function_name)

        user_dir = self._get_user_flows_dir(username)
        file_path = user_dir / f"{request.name}.py"

        existing_flow = self._flow_repo.find_by_user_and_name(username, request.name, project_id)
        old_deployment_id = existing_flow.deployment_id if existing_flow else None

        # Write code to file
        try:
            file_path.write_text(request.code, encoding="utf-8")
            logger.info(f"Saved flow code to {file_path}")
        except Exception as e:
            logger.error(f"Failed to write flow file: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to save flow file: {e}")

        # Auto-format with ruff
        self._format_with_ruff(file_path)

        # Register Prefect deployment
        try:
            deployment_name = f"{username}-{request.name}"
            deployment_id = await self._register_flow_deployment(
                file_path=str(file_path),
                flow_function_name=request.flow_function_name,
                deployment_name=deployment_name,
                old_deployment_id=old_deployment_id,
            )
            logger.info(f"Registered deployment: {deployment_id}")
        except Exception as e:
            logger.error(f"Failed to register deployment: {e}")
            if file_path.exists():
                file_path.unlink()
            raise HTTPException(status_code=500, detail=f"Failed to register deployment: {e}")

        # Upsert to MongoDB
        try:
            file_path_str = str(file_path)

            if existing_flow:
                logger.info(
                    f"[TRACE] save_flow default_run_parameters={request.default_run_parameters}"
                )
                self._flow_repo.update_flow(
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
                self._flow_repo.create_flow(
                    project_id=project_id,
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
            if file_path.exists():
                file_path.unlink()
            raise HTTPException(status_code=500, detail=f"Failed to save flow metadata: {e}")

        return SaveFlowResponse(
            name=request.name,
            file_path=file_path_str,
            message=message,
        )

    async def list_flows(self, username: str, project_id: str) -> ListFlowsResponse:
        """List all Flows for the current project.

        Parameters
        ----------
        username : str
            The username.
        project_id : str
            The project ID.

        Returns
        -------
        ListFlowsResponse
            List of flow summaries.

        """
        try:
            flows = self._flow_repo.list_by_user(username, project_id)
            logger.info(f"Listed {len(flows)} flows for user '{username}'")

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

    async def get_flow(self, name: str, username: str, project_id: str) -> GetFlowResponse:
        """Get Flow details including code content.

        Parameters
        ----------
        name : str
            Flow name.
        username : str
            The username.
        project_id : str
            The project ID.

        Returns
        -------
        GetFlowResponse
            Flow details with code.

        """
        flow = self._flow_repo.find_by_user_and_name(username, name, project_id)
        if not flow:
            raise HTTPException(status_code=404, detail=f"Flow '{name}' not found")

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

    async def delete_flow(self, name: str, username: str, project_id: str) -> dict[str, str]:
        """Delete a Flow (deployment + file + database).

        Parameters
        ----------
        name : str
            Flow name.
        username : str
            The username.
        project_id : str
            The project ID.

        Returns
        -------
        dict[str, str]
            Success message.

        """
        flow = self._flow_repo.find_by_user_and_name(username, name, project_id)
        if not flow:
            raise HTTPException(status_code=404, detail=f"Flow '{name}' not found")

        # Delete Prefect deployment
        if flow.deployment_id:
            try:
                async with get_client() as client:
                    await client.delete_deployment(flow.deployment_id)
                    logger.info(f"Deleted Prefect deployment: {flow.deployment_id}")
            except Exception as e:
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
            self._flow_repo.delete_by_user_and_name(username, name, project_id)
            logger.info(f"Deleted flow '{name}' from database")
        except Exception as e:
            logger.error(f"Failed to delete flow from database: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to delete flow metadata: {e}")

        return {"message": f"Flow '{name}' deleted successfully"}

    async def execute_flow(
        self,
        name: str,
        request: ExecuteFlowRequest,
        username: str,
        project_id: str,
    ) -> ExecuteFlowResponse:
        """Execute a Flow via Prefect deployment.

        Parameters
        ----------
        name : str
            Flow name.
        request : ExecuteFlowRequest
            Execution request with parameters.
        username : str
            The username.
        project_id : str
            The project ID.

        Returns
        -------
        ExecuteFlowResponse
            Execution result with IDs and URLs.

        """
        settings = get_settings()

        flow = self._flow_repo.find_by_user_and_name(username, name, project_id)
        if not flow:
            raise HTTPException(status_code=404, detail=f"Flow '{name}' not found")

        if not flow.deployment_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Flow '{name}' has no deployment."
                    " Please re-save the flow to register a deployment."
                ),
            )

        parameters: dict[str, Any] = {
            **flow.default_parameters,
            **request.parameters,
            "flow_name": name,
            "project_id": project_id,
        }
        if "tags" not in parameters and flow.tags:
            parameters["tags"] = flow.tags

        logger.info(
            f"Executing flow '{name}' "
            f"(deployment={flow.deployment_id}) "
            f"with parameters: {parameters}"
        )

        try:
            async with get_client() as client:
                flow_run = await client.create_flow_run_from_deployment(
                    deployment_id=flow.deployment_id,
                    parameters=parameters,
                )

                execution_id = str(flow_run.id)
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

    async def re_execute_from_snapshot(
        self,
        flow_name: str,
        source_execution_id: str,
        parameter_overrides: dict[str, Any],
        username: str,
        project_id: str,
    ) -> ExecuteFlowResponse:
        """Re-execute a flow using snapshot parameters from a previous execution.

        Parameters
        ----------
        flow_name : str
            Name of the flow to execute.
        source_execution_id : str
            Execution ID to load snapshot parameters from.
        parameter_overrides : dict[str, Any]
            Additional parameter overrides.
        username : str
            The username.
        project_id : str
            The project ID.

        Returns
        -------
        ExecuteFlowResponse
            Execution result with IDs and URLs.

        """
        settings = get_settings()

        # Try username-specific lookup first, then fallback to project-wide lookup.
        # The executor username may differ from the flow owner (e.g. shared flows).
        flow = self._flow_repo.find_by_user_and_name(username, flow_name, project_id)
        if not flow:
            logger.info(
                f"Flow '{flow_name}' not found for user '{username}', "
                f"trying project-wide lookup (project_id={project_id})"
            )
            flow = self._flow_repo.find_one({"project_id": project_id, "name": flow_name})
        if not flow:
            raise HTTPException(
                status_code=404,
                detail=f"Flow '{flow_name}' not found (user={username}, project={project_id})",
            )

        if not flow.deployment_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Flow '{flow_name}' has no deployment."
                    " Please re-save the flow to register a deployment."
                ),
            )

        parameters: dict[str, Any] = {
            **flow.default_parameters,
            **parameter_overrides,
            "flow_name": flow_name,
            "project_id": project_id,
            "source_execution_id": source_execution_id,
        }
        if "tags" not in parameters and flow.tags:
            parameters["tags"] = flow.tags

        logger.info(
            f"Re-executing flow '{flow_name}' from snapshot {source_execution_id} "
            f"(deployment={flow.deployment_id}) with parameters: {parameters}"
        )

        try:
            async with get_client() as client:
                flow_run = await client.create_flow_run_from_deployment(
                    deployment_id=flow.deployment_id,
                    parameters=parameters,
                )

                execution_id = str(flow_run.id)
                flow_run_url = (
                    f"http://localhost:{settings.prefect_port}/flow-runs/flow-run/{execution_id}"
                )
                qdash_ui_url = f"http://localhost:{settings.ui_port}/execution/{execution_id}"

                logger.info(f"Re-execution flow run created: {execution_id}")

                return ExecuteFlowResponse(
                    execution_id=execution_id,
                    flow_run_url=flow_run_url,
                    qdash_ui_url=qdash_ui_url,
                    message=f"Flow '{flow_name}' re-execution started from snapshot {source_execution_id}",
                )

        except Exception as e:
            logger.error(f"Failed to re-execute flow: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to re-execute flow: {e}")

    async def execute_single_task_from_snapshot(
        self,
        task_name: str,
        qid: str,
        chip_id: str,
        source_execution_id: str,
        username: str,
        project_id: str,
        tags: list[str] | None = None,
        source_task_id: str | None = None,
        parameter_overrides: dict[str, dict[str, Any]] | None = None,
    ) -> ExecuteFlowResponse:
        """Execute a single task via the system single-task-executor deployment.

        This method looks up the system deployment by name (no FlowDocument needed)
        and creates a Prefect flow run to re-execute one task for one qubit.

        Parameters
        ----------
        task_name : str
            Name of the task to execute (e.g., 'CheckRabi')
        qid : str
            Qubit ID to calibrate
        chip_id : str
            Chip ID
        source_execution_id : str
            Execution ID to load snapshot parameters from
        username : str
            The username
        project_id : str
            The project ID
        tags : list[str] | None
            Tags for categorization

        Returns
        -------
        ExecuteFlowResponse
            Execution result with IDs and URLs

        """
        settings = get_settings()
        deployment_name = "single-task-executor/system-single-task"

        try:
            async with get_client() as client:
                deployment = await client.read_deployment_by_name(deployment_name)
        except Exception:
            logger.error(f"System deployment '{deployment_name}' not found")
            raise HTTPException(
                status_code=503,
                detail=("System deployment not available. " "The worker may not have started yet."),
            )

        flow_name = f"re-execute:{task_name}"
        parameters: dict[str, Any] = {
            "username": username,
            "chip_id": chip_id,
            "qid": qid,
            "task_name": task_name,
            "source_execution_id": source_execution_id,
            "project_id": project_id,
            "flow_name": flow_name,
            "tags": tags or [],
            "source_task_id": source_task_id,
            "parameter_overrides": parameter_overrides,
        }

        logger.info(
            f"Executing single task '{task_name}' for qid={qid} "
            f"(deployment={deployment.id}) with parameters: {parameters}"
        )

        try:
            async with get_client() as client:
                flow_run = await client.create_flow_run_from_deployment(
                    deployment_id=deployment.id,
                    parameters=parameters,
                )

                execution_id = str(flow_run.id)
                flow_run_url = (
                    f"http://localhost:{settings.prefect_port}"
                    f"/flow-runs/flow-run/{execution_id}"
                )
                qdash_ui_url = f"http://localhost:{settings.ui_port}/execution/{execution_id}"

                logger.info(f"Single-task flow run created: {execution_id}")

                return ExecuteFlowResponse(
                    execution_id=execution_id,
                    flow_run_url=flow_run_url,
                    qdash_ui_url=qdash_ui_url,
                    message=(
                        f"Single task '{task_name}' (qid={qid}) "
                        f"re-execution started from snapshot {source_execution_id}"
                    ),
                )

        except Exception as e:
            logger.error(f"Failed to execute single task: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to execute single task: {e}",
            )

    async def list_templates(self) -> list[FlowTemplate]:
        """List all available flow templates.

        Returns
        -------
        list[FlowTemplate]
            List of flow templates (metadata only).

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

    async def get_template(self, template_id: str) -> FlowTemplateWithCode:
        """Get flow template details including code content.

        Parameters
        ----------
        template_id : str
            The template ID.

        Returns
        -------
        FlowTemplateWithCode
            Template with code content.

        """
        try:
            if not TEMPLATES_METADATA_FILE.exists():
                raise HTTPException(status_code=404, detail="Templates metadata file not found")

            with open(TEMPLATES_METADATA_FILE, encoding="utf-8") as f:
                templates_data = json.load(f)

            template_data = next((t for t in templates_data if t["id"] == template_id), None)
            if not template_data:
                raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")

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

    async def list_helper_files(self) -> list[str]:
        """List all Python files in the qdash.workflow.service module.

        Returns
        -------
        list[str]
            List of filenames.

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
            if (FLOW_HELPERS_DIR / "__init__.py").exists():
                files.insert(0, "__init__.py")

            files = sorted(set(files), key=lambda x: (x != "__init__.py", x))

            logger.info(f"Listed {len(files)} flow helper files")
            return files

        except Exception as e:
            logger.error(f"Failed to list flow helper files: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to list flow helper files: {e}")

    async def get_helper_file(self, filename: str) -> str:
        """Get the content of a flow helper file.

        Parameters
        ----------
        filename : str
            Name of the Python file.

        Returns
        -------
        str
            File content.

        """
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

    # --- Private helpers ---

    def _get_user_flows_dir(self, username: str) -> Path:
        """Get user's flows directory, create if not exists."""
        user_dir = self._user_flows_base_dir / username
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir

    @staticmethod
    def _validate_flow_name(name: str) -> None:
        """Validate flow name (alphanumeric + underscore only)."""
        if not re.match(r"^[a-zA-Z0-9_]+$", name):
            raise HTTPException(
                status_code=400,
                detail="Flow name must contain only alphanumeric characters and underscores",
            )

    @staticmethod
    def _validate_flow_code(code: str, expected_function_name: str) -> None:
        """Validate that Python code contains the expected @flow decorated function."""
        import ast

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Python syntax error in code: {e}",
            )

        flow_functions = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
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
                detail=(
                    "No @flow decorated function found in code."
                    " Please add @flow decorator to your flow function."
                ),
            )

        if expected_function_name not in flow_functions:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Flow function '{expected_function_name}' not found"
                    f" in code. Found: {', '.join(flow_functions)}."
                    " Please ensure your flow function name"
                    " matches the flow name."
                ),
            )

    @staticmethod
    def _format_with_ruff(file_path: Path) -> None:
        """Auto-format a file with ruff."""
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

    @staticmethod
    async def _register_flow_deployment(
        file_path: str,
        flow_function_name: str,
        deployment_name: str,
        old_deployment_id: str | None = None,
    ) -> str:
        """Register a flow as a Prefect deployment via Workflow service."""
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
                f"HTTP error during deployment registration: "
                f"{e.response.status_code} - {e.response.text}"
            )
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Failed to register deployment:"
                    f" {e.response.status_code}: {e.response.text}"
                ),
            )
        except httpx.HTTPError as e:
            logger.error(f"Failed to register deployment: {type(e).__name__}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to register deployment: {e}",
            )
