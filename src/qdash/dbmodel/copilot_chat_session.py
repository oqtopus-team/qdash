"""Document model for per-user copilot chat sessions."""

from datetime import datetime
from typing import Any, ClassVar, Literal

from bunnet import Document
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from qdash.common.utils.datetime import now


class CopilotChatSteer(BaseModel):
    """Where a user message sent while an answer was written landed in the conversation."""

    request_id: str = Field(..., description="The steer's request ID, so it is shown once")
    entry_id: str | None = Field(default=None, description="Its entry in the runtime's transcript")
    placement: Literal["exact", "approximate"] = Field(
        default="exact",
        description=(
            "exact: the chat saw where it landed. approximate: it was confirmed after the "
            "answer it interrupted was saved as one message, and follows that message."
        ),
    )


class CopilotChatMessage(BaseModel):
    """Single message inside a chat session."""

    role: str = Field(..., description='"user" or "assistant"')
    content: str = Field(..., description="Message content (markdown or serialized blocks JSON)")
    attached_image: str | None = Field(
        default=None,
        description="Optional base64 image attached on the user side",
    )
    steer: CopilotChatSteer | None = Field(
        default=None, description="Set on a user message sent while an answer was written"
    )
    entry_id: str | None = Field(
        default=None,
        description=(
            "An assistant answer's entry in the runtime's transcript, as the chat stream "
            "reported it; a chat can be branched from such an answer only"
        ),
    )
    created_at: datetime = Field(default_factory=now)


class CopilotChatBranchOrigin(BaseModel):
    """Where a branched chat came from. Set by the server only; a client never writes it."""

    source_session_id: str = Field(..., description="The chat session it was branched from")
    source_entry_id: str = Field(..., description="The answer it was branched at")
    source_conversation_id: str | None = Field(
        default=None, description="The source's conversation in the store; None is the root"
    )
    project_id: str | None = Field(default=None, description="The project it was branched in")
    status: Literal["pending", "ready"] = Field(
        default="ready",
        description=(
            "pending: recorded before the runtime forked it, hidden from the chat list, and "
            "counted as a user of the store until it is ready or removed"
        ),
    )
    operation_id: str | None = Field(
        default=None,
        description=(
            "The branch request that holds a pending branch; only it may finish or remove it"
        ),
    )
    lease_expires_at: datetime | None = Field(
        default=None,
        description=(
            "Until when that request holds the pending branch; after it, a retry or the "
            "cleanup may take it over. None: no request holds it."
        ),
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
    store_session_id: str | None = Field(
        default=None,
        description=(
            "The session whose runtime store (transcript and workspace) this chat uses; "
            "None is its own session_id. Set by the server only."
        ),
    )
    conversation_id: str | None = Field(
        default=None,
        description="The chat's conversation in that store; None is the root. Server only.",
    )
    branch: CopilotChatBranchOrigin | None = Field(
        default=None, description="Set on a chat branched from an answer of another one"
    )
    deleted_at: datetime | None = Field(
        default=None,
        description=(
            "Set when the user deleted the chat: hidden everywhere, kept only while it is the "
            "last user of its store and the runtime has not yet confirmed removing that store, "
            "or while stopping its turn is unconfirmed"
        ),
    )
    stop_pending: bool = Field(
        default=False,
        description=(
            "Set on a deleted chat whose turn the runtime could not be told to stop: the "
            "deleted chat is kept, even while a branch still uses its store, until a retry "
            "confirms that nothing of it runs"
        ),
    )
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
            IndexModel(
                [("username", ASCENDING), ("store_session_id", ASCENDING)],
                name="username_store_session_idx",
            ),
        ]
