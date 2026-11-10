"""Document model for a user's chosen glyph avatar."""

from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict
from pymongo import ASCENDING, IndexModel

from qdash.datamodel.user_avatar import UserAvatarModel


class UserAvatarDocument(UserAvatarModel, Document):
    """Chosen avatar of one user; see :class:`UserAvatarModel` for the fields."""

    model_config = ConfigDict(from_attributes=True)

    class Settings:
        """Mongo collection metadata."""

        name = "user_avatar"
        indexes: ClassVar = [
            IndexModel(
                [("user_id", ASCENDING)],
                unique=True,
                name="user_avatar_user_id_unique_idx",
            ),
        ]
