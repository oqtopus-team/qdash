"""Free-form note attached to a model (qubit, coupling, task result)."""

from datetime import datetime

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


class AiTriageReviewModel(BaseModel):
    """Persistent state for an AI triage review request on a task result."""

    model_config = ConfigDict(protected_namespaces=())

    status: str = Field(
        default="",
        description="AI triage status: requested, running, completed, or failed",
    )
    requested_at: datetime | None = Field(
        default=None,
        description="Timestamp when AI triage was requested",
    )
    requested_by: str = Field(
        default="",
        description="Username that requested AI triage",
    )
    model_provider: str = Field(
        default="",
        description="Provider for the selected AI triage model",
    )
    model_name: str = Field(
        default="",
        description="Name of the selected AI triage model",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="Timestamp when AI triage completed or failed",
    )
    error: str = Field(
        default="",
        description="Failure detail if AI triage failed",
    )
