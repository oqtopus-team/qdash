"""Schemas for a user's own Copilot preferences."""

from __future__ import annotations

from pydantic import BaseModel, Field

MAX_INSTRUCTIONS_CHARS = 2000


class CopilotPreferences(BaseModel):
    """The current user's Copilot preferences."""

    instructions: str = Field(
        default="",
        max_length=MAX_INSTRUCTIONS_CHARS,
        description=(
            "Instructions added to every chat of this user (style, language, formats). "
            "They apply to chat only, not to evaluations or forum replies, and cannot "
            "override the approval of write operations."
        ),
    )
    max_instructions_chars: int = Field(
        default=MAX_INSTRUCTIONS_CHARS, description="Longest instructions accepted"
    )


class CopilotPreferencesUpdate(BaseModel):
    """Replace the current user's Copilot instructions; empty clears them."""

    instructions: str = Field(default="", max_length=MAX_INSTRUCTIONS_CHARS)


class CopilotSystemPrompt(BaseModel):
    """What QDash tells the chat model, read-only: its system prompt and this user's part."""

    system_prompt: str = Field(
        description="QDash's system prompt for chats, set by the application"
    )
    user_preferences: str | None = Field(
        default=None,
        description="This user's instructions as they are appended to it, or None when unset",
    )
    tools: list[str] = Field(
        default_factory=list,
        description="Tools offered to the chat; their descriptions are sent with each request",
    )
