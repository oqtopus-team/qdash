"""Document model for Slack forum thread message tracking."""

from __future__ import annotations

from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel, ReturnDocument

from qdash.datamodel.system_info import SystemInfoModel


class SlackForumThreadDocument(Document):
    """Tracks the Slack message sent for a root forum thread."""

    post_id: str = Field(description="Forum root post ID (string representation of ObjectId)")
    project_id: str = Field(description="Project ID the forum post belongs to")
    channel_id: str = Field(description="Slack channel ID where the message was posted")
    message_ts: str = Field(description="Slack message timestamp (used as thread_ts for replies)")
    system_info: SystemInfoModel = Field(
        default_factory=SystemInfoModel, description="System timestamps"
    )

    class Settings:
        """Mongo collection metadata."""

        name = "slack_forum_thread"
        indexes: ClassVar = [
            IndexModel(
                [("post_id", ASCENDING)], unique=True, name="slack_forum_thread_post_id_unique_idx"
            ),
        ]

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def record(
        cls,
        *,
        post_id: str,
        project_id: str,
        channel_id: str,
        message_ts: str,
    ) -> SlackForumThreadDocument:
        """Upsert a Slack thread record for a forum post."""
        raw = cls.get_motor_collection().find_one_and_update(
            {"post_id": post_id},
            {
                "$set": {
                    "project_id": project_id,
                    "channel_id": channel_id,
                    "message_ts": message_ts,
                },
                "$setOnInsert": {"post_id": post_id},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if raw is None:
            doc = cls(
                post_id=post_id,
                project_id=project_id,
                channel_id=channel_id,
                message_ts=message_ts,
            )
            doc.insert()
            return doc
        validated: SlackForumThreadDocument = cls.model_validate(raw)
        return validated

    @classmethod
    def find_by_post_id(cls, post_id: str) -> SlackForumThreadDocument | None:
        """Find a Slack thread record by forum post ID."""
        return cls.find_one({"post_id": post_id}).run()
