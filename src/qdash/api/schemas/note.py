"""Schemas for note endpoints (qubit / coupling / task-result)."""

from datetime import datetime

from pydantic import BaseModel, Field

from qdash.datamodel.note import NoteCommentModel, NoteModel


class NoteUpsertRequest(BaseModel):
    """Body for upserting a note."""

    content: str = Field(..., max_length=5000, description="Note text content")


class NoteCommentRequest(BaseModel):
    """Body for creating or updating a note comment."""

    content: str = Field(..., max_length=5000, description="Comment text content")


class TaskNoteEntry(BaseModel):
    """Task-result note row for the dashboard summary."""

    task_id: str
    qid: str
    note: NoteModel
    ai_review_note: NoteModel = Field(
        default_factory=NoteModel,
        description="AI-generated review note for this task result",
    )


class TargetNoteEntry(BaseModel):
    """Per-target row for the dashboard summary (qubit or coupling)."""

    target_id: str
    note: NoteModel = Field(default_factory=NoteModel)
    comments: list[NoteCommentModel] = Field(default_factory=list)
    metric_notes: dict[str, NoteModel] = Field(default_factory=dict)


class ChipNotesSummaryResponse(BaseModel):
    """All notes for a chip in one fetch — drives the dashboard summary view."""

    chip_id: str
    qubits: list[TargetNoteEntry]
    couplings: list[TargetNoteEntry]
    task_notes: list[TaskNoteEntry]


class NoteEventResponse(BaseModel):
    """One row of the note audit log."""

    project_id: str
    chip_id: str
    scope: str = Field(
        ..., description="qubit | qubit_metric | coupling | coupling_metric | task_result"
    )
    target_id: str
    metric_key: str = ""
    action: str = Field(..., description="upsert | delete")
    actor_user_id: str | None = None
    actor: str
    content: str = ""
    extra: dict[str, str] = Field(default_factory=dict)
    created_at: datetime


class ListNoteEventsResponse(BaseModel):
    """Paginated note-event feed."""

    events: list[NoteEventResponse]
    total: int = Field(
        default=0,
        description=(
            "0 if the caller didn't request a count (search/list endpoints "
            "return paginated rows without a separate count by default)."
        ),
    )
