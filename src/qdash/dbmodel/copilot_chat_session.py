"""Document model for per-user copilot chat sessions."""

from datetime import datetime
from typing import Any, ClassVar

from bunnet import Document
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from qdash.common.utils.datetime import now


class CopilotChatMessage(BaseModel):
    """Single message inside a chat session."""

    role: str = Field(..., description='"user" or "assistant"')
    content: str = Field(..., description="Message content (markdown or serialized blocks JSON)")
    attached_image: str | None = Field(
        default=None,
        description="Optional base64 image attached on the user side",
    )
    created_at: datetime = Field(default_factory=now)


class CopilotChatSessionDocument(Document):
    """Persisted CopilotChatPage session owned by a single user."""

    username: str = Field(..., description="Owner username")
    session_id: str = Field(..., description="Client-generated session identifier")
    title: str = Field(default="New Chat", description="Display title")
    context: dict[str, Any] | None = Field(
        default=None,
        description="Optional chat context (e.g. chip_id/qid scope)",
    )
    messages: list[CopilotChatMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)

    model_config = ConfigDict(from_attributes=True)

    class Settings:
        """Mongo metadata."""

        name = "copilot_chat_session"
        indexes: ClassVar = [
            IndexModel(
                [("username", ASCENDING), ("session_id", ASCENDING)],
                unique=True,
                name="username_session_unique_idx",
            ),
            IndexModel(
                [("username", ASCENDING), ("updated_at", DESCENDING)],
                name="username_updated_idx",
            ),
        ]
