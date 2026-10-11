"""Calibration evaluation runs: bulk `qcal_evaluate` without a planner.

The chip page requests a run over the latest result of one task; the API
executes it in the background through the Pi Agent Runtime and stores one
evaluation record per task result, including what the evaluation model saw,
so runs can be compared and judged by people afterwards.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.security import (
    HTTPAuthorizationCredentials,  # noqa: TC002 - FastAPI resolves annotations
)

from qdash.api.dependencies import get_evaluation_service
from qdash.api.lib.auth import bearer_scheme
from qdash.api.lib.project import (
    ProjectContext,
    get_project_context,
    get_project_context_editor,
)
from qdash.api.schemas.evaluation import (
    CreateEvaluationRunRequest,
    CreateEvaluationRunResponse,
    EvaluationItem,
    EvaluationRunDetailResponse,
    ListEvaluationRunsResponse,
    ListEvaluationsResponse,
    SetEvaluationVerdictRequest,
)
from qdash.api.services.evaluation_service import (
    EvaluationService,
)
from qdash.api.services.pi_chat_service import QDashAuth

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "/evaluations/runs",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a bulk calibration evaluation run",
    operation_id="createEvaluationRun",
    response_model=CreateEvaluationRunResponse,
)
async def create_evaluation_run(
    body: CreateEvaluationRunRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
) -> CreateEvaluationRunResponse:
    """Queue the latest evaluable result of a task for every entity on a chip.

    The evaluations run in the background as the requesting user; poll the run
    for progress. Entities without an evaluable result are reported as skipped.
    """
    selection = service.request_run(
        project_id=ctx.project_id,
        chip_id=body.chip_id,
        task=body.task,
        entity_type=body.entity_type,
        date=body.date,
        task_ids=body.task_ids,
        question=body.question,
        trigger=body.trigger,
        mode=body.mode,
        requested_by=ctx.user.username,
    )
    service.launch(
        selection.run.run_id,
        QDashAuth(access_token=credentials.credentials, project_id=ctx.project_id),
    )
    logger.info(
        "evaluation run %s started: chip=%s task=%s items=%d by %s",
        selection.run.run_id,
        body.chip_id,
        body.task,
        len(selection.evaluations),
        ctx.user.username,
    )
    return CreateEvaluationRunResponse(
        run=service.summarize(selection.run),
        task_ids=[doc.task_id for doc in selection.evaluations],
        skipped=selection.skipped,
    )


@router.get(
    "/evaluations/runs",
    summary="List calibration evaluation runs",
    operation_id="listEvaluationRuns",
    response_model=ListEvaluationRunsResponse,
)
def list_evaluation_runs(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
    chip_id: Annotated[str | None, Query(description="Only runs on this chip")] = None,
    task: Annotated[str | None, Query(description="Only runs of this task")] = None,
    limit: Annotated[int, Query(ge=1, le=200, description="Newest runs to return")] = 20,
) -> ListEvaluationRunsResponse:
    """List runs of the project, newest first."""
    return ListEvaluationRunsResponse(
        runs=service.list_runs(project_id=ctx.project_id, chip_id=chip_id, task=task, limit=limit)
    )


@router.get(
    "/evaluations/runs/{run_id}",
    summary="Get a calibration evaluation run",
    operation_id="getEvaluationRun",
    response_model=EvaluationRunDetailResponse,
)
def get_evaluation_run(
    run_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
) -> EvaluationRunDetailResponse:
    """One run with every evaluation, including what the model saw and answered."""
    return service.get_run(project_id=ctx.project_id, run_id=run_id)


@router.get(
    "/evaluations",
    summary="List evaluations of a task result",
    operation_id="listEvaluations",
    response_model=ListEvaluationsResponse,
)
def list_evaluations(
    task_id: Annotated[str, Query(description="Task result ID")],
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
) -> ListEvaluationsResponse:
    """Every evaluation of one task result across runs, newest first."""
    return ListEvaluationsResponse(
        evaluations=service.list_for_task(project_id=ctx.project_id, task_id=task_id)
    )


@router.put(
    "/evaluations/{evaluation_id}/verdict",
    summary="Judge a calibration evaluation",
    operation_id="setEvaluationVerdict",
    response_model=EvaluationItem,
)
def set_evaluation_verdict(
    evaluation_id: str,
    body: SetEvaluationVerdictRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
) -> EvaluationItem:
    """Record whether a person agrees with an evaluation; null agree and no note clears it."""
    return service.set_verdict(
        project_id=ctx.project_id,
        evaluation_id=evaluation_id,
        agree=body.agree,
        note=body.note,
        username=ctx.user.username,
    )
