"""Document model for what an agent chat turn was admitted with."""

from datetime import datetime
from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel

from qdash.common.utils.datetime import now


class AgentChatTurnDocument(Document):
    """The project, planner and task of one chat turn, as its first request admitted it.

    Written once, before the turn's request reaches the runtime, and never changed: a
    retry or a reattach of the same turn reads it instead of trusting what its own
    request says, so the evaluations the turn's planner makes are filed under the
    turn's own project, planner model and task, whichever stream reports them.
    """

    username: str = Field(..., description="The user whose chat the turn belongs to")
    session_id: str = Field(..., description="The chat session")
    request_id: str = Field(..., description="The turn's request ID, unique in the session")
    project_id: str = Field(..., description="The project the turn was sent in")
    planner_model: str = Field(..., description="provider/name of the turn's planner model")
    task_id: str | None = Field(
        default=None, description="The task result a task chat's turn is about"
    )
    created_at: datetime = Field(default_factory=now)

    model_config = ConfigDict(from_attributes=True)

    class Settings:
        """Mongo metadata."""

        # Legacy physical collection and index names kept from the Copilot era so
        # existing turn records and their unique index stay in place.
        name = "copilot_chat_turn"
        indexes: ClassVar = [
            IndexModel(
                [("username", ASCENDING), ("session_id", ASCENDING), ("request_id", ASCENDING)],
                unique=True,
                name="copilot_chat_turn_unique_idx",
            ),
        ]
