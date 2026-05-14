"""Document model for user notifications."""

from datetime import datetime
from typing import ClassVar, Literal

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from qdash.common.utils.datetime import now

NotificationKind = Literal["mention", "issue_reply", "note_mention", "forum_mention", "forum_reply"]
NotificationSourceType = Literal["issue", "note_event", "forum_post"]


class NotificationDocument(Document):
    """In-app notification addressed to a single user."""

    project_id: str = Field(..., description="Owning project identifier")
    recipient_user_id: str | None = Field(default=None, description="Recipient user ID")
    recipient_username: str = Field(..., description="Recipient username snapshot")
    actor_user_id: str | None = Field(default=None, description="Actor user ID")
    actor_username: str = Field(..., description="Actor username snapshot")
    kind: str = Field(..., description="mention | issue_reply | note_mention | forum_*")
    source_type: str = Field(..., description="issue | note_event | forum_post")
    source_id: str = Field(..., description="Source document identifier")
    target_url: str = Field(..., description="Frontend URL to open from the inbox")
    title: str = Field(..., description="Notification title")
    excerpt: str = Field(default="", description="Short body preview")
    dedupe_key: str = Field(..., description="Stable key to prevent duplicate notifications")
    read_at: datetime | None = Field(default=None, description="When the recipient read it")
    created_at: datetime = Field(default_factory=now, description="When this notification was made")

    model_config = ConfigDict(from_attributes=True)

    class Settings:
        """Mongo metadata."""

        name = "notification"
        indexes: ClassVar = [
            IndexModel(
                [
                    ("recipient_user_id", ASCENDING),
                    ("project_id", ASCENDING),
                    ("created_at", DESCENDING),
                ],
                name="recipient_user_id_project_created_idx",
            ),
            IndexModel(
                [
                    ("recipient_user_id", ASCENDING),
                    ("read_at", ASCENDING),
                    ("created_at", DESCENDING),
                ],
                name="recipient_user_id_read_created_idx",
            ),
            IndexModel(
                [
                    ("recipient_username", ASCENDING),
                    ("project_id", ASCENDING),
                    ("created_at", DESCENDING),
                ],
                name="recipient_project_created_idx",
            ),
            IndexModel(
                [
                    ("recipient_username", ASCENDING),
                    ("read_at", ASCENDING),
                    ("created_at", DESCENDING),
                ],
                name="recipient_read_created_idx",
            ),
            IndexModel([("dedupe_key", ASCENDING)], unique=True, name="dedupe_key_unique_idx"),
        ]
