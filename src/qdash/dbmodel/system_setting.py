"""Document model for singleton system settings."""

from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel, ReturnDocument

from qdash.datamodel.system_info import SystemInfoModel

SYSTEM_SETTING_KEY = "global"


class SystemSettingDocument(Document):
    """Singleton document for system-wide runtime settings."""

    key: str = Field(default=SYSTEM_SETTING_KEY, description="Singleton document key")
    slack_forum_notifications_enabled: bool = Field(
        default=False,
        description="Whether forum thread creation sends Slack webhook notifications",
    )
    system_info: SystemInfoModel = Field(
        default_factory=SystemInfoModel, description="System timestamps"
    )

    class Settings:
        """Mongo collection metadata."""

        name = "system_setting"
        indexes: ClassVar = [
            IndexModel([("key", ASCENDING)], unique=True, name="system_setting_key_unique_idx"),
        ]

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def get_singleton(cls) -> "SystemSettingDocument":
        """Return the singleton document, creating it with defaults when missing."""
        existing = cls.find_one({"key": SYSTEM_SETTING_KEY}).run()
        if existing is not None:
            return existing
        doc = cls(key=SYSTEM_SETTING_KEY)
        doc.insert()
        return doc

    @classmethod
    def set_slack_forum_notifications_enabled(cls, enabled: bool) -> "SystemSettingDocument":
        """Update Slack forum notification state and return the singleton."""
        raw = cls.get_motor_collection().find_one_and_update(
            {"key": SYSTEM_SETTING_KEY},
            {
                "$set": {"slack_forum_notifications_enabled": enabled},
                "$setOnInsert": {"key": SYSTEM_SETTING_KEY},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if raw is None:
            return cls.get_singleton()
        return cls.model_validate(raw)
