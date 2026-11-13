"""Free-form note attached to a model (qubit, coupling, task result)."""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field


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
