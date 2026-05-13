"""Unified note router (qubit / coupling / task-result)."""

from __future__ import annotations

import logging
from datetime import datetime  # noqa: TCH003
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from qdash.api.dependencies import get_note_service  # noqa: TCH002
from qdash.api.lib.project import (  # noqa: TCH002
    ProjectContext,
    get_project_context,
    get_project_context_editor,
)
from qdash.api.schemas.note import (
    ChipNotesSummaryResponse,
    ListNoteEventsResponse,
    NoteUpsertRequest,
)
from qdash.api.schemas.success import SuccessResponse
from qdash.api.services.note_service import NoteService  # noqa: TCH002
from qdash.datamodel.note import NoteModel

router = APIRouter()
logger = logging.getLogger(__name__)


# =============================================================================
# Qubit notes
# =============================================================================


@router.put(
    "/chips/{chip_id}/qubits/{qid}/note",
    summary="Upsert the general note for a qubit",
    operation_id="upsertQubitNote",
    response_model=NoteModel,
)
def upsert_qubit_note(
    chip_id: str,
    qid: str,
    body: NoteUpsertRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[NoteService, Depends(get_note_service)],
) -> NoteModel:
    return service.upsert_qubit_note(
        project_id=ctx.project_id,
        chip_id=chip_id,
        qid=qid,
        content=body.content,
        username=ctx.user.username,
    )


@router.delete(
    "/chips/{chip_id}/qubits/{qid}/note",
    summary="Clear the general note for a qubit",
    operation_id="deleteQubitNote",
    response_model=SuccessResponse,
)
def delete_qubit_note(
    chip_id: str,
    qid: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[NoteService, Depends(get_note_service)],
) -> SuccessResponse:
    return service.delete_qubit_note(
        project_id=ctx.project_id,
        chip_id=chip_id,
        qid=qid,
        username=ctx.user.username,
    )


@router.put(
    "/chips/{chip_id}/qubits/{qid}/metric-notes/{metric_key}",
    summary="Upsert a per-metric note for a qubit",
    operation_id="upsertQubitMetricNote",
    response_model=NoteModel,
)
def upsert_qubit_metric_note(
    chip_id: str,
    qid: str,
    metric_key: str,
    body: NoteUpsertRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[NoteService, Depends(get_note_service)],
    cooldown_id: Annotated[
        str | None,
        Query(description="Optional explicit cool-down scope identifier"),
    ] = None,
    start_at: Annotated[
        datetime | None,
        Query(description="Optional time-range scope start"),
    ] = None,
    end_at: Annotated[
        datetime | None,
        Query(description="Optional time-range scope end"),
    ] = None,
) -> NoteModel:
    return service.upsert_qubit_metric_note(
        project_id=ctx.project_id,
        chip_id=chip_id,
        qid=qid,
        metric_key=metric_key,
        content=body.content,
        username=ctx.user.username,
        cooldown_id=cooldown_id,
        start_at=start_at,
        end_at=end_at,
    )


@router.delete(
    "/chips/{chip_id}/qubits/{qid}/metric-notes/{metric_key}",
    summary="Delete a per-metric note for a qubit",
    operation_id="deleteQubitMetricNote",
    response_model=SuccessResponse,
)
def delete_qubit_metric_note(
    chip_id: str,
    qid: str,
    metric_key: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[NoteService, Depends(get_note_service)],
    cooldown_id: Annotated[
        str | None,
        Query(description="Optional explicit cool-down scope identifier"),
    ] = None,
    start_at: Annotated[
        datetime | None,
        Query(description="Optional time-range scope start"),
    ] = None,
    end_at: Annotated[
        datetime | None,
        Query(description="Optional time-range scope end"),
    ] = None,
) -> SuccessResponse:
    return service.delete_qubit_metric_note(
        project_id=ctx.project_id,
        chip_id=chip_id,
        qid=qid,
        metric_key=metric_key,
        username=ctx.user.username,
        cooldown_id=cooldown_id,
        start_at=start_at,
        end_at=end_at,
    )


# =============================================================================
# Coupling notes
# =============================================================================


@router.put(
    "/chips/{chip_id}/couplings/{coupling_id}/note",
    summary="Upsert the general note for a coupling",
    operation_id="upsertCouplingNote",
    response_model=NoteModel,
)
def upsert_coupling_note(
    chip_id: str,
    coupling_id: str,
    body: NoteUpsertRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[NoteService, Depends(get_note_service)],
) -> NoteModel:
    return service.upsert_coupling_note(
        project_id=ctx.project_id,
        chip_id=chip_id,
        coupling_id=coupling_id,
        content=body.content,
        username=ctx.user.username,
    )


@router.delete(
    "/chips/{chip_id}/couplings/{coupling_id}/note",
    summary="Clear the general note for a coupling",
    operation_id="deleteCouplingNote",
    response_model=SuccessResponse,
)
def delete_coupling_note(
    chip_id: str,
    coupling_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[NoteService, Depends(get_note_service)],
) -> SuccessResponse:
    return service.delete_coupling_note(
        project_id=ctx.project_id,
        chip_id=chip_id,
        coupling_id=coupling_id,
        username=ctx.user.username,
    )


@router.put(
    "/chips/{chip_id}/couplings/{coupling_id}/metric-notes/{metric_key}",
    summary="Upsert a per-metric note for a coupling",
    operation_id="upsertCouplingMetricNote",
    response_model=NoteModel,
)
def upsert_coupling_metric_note(
    chip_id: str,
    coupling_id: str,
    metric_key: str,
    body: NoteUpsertRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[NoteService, Depends(get_note_service)],
    cooldown_id: Annotated[
        str | None,
        Query(description="Optional explicit cool-down scope identifier"),
    ] = None,
    start_at: Annotated[
        datetime | None,
        Query(description="Optional time-range scope start"),
    ] = None,
    end_at: Annotated[
        datetime | None,
        Query(description="Optional time-range scope end"),
    ] = None,
) -> NoteModel:
    return service.upsert_coupling_metric_note(
        project_id=ctx.project_id,
        chip_id=chip_id,
        coupling_id=coupling_id,
        metric_key=metric_key,
        content=body.content,
        username=ctx.user.username,
        cooldown_id=cooldown_id,
        start_at=start_at,
        end_at=end_at,
    )


@router.delete(
    "/chips/{chip_id}/couplings/{coupling_id}/metric-notes/{metric_key}",
    summary="Delete a per-metric note for a coupling",
    operation_id="deleteCouplingMetricNote",
    response_model=SuccessResponse,
)
def delete_coupling_metric_note(
    chip_id: str,
    coupling_id: str,
    metric_key: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[NoteService, Depends(get_note_service)],
    cooldown_id: Annotated[
        str | None,
        Query(description="Optional explicit cool-down scope identifier"),
    ] = None,
    start_at: Annotated[
        datetime | None,
        Query(description="Optional time-range scope start"),
    ] = None,
    end_at: Annotated[
        datetime | None,
        Query(description="Optional time-range scope end"),
    ] = None,
) -> SuccessResponse:
    return service.delete_coupling_metric_note(
        project_id=ctx.project_id,
        chip_id=chip_id,
        coupling_id=coupling_id,
        metric_key=metric_key,
        username=ctx.user.username,
        cooldown_id=cooldown_id,
        start_at=start_at,
        end_at=end_at,
    )


# =============================================================================
# Task-result notes
# =============================================================================


@router.get(
    "/task-results/{task_id}/note",
    summary="Get the user note for a task result",
    operation_id="getTaskNote",
    response_model=NoteModel,
)
def get_task_note(
    task_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[NoteService, Depends(get_note_service)],
) -> NoteModel:
    note = service.get_task_note(project_id=ctx.project_id, task_id=task_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Task note not set")
    return note


@router.put(
    "/task-results/{task_id}/note",
    summary="Upsert the user note for a task result",
    operation_id="upsertTaskNote",
    response_model=NoteModel,
)
def upsert_task_note(
    task_id: str,
    body: NoteUpsertRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[NoteService, Depends(get_note_service)],
) -> NoteModel:
    return service.upsert_task_note(
        project_id=ctx.project_id,
        task_id=task_id,
        content=body.content,
        username=ctx.user.username,
    )


@router.delete(
    "/task-results/{task_id}/note",
    summary="Clear the user note for a task result",
    operation_id="deleteTaskNote",
    response_model=SuccessResponse,
)
def delete_task_note(
    task_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[NoteService, Depends(get_note_service)],
) -> SuccessResponse:
    return service.delete_task_note(
        project_id=ctx.project_id,
        task_id=task_id,
        username=ctx.user.username,
    )


# =============================================================================
# Chip-wide notes summary (for dashboard)
# =============================================================================


@router.get(
    "/chips/{chip_id}/notes-summary",
    summary="List all notes (qubit / coupling / task-result) on a chip",
    operation_id="getChipNotesSummary",
    response_model=ChipNotesSummaryResponse,
)
def get_chip_notes_summary(
    chip_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[NoteService, Depends(get_note_service)],
    cooldown_id: Annotated[
        str | None,
        Query(description="Optional explicit cool-down scope identifier"),
    ] = None,
    start_at: Annotated[
        datetime | None,
        Query(description="Optional time-range scope start"),
    ] = None,
    end_at: Annotated[
        datetime | None,
        Query(description="Optional time-range scope end"),
    ] = None,
) -> ChipNotesSummaryResponse:
    return service.chip_notes_summary(
        project_id=ctx.project_id,
        chip_id=chip_id,
        cooldown_id=cooldown_id,
        start_at=start_at,
        end_at=end_at,
    )


# =============================================================================
# Note event feed (audit log + knowledge view)
# =============================================================================


@router.get(
    "/chips/{chip_id}/note-events",
    summary="Chip-scoped note edit timeline",
    operation_id="listChipNoteEvents",
    response_model=ListNoteEventsResponse,
)
def list_chip_note_events(
    chip_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[NoteService, Depends(get_note_service)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ListNoteEventsResponse:
    return service.list_chip_events(
        project_id=ctx.project_id, chip_id=chip_id, skip=skip, limit=limit
    )


@router.get(
    "/note-events/by-target",
    summary="Per-target note edit timeline",
    operation_id="listTargetNoteEvents",
    response_model=ListNoteEventsResponse,
)
def list_target_note_events(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[NoteService, Depends(get_note_service)],
    scope: Annotated[
        str,
        Query(
            pattern="^(qubit|qubit_metric|coupling|coupling_metric|task_result)$",
            description="Note scope",
        ),
    ],
    target_id: Annotated[str, Query(description="qid / coupling_id / task_id")],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ListNoteEventsResponse:
    return service.list_target_events(
        project_id=ctx.project_id,
        scope=scope,
        target_id=target_id,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/note-events/search",
    summary="Full-text search across note contents",
    operation_id="searchNoteEvents",
    response_model=ListNoteEventsResponse,
)
def search_note_events(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[NoteService, Depends(get_note_service)],
    q: Annotated[str, Query(min_length=1, description="Free-text search query")],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ListNoteEventsResponse:
    return service.search_events(project_id=ctx.project_id, query=q, skip=skip, limit=limit)
