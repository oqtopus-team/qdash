"""Document model for read-only snapshots of agent chats shared with a project."""

from datetime import datetime
from typing import Any, ClassVar, Literal
from uuid import uuid4

from bunnet import Document
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from qdash.common.utils.datetime import now


def new_share_id() -> str:
    """An unguessable share identifier; reading a share still requires project membership."""
    return f"chatshare_{uuid4().hex}"


class AgentChatShareBlock(BaseModel):
    """One user-facing piece of a shared answer: Markdown text, a chart, or a composed UI."""

    type: Literal["text", "chart", "ui"]
    content: str | None = Field(
        default=None, description="Markdown for text; the plain-text fallback for ui"
    )
    chart: dict[str, Any] | None = Field(default=None, description="Plotly data and layout")
    ui: dict[str, Any] | None = Field(default=None, description="A read-only composed UI spec")


class AgentChatShareMessage(BaseModel):
    """One message of a snapshot, reduced to what the conversation showed its reader."""

    role: Literal["user", "assistant"]
    blocks: list[AgentChatShareBlock] = Field(default_factory=list)
    is_error: bool = Field(default=False, description="The answer ended with an error")
    figures_attached: bool = Field(
        default=False, description="The user message went out with figures; they are not kept"
    )
    incomplete: Literal["stopped", "interrupted"] | None = Field(
        default=None, description="The answer did not end normally"
    )
    omitted_content: bool = Field(
        default=False,
        description="Tool steps, figures or interactive cards of the answer were left out",
    )
    created_at: datetime | None = None


class AgentChatShareDocument(Document):
    """A project-scoped, read-only snapshot of one user's chat.

    The snapshot is copied from the chat when its owner shares or updates it and never
    follows the chat on its own. It holds no runtime store, conversation, entry or turn
    identifiers, so reading it opens nothing of the owner's runtime workspace.
    """

    share_id: str = Field(default_factory=new_share_id, description="Share identifier")
    project_id: str = Field(..., description="The project whose members may read it")
    owner_username: str = Field(..., description="The chat's owner")
    owner_user_id: str | None = Field(default=None, description="The chat owner's user ID")
    source_session_id: str = Field(
        ..., description="The owner's chat the snapshot was copied from; never returned"
    )
    title: str = Field(default="New Chat", description="Chat title when the snapshot was taken")
    messages: list[AgentChatShareMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=now, description="When it was first shared")
    snapshot_at: datetime = Field(default_factory=now, description="When it was last copied")

    model_config = ConfigDict(from_attributes=True)

    class Settings:
        """Mongo metadata."""

        name = "agent_chat_share"
        indexes: ClassVar = [
            IndexModel([("share_id", ASCENDING)], unique=True, name="share_id_unique_idx"),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("owner_username", ASCENDING),
                    ("source_session_id", ASCENDING),
                ],
                unique=True,
                name="project_owner_session_unique_idx",
            ),
            IndexModel(
                [("owner_username", ASCENDING), ("source_session_id", ASCENDING)],
                name="owner_session_idx",
            ),
            IndexModel(
                [("project_id", ASCENDING), ("snapshot_at", DESCENDING)],
                name="project_snapshot_idx",
            ),
        ]
