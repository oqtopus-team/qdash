from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class SlackEvent(BaseModel):
    """Slack event model."""

    type: str
    text: str
    user: str
    ts: str
    channel: str
    event_ts: str
    thread_ts: str | None = None

    @property
    def clean_text(self) -> str:
        """Text without mentions."""
        import re

        # Remove <@USER_ID> format mentions
        return re.sub(r"<@\w+>", "", self.text).strip()


class SlackMessage(BaseModel):
    """Slack message model."""

    text: str
    thread_ts: str | None = None
    channel: str | None = None


class ConversationTurn(BaseModel):
    """Conversation turn."""

    role: str = Field(..., pattern="^(system|user|assistant|tool)$")
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None


class AgentContext(BaseModel):
    """Agent context."""

    user_id: str
    channel_id: str
    thread_ts: str
    original_message: str
    start_time: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))

    @property
    def elapsed_time(self) -> float:
        """Elapsed time in seconds."""
        return (datetime.now(tz=timezone.utc) - self.start_time).total_seconds()
