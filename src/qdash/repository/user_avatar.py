"""MongoDB access for generated user avatars."""

from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from qdash.datamodel.user_avatar import UserAvatarModel
from qdash.dbmodel.user import UserDocument
from qdash.dbmodel.user_avatar import UserAvatarDocument


def _fields(avatar: UserAvatarModel) -> dict[str, Any]:
    fields: dict[str, Any] = avatar.model_dump()
    return fields


class MongoUserAvatarRepository:
    """Store generated avatars in the ``user_avatar`` collection, one per user."""

    def find_user_id(self, username: str) -> str | None:
        """Return the internal user ID for ``username``, or ``None`` if no such user."""
        user = UserDocument.find_one({"username": username}).run()
        return user.user_id if user else None

    def find_avatar(self, user_id: str) -> UserAvatarModel | None:
        """Return the saved avatar for ``user_id``, if one exists."""
        raw = UserAvatarDocument.get_motor_collection().find_one({"user_id": user_id})
        return UserAvatarModel.model_validate(raw) if raw is not None else None

    def insert_if_absent(self, avatar: UserAvatarModel) -> UserAvatarModel:
        """Save ``avatar`` unless the user already has one, and return the stored record.

        The first writer wins: a concurrent request that generated the same avatar, or a custom
        avatar saved in the meantime, is returned unchanged and never overwritten.
        """
        collection = UserAvatarDocument.get_motor_collection()
        try:
            raw = collection.find_one_and_update(
                {"user_id": avatar.user_id},
                {"$setOnInsert": _fields(avatar)},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            # Two upserts raced on the unique index; the other one saved the record.
            raw = collection.find_one({"user_id": avatar.user_id})
        return self._validated(raw, avatar.user_id)

    def replace(self, avatar: UserAvatarModel) -> UserAvatarModel:
        """Save ``avatar`` as the user's avatar, replacing any existing record."""
        fields = _fields(avatar)
        created_at = fields.pop("created_at")
        collection = UserAvatarDocument.get_motor_collection()
        update = {"$set": fields, "$setOnInsert": {"created_at": created_at}}
        try:
            raw = collection.find_one_and_update(
                {"user_id": avatar.user_id},
                update,
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            # A concurrent first insert won the upsert; the record now exists, so update it.
            raw = collection.find_one_and_update(
                {"user_id": avatar.user_id},
                update,
                return_document=ReturnDocument.AFTER,
            )
        return self._validated(raw, avatar.user_id)

    @staticmethod
    def _validated(raw: Any, user_id: str) -> UserAvatarModel:
        if raw is None:  # pragma: no cover - the record exists after a successful upsert
            msg = f"Avatar record for user {user_id} was not saved"
            raise RuntimeError(msg)
        return UserAvatarModel.model_validate(raw)
