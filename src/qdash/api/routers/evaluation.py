"""Calibration evaluation runs: bulk `qcal_evaluate` without a planner.

The chip page requests a run over the latest result of one task; the API
executes it in the background through the Pi Agent Runtime and stores one
evaluation record per task result, including what the evaluation model saw,
so runs can be compared and judged by people afterwards.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, UploadFile, status
from fastapi.responses import FileResponse, Response
from fastapi.security import (
    HTTPAuthorizationCredentials,  # noqa: TC002 - FastAPI resolves annotations
)

from qdash.api.dependencies import get_evaluation_service, get_knowledge_draft_store
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
    EvaluationRunSummary,
    KnowledgeDraftResponse,
    ListEvaluationRunsResponse,
    ListEvaluationsResponse,
    RetryEvaluationRunResponse,
    SetEvaluationVerdictRequest,
)
from qdash.api.schemas.task import TaskKnowledgeResponse, TaskReferenceResponse
from qdash.api.services.evaluation_service import (
    EvaluationService,
)
from qdash.api.services.knowledge_draft_service import (
    MAX_ZIP_BYTES,
    KnowledgeDraft,
    KnowledgeDraftStore,
)
from qdash.api.services.pi_chat_service import QDashAuth
from qdash.api.services.task_service import knowledge_response

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
    drafts: Annotated[KnowledgeDraftStore, Depends(get_knowledge_draft_store)],
) -> CreateEvaluationRunResponse:
    """Queue the latest evaluable result of a task for every entity on a chip.

    The evaluations run in the background as the requesting user; poll the run
    for progress. Entities without an evaluable result are reported as skipped.
    With `knowledge_draft_id` the run reads that uploaded draft instead of the
    task's shared knowledge.
    """
    draft = drafts.get(ctx.project_id, body.knowledge_draft_id) if body.knowledge_draft_id else None
    selection = service.request_run(
        project_id=ctx.project_id,
        chip_id=body.chip_id,
        task=body.task,
        entity_type=body.entity_type,
        date=body.date,
        task_ids=body.task_ids,
        qids=body.qids,
        knowledge_draft=draft,
        trigger=body.trigger,
        mode=body.mode,
        evaluation_model=(
            body.evaluation_model.model_dump() if body.evaluation_model is not None else None
        ),
        with_examples=body.with_examples,
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


@router.post(
    "/evaluations/runs/{run_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Retry unfinished calibration evaluations",
    operation_id="retryEvaluationRun",
    response_model=RetryEvaluationRunResponse,
)
async def retry_evaluation_run(
    run_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
) -> RetryEvaluationRunResponse:
    """Reset failed, interrupted or cancelled items and execute them again."""
    run, retried = service.retry_run(project_id=ctx.project_id, run_id=run_id)
    service.launch(
        run_id, QDashAuth(access_token=credentials.credentials, project_id=ctx.project_id)
    )
    return RetryEvaluationRunResponse(run=run, retried=retried)


@router.post(
    "/evaluations/runs/{run_id}/cancel",
    summary="Cancel a calibration evaluation run",
    operation_id="cancelEvaluationRun",
    response_model=EvaluationRunSummary,
)
async def cancel_evaluation_run(
    run_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
) -> EvaluationRunSummary:
    """Cancel evaluations in this run that have not completed."""
    return service.cancel_run(project_id=ctx.project_id, run_id=run_id)


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
        issues=body.issues,
        username=ctx.user.username,
    )


@router.get(
    "/evaluations/{evaluation_id}/figures/{sha256}",
    summary="Get a snapshotted evaluation figure",
    operation_id="getEvaluationFigure",
    response_class=Response,
)
def get_evaluation_figure(
    evaluation_id: str,
    sha256: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
) -> Response:
    """The exact image bytes supplied to the model for this evaluation."""
    data, media_type = service.evaluation_asset(
        project_id=ctx.project_id, evaluation_id=evaluation_id, sha256=sha256
    )
    return Response(
        content=data,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


def _draft_response(draft: KnowledgeDraft) -> KnowledgeDraftResponse:
    knowledge = draft.knowledge
    return KnowledgeDraftResponse(
        draft_id=draft.draft_id,
        task_name=draft.task_name,
        filename=draft.filename,
        uploaded_by=draft.uploaded_by,
        created_at=draft.created_at,
        warnings=draft.warnings,
        reference=TaskReferenceResponse(**knowledge.reference().model_dump()),
        example_count=len(knowledge.examples),
        figure_count=len(knowledge.figures) + sum(len(e.figures) for e in knowledge.examples),
    )


@router.post(
    "/evaluations/knowledge-drafts",
    summary="Upload a task-knowledge draft to evaluate against",
    operation_id="createKnowledgeDraft",
    response_model=KnowledgeDraftResponse,
    responses={400: {"description": "The zip is not one usable task directory"}},
)
async def create_knowledge_draft(
    file: UploadFile,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    drafts: Annotated[KnowledgeDraftStore, Depends(get_knowledge_draft_store)],
) -> KnowledgeDraftResponse:
    """Store one task's knowledge directory, zipped, as a draft of the project.

    The draft is parsed by the knowledge repository's own generator and is
    read only by the evaluation runs and prompt previews that name it; the
    shared knowledge does not change. Uploading the same zip again returns
    the stored draft.
    """
    data = await file.read(MAX_ZIP_BYTES + 1)
    draft = drafts.create(
        ctx.project_id, data, filename=file.filename or "", uploaded_by=ctx.user.username
    )
    return _draft_response(draft)


@router.get(
    "/evaluations/knowledge-drafts/{draft_id}",
    summary="Get a task-knowledge draft",
    operation_id="getKnowledgeDraft",
    response_model=KnowledgeDraftResponse,
)
def get_knowledge_draft(
    draft_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    drafts: Annotated[KnowledgeDraftStore, Depends(get_knowledge_draft_store)],
) -> KnowledgeDraftResponse:
    """The draft's task, uploader, generator warnings and derived reference."""
    return _draft_response(drafts.get(ctx.project_id, draft_id))


@router.get(
    "/evaluations/knowledge-drafts/{draft_id}/knowledge",
    summary="Get a task-knowledge draft as task knowledge",
    operation_id="getKnowledgeDraftKnowledge",
    response_model=TaskKnowledgeResponse,
)
def get_knowledge_draft_knowledge(
    draft_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    drafts: Annotated[KnowledgeDraftStore, Depends(get_knowledge_draft_store)],
) -> TaskKnowledgeResponse:
    """The draft in the shape of `GET /tasks/{name}/knowledge`, for the Agent Runtime."""
    return knowledge_response(drafts.get(ctx.project_id, draft_id).knowledge)


@router.get(
    "/evaluations/knowledge-drafts/{draft_id}/archive",
    summary="Download the zip a task-knowledge draft was uploaded as",
    operation_id="downloadKnowledgeDraftArchive",
    response_class=FileResponse,
    responses={
        200: {"content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}}}
    },
)
def download_knowledge_draft_archive(
    draft_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    drafts: Annotated[KnowledgeDraftStore, Depends(get_knowledge_draft_store)],
) -> FileResponse:
    """The uploaded zip, byte for byte, so the knowledge a run read can be reused."""
    path, filename = drafts.archive(ctx.project_id, draft_id)
    return FileResponse(path, media_type="application/zip", filename=filename)
