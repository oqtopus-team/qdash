"""Application service for project flow CRUD, templates and execution."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException

from qdash.api.schemas.execution import (
    ExecutionAvailabilityRequest,
    ExecutionAvailabilityResponse,
)
from qdash.api.schemas.flow import (
    ExecuteFlowRequest,
    ExecuteFlowResponse,
    FlowSummary,
    FlowTemplate,
    FlowTemplateWithCode,
    GetFlowResponse,
    ListFlowsResponse,
    MoveFlowResponse,
    SaveFlowRequest,
    SaveFlowResponse,
)
from qdash.api.services.flow_service.deployment_client import DeploymentServiceClient
from qdash.api.services.flow_service.execution import (
    DispatchResult,
    ExecutionCoordinator,
    FlowDispatchError,
)
from qdash.api.services.flow_service.prefect_gateway import SystemDeploymentUnavailable
from qdash.api.services.flow_service.source_store import FlowSourceStore
from qdash.api.services.flow_service.templates import TemplateCatalog
from qdash.api.services.flow_service.validation import (
    format_with_ruff,
    normalize_folder,
    validate_flow_code,
    validate_flow_name,
)
from qdash.config import get_settings

if TYPE_CHECKING:
    from uuid import UUID

    from qdash.repository import MongoExecutionLockRepository, MongoFlowRepository

logger = logging.getLogger("uvicorn.app")


class FlowService:
    """Coordinate flow storage, deployment registration and execution dispatch."""

    def __init__(
        self,
        flow_repository: MongoFlowRepository,
        execution_lock_repository: MongoExecutionLockRepository | None = None,
        *,
        coordinator: ExecutionCoordinator | None = None,
        source_store: FlowSourceStore | None = None,
        deployment_client: DeploymentServiceClient | None = None,
        templates: TemplateCatalog | None = None,
    ) -> None:
        """Wire the flow repository and the collaborators it coordinates."""
        self._flow_repo = flow_repository
        self._coordinator = coordinator or ExecutionCoordinator(
            lock_repository=execution_lock_repository,
        )
        self._sources = source_store or FlowSourceStore()
        self._deployment = deployment_client or DeploymentServiceClient()
        self._templates = templates or TemplateCatalog()

    async def save_flow(
        self,
        request: SaveFlowRequest,
        username: str,
        project_id: str,
    ) -> SaveFlowResponse:
        """Validate, store and deploy a flow, then upsert its metadata.

        On an update with an existing file, a failed registration or metadata
        write puts the previous source back; otherwise it removes the file it
        just wrote. The previous deployment may already have been replaced.
        """
        validate_flow_name(request.name)
        # None keeps the stored folder, so a client that does not know about
        # folders (the Copilot's save tool) does not move the flow to the root.
        folder = normalize_folder(request.folder) if request.folder is not None else None

        if request.flow_function_name is None:
            request.flow_function_name = request.name

        validate_flow_code(request.code, request.flow_function_name)

        file_path = self._sources.path_for(project_id, request.name)
        file_path_str = str(file_path)
        existing_flow = self._flow_repo.find_by_project_and_name(project_id, request.name)
        old_deployment_id = existing_flow.deployment_id if existing_flow else None

        # Read the old source on an update path, so we can restore it if the
        # registration or the metadata write fails later.
        old_source: str | None = None
        if existing_flow and self._sources.exists(file_path):
            old_source = self._sources.read(file_path)

        self._sources.write(file_path, request.code)
        format_with_ruff(file_path)

        deployment_name = f"{project_id}-{request.name}"
        try:
            deployment_id = await self._deployment.register(
                file_path=str(self._sources.to_deployment_path(file_path)),
                flow_function_name=request.flow_function_name,
                deployment_name=deployment_name,
                old_deployment_id=old_deployment_id,
            )
            logger.info(f"Registered deployment: {deployment_id}")
        except Exception as exc:
            logger.error(f"Failed to register deployment: {exc}")
            if existing_flow and old_source is not None:
                self._sources.write(file_path, old_source)
            else:
                self._discard_file(file_path)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to register deployment: {exc}",
            ) from exc

        try:
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
                    folder=folder,
                )
                logger.info(
                    f"Updated flow '{request.name}' in project '{project_id}' by user '{username}'"
                )
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
                    folder=folder or "",
                )
                logger.info(
                    f"Created new flow '{request.name}' in project '{project_id}'"
                    f" by user '{username}'"
                )
                message = f"Flow '{request.name}' created successfully"
        except Exception as exc:
            logger.error(f"Failed to save flow to database: {exc}")
            # On an update, restore the previous source rather than deleting
            # the new file. The deployment was already registered against the
            # new path, so removing it would leave a dangling registration.
            # On a create, discard the file so a half-saved flow never keeps
            # a source that is not registered.
            if existing_flow and old_source is not None:
                self._sources.write(file_path, old_source)
            else:
                self._discard_file(file_path)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save flow metadata: {exc}",
            ) from exc

        return SaveFlowResponse(
            name=request.name,
            file_path=file_path_str,
            message=message,
        )

    async def list_flows(self, username: str, project_id: str) -> ListFlowsResponse:
        """List the flows stored for a project."""
        try:
            flows = self._flow_repo.list_by_project(project_id)
            logger.info(
                f"Listed {len(flows)} flows in project '{project_id}' for user '{username}'"
            )

            flow_summaries = [
                FlowSummary(
                    name=flow.name,
                    created_by=flow.username,
                    description=flow.description,
                    chip_id=flow.chip_id,
                    flow_function_name=flow.flow_function_name,
                    created_at=flow.created_at,
                    updated_at=flow.updated_at,
                    tags=flow.tags,
                    folder=flow.folder,
                    file_exists=self._sources.exists(Path(flow.file_path)),
                )
                for flow in flows
            ]

            return ListFlowsResponse(flows=flow_summaries)
        except Exception as exc:
            logger.error(f"Failed to list flows: {exc}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to list flows: {exc}",
            ) from exc

    async def get_flow(self, name: str, username: str, project_id: str) -> GetFlowResponse:
        """Return a flow's metadata together with its stored source."""
        flow = self._flow_repo.find_by_project_and_name(project_id, name)
        if not flow:
            raise HTTPException(status_code=404, detail=f"Flow '{name}' not found")

        file_path = Path(flow.file_path)
        if not self._sources.exists(file_path):
            logger.error(f"Flow file not found: {file_path}")
            raise HTTPException(status_code=404, detail=f"Flow file not found: {file_path}")

        code = self._sources.read(file_path)
        logger.info(f"[TRACE] get_flow default_run_parameters={flow.default_run_parameters}")
        return GetFlowResponse(
            name=flow.name,
            created_by=flow.username,
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
            folder=flow.folder,
        )

    async def move_flow(self, name: str, project_id: str, folder: str) -> MoveFlowResponse:
        """Move a Flow to another folder; only the stored metadata changes.

        The name, file and Prefect deployment stay as they are, so a move is
        instant and cannot break a running or scheduled flow.
        """
        flow = self._flow_repo.find_by_project_and_name(project_id, name)
        if not flow:
            raise HTTPException(status_code=404, detail=f"Flow '{name}' not found")
        normalized = normalize_folder(folder)
        self._flow_repo.update_flow(flow=flow, folder=normalized)
        logger.info(f"Moved flow '{name}' in project '{project_id}' to folder '{normalized}'")
        return MoveFlowResponse(
            name=name,
            folder=normalized,
            message=f"Flow '{name}' moved to '{normalized or '/'}'",
        )

    async def delete_flow(self, name: str, username: str, project_id: str) -> dict[str, str]:
        """Delete a flow's deployment, source file and metadata."""
        flow = self._flow_repo.find_by_project_and_name(project_id, name)
        if not flow:
            raise HTTPException(status_code=404, detail=f"Flow '{name}' not found")

        if flow.deployment_id:
            await self._coordinator.delete_deployment(str(flow.deployment_id))

        file_path = Path(flow.file_path)
        if self._sources.exists(file_path):
            self._sources.delete(file_path)

        try:
            self._flow_repo.delete_by_project_and_name(project_id, name)
            logger.info(f"Deleted flow '{name}' from project '{project_id}' by user '{username}'")
        except Exception as exc:
            logger.error(f"Failed to delete flow from database: {exc}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete flow metadata: {exc}",
            ) from exc

        return {"message": f"Flow '{name}' deleted successfully"}

    async def execute_flow(
        self,
        name: str,
        request: ExecuteFlowRequest,
        username: str,
        project_id: str,
    ) -> ExecuteFlowResponse:
        """Execute a saved flow through its Prefect deployment."""
        flow = self._flow_repo.find_by_project_and_name(project_id, name)
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
            "username": username,
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

        chip_id = str(parameters.get("chip_id") or flow.chip_id or "").strip()
        try:
            result = await self._coordinator.dispatch_run(
                project_id=project_id,
                username=username,
                chip_id=chip_id,
                name=name,
                deployment_id=flow.deployment_id,
                parameters=parameters,
                tags=parameters.get("tags") or flow.tags,
                workflow=True,
            )
        except FlowDispatchError as exc:
            logger.error(f"Failed to execute flow: {exc}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to execute flow: {exc}",
            ) from exc

        logger.info(f"Flow run created: {result.flow_run_id}")
        return _execute_response(result, f"Flow '{name}' execution started successfully")

    async def execute_single_task_from_snapshot(
        self,
        task_name: str,
        qid: str,
        chip_id: str,
        source_execution_id: str | None,
        username: str,
        project_id: str,
        tags: list[str] | None = None,
        source_task_id: str | None = None,
        parameter_overrides: dict[str, dict[str, Any]] | None = None,
        update_params: bool = True,
        persist_output_parameters: bool = True,
        reconfigure: bool = False,
        execution_name: str | None = None,
        backend_name: str | None = None,
        default_run_parameters: dict[str, Any] | None = None,
        task_run_parameters: dict[str, dict[str, Any]] | None = None,
    ) -> ExecuteFlowResponse:
        """Execute one task for one qubit through the system single-task deployment.

        The deployment is looked up by name, so no FlowDocument is involved, and
        the run claims the same execution lock as a full workflow.
        """
        deployment_name = "single-task-executor/system-single-task"
        deployment_id = await self._system_deployment(deployment_name)

        flow_name = execution_name or f"re-execute:{task_name}"
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
            "persist_output_parameters": persist_output_parameters,
            "update_params": update_params,
            "reconfigure": reconfigure,
            "backend_name": backend_name,
            "default_run_parameters": default_run_parameters,
            "task_run_parameters": task_run_parameters,
        }

        logger.info(
            f"Executing single task '{task_name}' for qid={qid} "
            f"(deployment={deployment_id}) with parameters: {parameters}"
        )

        try:
            result = await self._coordinator.dispatch_run(
                project_id=project_id,
                username=username,
                chip_id=chip_id,
                name=flow_name,
                deployment_id=deployment_id,
                parameters=parameters,
                tags=tags,
            )
        except FlowDispatchError as exc:
            logger.error(f"Failed to execute single task: {exc}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to execute single task: {exc}",
            ) from exc

        logger.info(f"Single-task flow run created: {result.flow_run_id}")
        return _execute_response(
            result,
            f"Single task '{task_name}' (qid={qid}) "
            f"re-execution started from snapshot {source_execution_id}",
        )

    async def execute_calibration_pipeline(
        self,
        *,
        spec: dict[str, Any],
        chip_id: str,
        username: str,
        project_id: str,
        backend_name: str | None = None,
        flow_name: str | None = None,
        tags: list[str] | None = None,
    ) -> ExecuteFlowResponse:
        """Run a validated pipeline spec through the system pipeline deployment.

        The caller (``CalibrationPipelineService``) has already validated the
        spec; this only claims the execution lock, creates the Prefect run, and
        pre-creates the execution row, exactly as a saved flow would.
        """
        deployment_id = await self._system_deployment(
            "calibration-pipeline/system-calibration-pipeline",
            unavailable_detail=(
                "Calibration pipeline deployment not available."
                " The worker may not have started yet."
            ),
        )

        name = flow_name or str(spec.get("name") or "pipeline")
        all_tags = sorted({*(tags or []), *(spec.get("tags") or []), "pipeline"})
        parameters: dict[str, Any] = {
            "username": username,
            "chip_id": chip_id,
            "spec": spec,
            "project_id": project_id,
            "flow_name": name,
            "tags": all_tags,
            "backend_name": backend_name,
        }
        logger.info(
            f"Executing calibration pipeline '{name}' on chip {chip_id} "
            f"(deployment={deployment_id}, steps={len(spec.get('steps') or [])})"
        )

        try:
            result = await self._coordinator.dispatch_run(
                project_id=project_id,
                username=username,
                chip_id=chip_id,
                name=name,
                deployment_id=deployment_id,
                parameters=parameters,
                tags=all_tags,
                workflow=True,
            )
        except FlowDispatchError as exc:
            logger.error(f"Failed to execute calibration pipeline: {exc}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to execute calibration pipeline: {exc}",
            ) from exc

        logger.info(f"Pipeline flow run created: {result.flow_run_id}")
        return _execute_response(result, f"Calibration pipeline '{name}' started")

    async def execute_agent_candidate_apply(
        self,
        *,
        project_id: str,
        session_id: str,
        commit_id: str,
        push_to_github: bool,
    ) -> ExecuteFlowResponse:
        """Dispatch worker-side application of one audited agent candidate commit."""
        deployment_id = await self._system_deployment(
            "agent-candidate-apply/system-candidate-apply",
            unavailable_detail="Agent candidate apply deployment is not available",
        )

        parameters = {
            "project_id": project_id,
            "session_id": session_id,
            "commit_id": commit_id,
            "push_to_github": push_to_github,
        }
        try:
            operation_id = await self._coordinator.dispatch_background(
                deployment_id=deployment_id,
                parameters=parameters,
            )
        except FlowDispatchError as exc:
            logger.error(f"Failed to dispatch agent candidate apply: {exc}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to dispatch agent candidate apply: {exc}",
            ) from exc

        settings = get_settings()
        return ExecuteFlowResponse(
            execution_id=operation_id,
            flow_run_id=operation_id,
            flow_run_url=f"http://localhost:{settings.prefect_port}/runs/flow-run/{operation_id}",
            qdash_ui_url=f"http://localhost:{settings.ui_port}/",
            message=f"Agent candidate commit '{commit_id}' queued for backend application",
        )

    async def list_templates(self, backend: str | None = None) -> list[FlowTemplate]:
        """List the available flow templates, optionally only those for one backend."""
        return self._templates.list_templates(backend)

    async def get_template(self, template_id: str) -> FlowTemplateWithCode:
        """Return one flow template together with its source."""
        return self._templates.get_template(template_id)

    async def list_helper_files(self) -> list[str]:
        """List the helper modules importable from a user flow."""
        return self._templates.list_helper_files()

    async def get_helper_file(self, filename: str) -> str:
        """Return the source of one helper module."""
        return self._templates.get_helper_file(filename)

    def check_execution_availability(
        self, request: ExecutionAvailabilityRequest, project_id: str
    ) -> ExecutionAvailabilityResponse:
        """Preview admission using the same saved defaults and wiring as execution."""
        parameters = dict(request.parameters)
        fallback_chip_id = ""
        if request.flow_name is not None:
            flow = self._flow_repo.find_by_project_and_name(project_id, request.flow_name)
            if flow is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Flow '{request.flow_name}' not found",
                )
            parameters = {**flow.default_parameters, **parameters}
            fallback_chip_id = flow.chip_id or ""

        chip_id = str(parameters.get("chip_id") or fallback_chip_id).strip()
        if not chip_id:
            return ExecutionAvailabilityResponse(
                available=False, reason="Select a chip to check execution availability."
            )

        available, reason = self._coordinator.availability(
            project_id=project_id,
            chip_id=chip_id,
            parameters=parameters,
            workflow=request.flow_name is not None,
        )
        return ExecutionAvailabilityResponse(available=available, reason=reason)

    async def _system_deployment(
        self,
        deployment_name: str,
        *,
        unavailable_detail: str = (
            "System deployment not available. The worker may not have started yet."
        ),
    ) -> UUID:
        """Resolve a system deployment or report it as not started yet."""
        try:
            return await self._coordinator.read_deployment_id(deployment_name)
        except SystemDeploymentUnavailable as exc:
            raise HTTPException(status_code=503, detail=unavailable_detail) from exc

    @staticmethod
    def _discard_file(file_path: Path) -> None:
        """Remove a file written for a save that could not be completed."""
        if file_path.exists():
            file_path.unlink()


def _execute_response(result: DispatchResult, message: str) -> ExecuteFlowResponse:
    """Map a dispatched run onto the API response, falling back to the flow run ID."""
    return ExecuteFlowResponse(
        execution_id=result.execution_id or result.flow_run_id,
        flow_run_id=result.flow_run_id,
        flow_run_url=result.flow_run_url,
        qdash_ui_url=result.qdash_ui_url,
        message=message,
    )
