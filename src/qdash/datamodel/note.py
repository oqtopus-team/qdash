"""Free-form note attached to a model (qubit, coupling, task result)."""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class NoteModel(BaseModel):
    """A free-form note with author and timestamp metadata.

    ``updated_at`` is ``None`` until someone first writes content. This makes it
    possible to distinguish "never noted" from "noted then cleared".
    """

    content: str = Field(default="", description="Free-form note text")
    updated_by: str = Field(default="", description="Username of the last editor")
    updated_at: datetime | None = Field(
        default=None, description="Timestamp of the last edit; None if never edited"
    )


class NoteCommentModel(BaseModel):
    """One user-authored comment on a target summary note."""

    comment_id: str = Field(
        default_factory=lambda: uuid4().hex,
        description="Stable comment identifier",
    )
    content: str = Field(default="", description="Free-form comment text")
    created_by: str = Field(default="", description="Username of the original author")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Creation timestamp"
    )
    updated_by: str = Field(default="", description="Username of the last editor")
    updated_at: datetime | None = Field(
        default=None, description="Timestamp of the last edit; None until edited"
    )


class AiReviewModel(BaseModel):
    """Persistent state for an AI review run on a task result."""

    model_config = ConfigDict(protected_namespaces=())

    status: str = Field(
        default="",
        description="AI review status: requested, running, completed, or failed",
    )
    requested_at: datetime | None = Field(
        default=None,
        description="Timestamp when AI review was requested",
    )
    requested_by: str = Field(
        default="",
        description="Username that requested AI review",
    )
    review_run_id: str = Field(
        default="",
        description="AI review run identifier shared by task results in the same run",
    )
    trigger_type: str = Field(
        default="manual_chip_bulk",
        description="How this AI review run was triggered, such as manual_chip_bulk or execution",
    )
    model_provider: str = Field(
        default="",
        description="Provider for the selected AI review model",
    )
    model_name: str = Field(
        default="",
        description="Name of the selected AI review model",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="Timestamp when AI review completed or failed",
    )
    error: str = Field(
        default="",
        description="Failure detail if AI review failed",
    )
