"""Declarative calibration pipelines: catalog, validation, and execution."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from qdash.api.dependencies import (
    get_calibration_pipeline_service,
    get_calibration_session_service,
    get_flow_service,
)
from qdash.api.lib.project import (
    ProjectContext,
    get_project_context,
    get_project_context_editor,
)
from qdash.api.schemas.calibration_pipeline import (
    ExecutePipelineRequest,
    ExecutePipelineResponse,
    PipelineCatalogResponse,
    ValidatePipelineRequest,
    ValidatePipelineResponse,
)
from qdash.api.schemas.flow import ExecuteFlowResponse
from qdash.api.services.calibration_pipeline_service import CalibrationPipelineService
from qdash.api.services.calibration_session_service import CalibrationSessionService
from qdash.api.services.flow_service import FlowService
from qdash.api.services.pipeline_launch import record_pipeline_launch

router = APIRouter(prefix="/calibration-pipelines")


@router.get(
    "/catalog",
    response_model=PipelineCatalogResponse,
    summary="Step types, tasks, and spec schema for writing a calibration pipeline",
    operation_id="getCalibrationPipelineCatalog",
)
def get_catalog(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[CalibrationPipelineService, Depends(get_calibration_pipeline_service)],
    backend_name: Annotated[str | None, Query()] = None,
) -> PipelineCatalogResponse:
    """Everything an agent needs to compose a spec: step types with their
    dependencies and default tasks, the backend's tasks by type, and the JSON
    schema of the spec."""
    return service.catalog(ctx.project_id, backend_name)


@router.post(
    "/validate",
    response_model=ValidatePipelineResponse,
    summary="Check a calibration pipeline spec without running it",
    operation_id="validateCalibrationPipeline",
)
def validate_pipeline(
    request: ValidatePipelineRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[CalibrationPipelineService, Depends(get_calibration_pipeline_service)],
) -> ValidatePipelineResponse:
    """Dry run: reports every problem with a path into the spec, and the
    resolved steps and tasks when it would run."""
    return service.validate(
        project_id=ctx.project_id,
        chip_id=request.chip_id,
        spec=request.spec,
        backend_name=request.backend_name,
    )


@router.post(
    "/execute",
    response_model=ExecutePipelineResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Validate and run a calibration pipeline spec",
    operation_id="executeCalibrationPipeline",
)
async def execute_pipeline(
    request: ExecutePipelineRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[CalibrationPipelineService, Depends(get_calibration_pipeline_service)],
    flows: Annotated[FlowService, Depends(get_flow_service)],
    sessions: Annotated[CalibrationSessionService, Depends(get_calibration_session_service)],
) -> ExecutePipelineResponse:
    """Runs the spec as one execution through the worker's calibration-pipeline
    deployment. A spec with problems is rejected with 422 and the same problem
    list that /validate returns.

    With ``calibration_session_id`` the run is recorded in that calibration
    session before it is launched, and ``idempotency_key`` makes a retry return
    the recorded run instead of starting another."""

    def validate() -> ValidatePipelineResponse:
        result = service.validate(
            project_id=ctx.project_id,
            chip_id=request.chip_id,
            spec=request.spec,
            backend_name=request.backend_name,
        )
        if not result.valid or result.spec is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": "calibration pipeline spec is not valid",
                    "problems": [problem.model_dump() for problem in result.problems],
                },
            )
        return result

    async def dispatch(result: ValidatePipelineResponse) -> ExecuteFlowResponse:
        assert result.spec is not None  # validate() refused a spec without one
        dispatched = await flows.execute_calibration_pipeline(
            spec=result.spec,
            chip_id=request.chip_id,
            username=ctx.user.username,
            project_id=ctx.project_id,
            backend_name=result.backend_name,
        )
        # Only what the caller reported, stored as reported; it never decides anything here.
        record_pipeline_launch(
            project_id=ctx.project_id,
            chip_id=request.chip_id,
            username=ctx.user.username,
            dispatched=dispatched,
            reported_origin=request.reported_origin,
        )
        return dispatched

    def response(
        result: ValidatePipelineResponse, dispatched: ExecuteFlowResponse
    ) -> dict[str, Any]:
        return ExecutePipelineResponse(
            **dispatched.model_dump(),
            steps=result.steps,
            targets=result.targets,
        ).model_dump(mode="json")

    if request.calibration_session_id is None or request.idempotency_key is None:
        validated = validate()
        return ExecutePipelineResponse.model_validate(
            response(validated, await dispatch(validated))
        )

    recorded = await sessions.execute_pipeline(
        project_id=ctx.project_id,
        username=ctx.user.username,
        calibration_session_id=request.calibration_session_id,
        idempotency_key=request.idempotency_key,
        chip_id=request.chip_id,
        spec=request.spec,
        backend_name=request.backend_name,
        validate=validate,
        dispatch=dispatch,
        response=response,
        reported_origin=request.reported_origin,
        decision_id=request.decision_id,
    )
    return ExecutePipelineResponse.model_validate(
        {
            **recorded.response,
            "calibration_session_id": request.calibration_session_id,
            "pipeline_run_id": recorded.run_id,
            # The request hash includes the decision, so a replay carries the same link.
            "decision_id": request.decision_id,
            "replayed": recorded.replayed,
        }
    )
