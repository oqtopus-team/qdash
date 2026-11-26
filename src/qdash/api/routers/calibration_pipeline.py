"""Declarative calibration pipelines: catalog, validation, and execution."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from qdash.api.dependencies import (
    get_calibration_pipeline_service,
    get_calibration_session_service,
    get_flow_service,
    get_pipeline_plan_service,
)
from qdash.api.lib.project import (
    ProjectContext,
    get_project_context,
    get_project_context_editor,
)
from qdash.api.schemas.calibration_pipeline import (
    CreatePipelinePlanRequest,
    ExecutePipelinePlanRequest,
    ExecutePipelineRequest,
    ExecutePipelineResponse,
    PipelineCatalogResponse,
    PipelinePlanResponse,
    ValidatePipelineRequest,
    ValidatePipelineResponse,
)
from qdash.api.schemas.flow import ExecuteFlowResponse
from qdash.api.services.calibration_pipeline_plan_service import (
    PipelinePlanService,
    ValidatedPlan,
)
from qdash.api.services.calibration_pipeline_service import CalibrationPipelineService
from qdash.api.services.calibration_session_service import CalibrationSessionService
from qdash.api.services.flow_service import FlowService
from qdash.api.services.pipeline_launch import record_pipeline_launch
from qdash.api.services.run_ledger import (
    RecordedPlan,
    RunLedger,
    pipeline_request_hash,
    plan_request_hash,
)
from qdash.datamodel.run import RunIdentity, RunKind

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
    """Dispatch one pipeline run. Each step the worker reaches creates an execution.

    An invalid spec returns 422 with the same problems as /validate.

    The run is recorded before it is launched. It joins ``calibration_session_id``
    when given; otherwise QDash creates an automatic calibration session.
    ``idempotency_key`` makes a retry return the
    recorded run instead of starting another."""

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

    async def dispatch(
        result: ValidatePipelineResponse, identity: RunIdentity | None
    ) -> ExecuteFlowResponse:
        assert result.spec is not None  # validate() refused a spec without one
        dispatched = await flows.execute_calibration_pipeline(
            spec=result.spec,
            chip_id=request.chip_id,
            username=ctx.user.username,
            project_id=ctx.project_id,
            backend_name=result.backend_name,
            calibration_run=identity,
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

    recorded = await RunLedger(sessions).launch(
        project_id=ctx.project_id,
        username=ctx.user.username,
        chip_id=request.chip_id,
        kind=RunKind.PIPELINE,
        run_name=str(request.spec.get("name") or ""),
        request_hash=pipeline_request_hash(
            request.chip_id, request.spec, request.backend_name, request.decision_id
        ),
        calibration_session_id=request.calibration_session_id,
        idempotency_key=request.idempotency_key,
        validate=validate,
        dispatch=dispatch,
        response=response,
        recorded_spec=lambda result: result.spec or request.spec,
        backend_name=request.backend_name,
        reported_origin=request.reported_origin,
        decision_id=request.decision_id,
        # A pipeline claims the whole chip; refuse it before anything is recorded.
        preflight=lambda _: flows.ensure_hardware_available(
            project_id=ctx.project_id,
            chip_id=request.chip_id,
            parameters={},
            workflow=True,
        ),
    )
    return ExecutePipelineResponse.model_validate(
        {
            **recorded.response,
            "calibration_session_id": recorded.calibration_session_id,
            "calibration_run_id": recorded.run_id,
            "pipeline_run_id": recorded.run_id,
            # The request hash includes the decision, so a replay carries the same link.
            "decision_id": request.decision_id,
            "replayed": recorded.replayed,
        }
    )


@router.post(
    "/plans",
    response_model=PipelinePlanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Store a validated calibration pipeline spec as a plan to approve by reference",
    operation_id="createCalibrationPipelinePlan",
)
def create_plan(
    request: CreatePipelinePlanRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    plans: Annotated[PipelinePlanService, Depends(get_pipeline_plan_service)],
) -> PipelinePlanResponse:
    """Validate the spec and store it, with its review content and review digest.

    A plan is a proposal: it starts no run, reserves no hardware, joins no calibration
    session, and grants nothing. An invalid spec returns 422 with the same problems as
    /validate and stores nothing. Default task lists are written into the stored spec and
    MUX targets are expanded, so what is reviewed is what runs. The plan expires after 24
    hours and is never renewed. ``idempotency_key`` names this creation: repeating it
    returns the same plan (409 for another request, 410 once it expired)."""
    return plans.create(
        project_id=ctx.project_id,
        username=ctx.user.username,
        chip_id=request.chip_id,
        spec=request.spec,
        backend_name=request.backend_name,
        idempotency_key=request.idempotency_key,
    )


@router.get(
    "/plans/{plan_id}",
    response_model=PipelinePlanResponse,
    summary="Read a stored calibration pipeline plan",
    operation_id="getCalibrationPipelinePlan",
)
def get_plan(
    plan_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    plans: Annotated[PipelinePlanService, Depends(get_pipeline_plan_service)],
) -> PipelinePlanResponse:
    """The plan with its review content; ``expired`` says whether it can still run. Only
    its creator reads it: another user's plan, or one of another project, is not found."""
    return plans.get(project_id=ctx.project_id, username=ctx.user.username, plan_id=plan_id)


async def _require_plan_deployment(flows: FlowService) -> None:
    """Refuse a stored plan's run while no deployment accepts an approved plan."""
    await flows.approved_plan_deployment()


@router.post(
    "/plans/{plan_id}/execute",
    response_model=ExecutePipelineResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run a stored calibration pipeline plan exactly as it was approved",
    operation_id="executeCalibrationPipelinePlan",
)
async def execute_plan(
    plan_id: str,
    request: ExecutePipelinePlanRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    plans: Annotated[PipelinePlanService, Depends(get_pipeline_plan_service)],
    flows: Annotated[FlowService, Depends(get_flow_service)],
    sessions: Annotated[CalibrationSessionService, Depends(get_calibration_session_service)],
) -> ExecutePipelineResponse:
    """Dispatch the plan's spec as one pipeline run, recorded like /execute.

    A retry with the same ``idempotency_key`` and request returns the recorded run first,
    even after the plan expired or was deleted. Otherwise the plan is read again and must be
    the user's, unexpired, for ``chip_id`` (and ``backend_name`` when given), and have
    ``expected_review_digest``; its spec is validated again, and its review content resolved
    now must still have that digest. Then the hardware, session, and decision checks of
    /execute apply. The worker receives the approved review content and refuses to measure
    when what it would run differs."""

    def validate() -> ValidatedPlan:
        return plans.for_execution(
            project_id=ctx.project_id,
            username=ctx.user.username,
            plan_id=plan_id,
            chip_id=request.chip_id,
            backend_name=request.backend_name,
            expected_review_digest=request.expected_review_digest,
        )

    async def dispatch(plan: ValidatedPlan, identity: RunIdentity | None) -> ExecuteFlowResponse:
        dispatched = await flows.execute_calibration_pipeline(
            spec=plan.spec,
            chip_id=request.chip_id,
            username=ctx.user.username,
            project_id=ctx.project_id,
            backend_name=plan.backend_name,
            calibration_run=identity,
            approved_plan={
                "plan_id": plan.doc.plan_id,
                "review_digest": plan.doc.review_digest,
                "review": plan.review,
            },
        )
        record_pipeline_launch(
            project_id=ctx.project_id,
            chip_id=request.chip_id,
            username=ctx.user.username,
            dispatched=dispatched,
            reported_origin=request.reported_origin,
        )
        return dispatched

    def response(plan: ValidatedPlan, dispatched: ExecuteFlowResponse) -> dict[str, Any]:
        return ExecutePipelineResponse(
            **dispatched.model_dump(),
            steps=plan.steps,
            targets=plan.targets,
            plan_id=plan.doc.plan_id,
            review_digest=plan.doc.review_digest,
        ).model_dump(mode="json")

    recorded = await RunLedger(sessions).launch(
        project_id=ctx.project_id,
        username=ctx.user.username,
        chip_id=request.chip_id,
        kind=RunKind.PIPELINE,
        # A display name only: a replay or a refusal never depends on the plan being there.
        run_name=plans.display_name(ctx.project_id, ctx.user.username, plan_id),
        request_hash=plan_request_hash(
            plan_id,
            request.expected_review_digest,
            request.chip_id,
            request.backend_name,
            request.decision_id,
        ),
        calibration_session_id=request.calibration_session_id,
        idempotency_key=request.idempotency_key,
        validate=validate,
        dispatch=dispatch,
        response=response,
        recorded_spec=lambda plan: plan.spec,
        recorded_plan=lambda plan: RecordedPlan(
            plan_id=plan.doc.plan_id, review_digest=plan.doc.review_digest, review=plan.review
        ),
        backend_name=request.backend_name,
        reported_origin=request.reported_origin,
        decision_id=request.decision_id,
        preflight=lambda _: flows.ensure_hardware_available(
            project_id=ctx.project_id,
            chip_id=request.chip_id,
            parameters={},
            workflow=True,
        ),
        # Before anything is recorded or reserved: a pipeline deployment that does not accept
        # an approved plan refuses the run (503). Dispatch resolves and checks it again.
        async_preflight=lambda _: _require_plan_deployment(flows),
    )
    return ExecutePipelineResponse.model_validate(
        {
            **recorded.response,
            "calibration_session_id": recorded.calibration_session_id,
            "calibration_run_id": recorded.run_id,
            "pipeline_run_id": recorded.run_id,
            "decision_id": request.decision_id,
            "replayed": recorded.replayed,
        }
    )
