"""Schemas for persisted copilot chat sessions."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CopilotChatMessageSchema(BaseModel):
    """One message inside a copilot chat session."""

    role: str = Field(..., description='"user" or "assistant"')
    content: str = Field(..., description="Message content")
    attached_image: str | None = Field(default=None)
    created_at: datetime | None = Field(default=None)


class CopilotChatSessionResponse(BaseModel):
    """Full session payload returned to the client."""

    session_id: str
    title: str
    context: dict[str, Any] | None = None
    messages: list[CopilotChatMessageSchema] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class CopilotChatSessionSummary(BaseModel):
    """Lightweight session entry used in the session list."""

    session_id: str
    title: str
    context: dict[str, Any] | None = None
    message_count: int = 0
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
