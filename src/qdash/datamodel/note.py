"""Free-form note attached to a model (qubit, coupling, task result)."""

from datetime import datetime

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
