"""Schemas for persisted copilot chat sessions."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class CopilotChatSteerSchema(BaseModel):
    """Where a user message sent while an answer was written landed in the conversation."""

    request_id: str = Field(..., min_length=1, max_length=200)
    entry_id: str | None = Field(default=None, max_length=64)
    placement: Literal["exact", "approximate"] = Field(
        default="exact",
        description=(
            "exact: the chat saw where it landed. approximate: it was confirmed after the "
            "answer it interrupted was saved as one message, and follows that message."
        ),
    )


class CopilotChatMessageSchema(BaseModel):
    """One message inside a copilot chat session."""

    role: str = Field(..., description='"user" or "assistant"')
    content: str = Field(..., description="Message content")
    attached_image: str | None = Field(default=None)
    steer: CopilotChatSteerSchema | None = Field(
        default=None, description="Set on a user message sent while an answer was written"
    )
    entry_id: str | None = Field(
        default=None,
        pattern=r"^[0-9]{1,15}$",
        description=(
            "An assistant answer's entry in the runtime's transcript, from the chat stream's "
            "result; the chat can be branched from that answer"
        ),
    )
    turn_request_id: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "The chat turn this message belongs to. The server records the latest turn's "
            "messages itself; a save cannot replace them."
        ),
    )
    created_at: datetime | None = Field(default=None)


class CopilotChatBranchSchema(BaseModel):
    """Where a branched chat came from."""

    source_session_id: str = Field(..., description="The chat session it was branched from")
    source_entry_id: str = Field(..., description="The answer it was branched at")


class CopilotChatTurnSchema(BaseModel):
    """The latest turn the server records for a chat, as a reloaded page needs it.

    A page that reattaches to a turn, or follows one another window started, finds
    the turn's messages by ``request_id`` (each carries it as ``turn_request_id``)
    and uses ``status`` to tell a running turn from one whose end is saved.
    """

    request_id: str = Field(..., description="The turn's request ID")
    project_id: str | None = Field(default=None, description="The project it was sent from")
    status: Literal["running", "completed", "failed", "stopped", "noop"] = Field(
        ..., description="Whether the turn still runs, or how it ended"
    )
    start_index: int = Field(..., description="How many messages precede the turn")
    continuing: bool = Field(default=False, description="A continue: no user message")
    started_at: datetime | None = Field(default=None)


class CopilotChatSessionResponse(BaseModel):
    """Full session payload returned to the client."""

    session_id: str
    title: str
    context: dict[str, Any] | None = None
    messages: list[CopilotChatMessageSchema] = Field(default_factory=list)
    branch: CopilotChatBranchSchema | None = None
    turn: CopilotChatTurnSchema | None = Field(
        default=None, description="The latest turn the server records for the chat"
    )
    created_at: datetime
    updated_at: datetime


class CopilotChatSessionSummary(BaseModel):
    """Lightweight session entry used in the session list."""

    session_id: str
    title: str
    context: dict[str, Any] | None = None
    message_count: int = 0
    branch: CopilotChatBranchSchema | None = None
    created_at: datetime
    updated_at: datetime


class ListCopilotChatSessionsResponse(BaseModel):
    """Response for GET /copilot/chat/sessions."""

    sessions: list[CopilotChatSessionSummary]


class CreateCopilotChatSessionRequest(BaseModel):
    """Body for POST /copilot/chat/sessions."""

    session_id: str = Field(..., description="Client-generated session identifier")
    title: str = Field(default="New Chat")
    context: dict[str, Any] | None = None
    messages: list[CopilotChatMessageSchema] = Field(default_factory=list)


class UpdateCopilotChatSessionRequest(BaseModel):
    """Body for PATCH /copilot/chat/sessions/{session_id}."""

    title: str | None = None
    context: dict[str, Any] | None = None
    messages: list[CopilotChatMessageSchema] | None = None


class CreateCopilotChatBranchRequest(BaseModel):
    """Body for POST /copilot/chat/sessions/{session_id}/branches."""

    entry_id: str = Field(
        ...,
        pattern=r"^[0-9]{1,15}$",
        description="The saved answer to branch at: its runtime entry ID",
    )
    target_session_id: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description=(
            "Client-generated ID of the new chat session; sending the same request again "
            "returns the same branch"
        ),
    )
