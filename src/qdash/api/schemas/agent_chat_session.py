"""Schemas for persisted agent chat sessions."""

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentChatSteerSchema(BaseModel):
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


class AgentChatMessageSchema(BaseModel):
    """One message inside an agent chat session."""

    role: str = Field(..., description='"user" or "assistant"')
    content: str = Field(..., description="Message content")
    attached_image: str | None = Field(default=None)
    steer: AgentChatSteerSchema | None = Field(
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


class AgentChatBranchSchema(BaseModel):
    """Where a branched chat came from."""

    source_session_id: str = Field(..., description="The chat session it was branched from")
    source_entry_id: str = Field(..., description="The answer it was branched at")


class AgentChatTurnSchema(BaseModel):
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


class AgentChatSessionResponse(BaseModel):
    """Full session payload returned to the client."""

    session_id: str
    title: str
    context: dict[str, Any] | None = None
    messages: list[AgentChatMessageSchema] = Field(default_factory=list)
    branch: AgentChatBranchSchema | None = None
    turn: AgentChatTurnSchema | None = Field(
        default=None, description="The latest turn the server records for the chat"
    )
    created_at: datetime
    updated_at: datetime


class AgentChatSessionSummary(BaseModel):
    """Lightweight session entry used in the session list."""

    session_id: str
    title: str
    context: dict[str, Any] | None = None
    message_count: int = 0
    branch: AgentChatBranchSchema | None = None
    created_at: datetime
    updated_at: datetime


class ListAgentChatSessionsResponse(BaseModel):
    """Response for GET /agent/chat/sessions."""

    sessions: list[AgentChatSessionSummary]


class CreateAgentChatSessionRequest(BaseModel):
    """Body for POST /agent/chat/sessions."""

    session_id: str = Field(..., description="Client-generated session identifier")
    title: str = Field(default="New Chat")
    context: dict[str, Any] | None = None
    messages: list[AgentChatMessageSchema] = Field(default_factory=list)


class UpdateAgentChatSessionRequest(BaseModel):
    """Body for PATCH /agent/chat/sessions/{session_id}."""

    title: str | None = None
    context: dict[str, Any] | None = None
    messages: list[AgentChatMessageSchema] | None = None


class CreateAgentChatBranchRequest(BaseModel):
    """Body for POST /agent/chat/sessions/{session_id}/branches."""

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


# ---------------------------------------------------------------------------
# Read-only snapshots shared with a project
# ---------------------------------------------------------------------------


class AgentChatShareBlockType(str, Enum):
    """The kind of one piece of a shared answer.

    A named enum, so generated clients give it its own name instead of a generic
    ``Type`` that would take that name from another schema's enum.
    """

    TEXT = "text"
    CHART = "chart"
    UI = "ui"


class AgentChatShareBlockSchema(BaseModel):
    """One user-facing piece of a shared answer."""

    type: AgentChatShareBlockType
    content: str | None = Field(
        default=None, description="Markdown for text; the plain-text fallback for ui"
    )
    chart: dict[str, Any] | None = Field(default=None, description="Plotly data and layout")
    ui: dict[str, Any] | None = Field(default=None, description="A read-only composed UI spec")


class AgentChatShareMessageSchema(BaseModel):
    """One message of a shared snapshot, without tool steps or runtime identifiers."""

    role: Literal["user", "assistant"]
    blocks: list[AgentChatShareBlockSchema] = Field(default_factory=list)
    is_error: bool = Field(default=False, description="The answer ended with an error")
    figures_attached: bool = Field(
        default=False,
        description="The user message went out with figures; the snapshot does not keep them",
    )
    incomplete: Literal["stopped", "interrupted"] | None = Field(
        default=None, description="The answer did not end normally"
    )
    omitted_content: bool = Field(
        default=False,
        description="Tool steps, figures or interactive cards of the answer were left out",
    )
    created_at: datetime | None = None


class AgentChatShareSummary(BaseModel):
    """A chat's snapshot shared with the current project, as its owner manages it."""

    share_id: str
    project_id: str
    title: str
    message_count: int
    created_at: datetime = Field(..., description="When the chat was first shared")
    snapshot_at: datetime = Field(..., description="When the snapshot was last copied")


class AgentChatShareStatusResponse(BaseModel):
    """Whether one of the caller's chats is shared with the current project."""

    share: AgentChatShareSummary | None = None


class AgentChatShareResponse(BaseModel):
    """A shared snapshot as a project member reads it."""

    share_id: str
    project_id: str
    title: str
    owner_username: str
    messages: list[AgentChatShareMessageSchema]
    created_at: datetime = Field(..., description="When the chat was first shared")
    snapshot_at: datetime = Field(..., description="When the snapshot was last copied")
    is_owner: bool = Field(..., description="The caller owns the chat and may update the snapshot")
    can_revoke: bool = Field(
        ..., description="The caller may stop sharing: the chat's owner or a project owner"
    )
