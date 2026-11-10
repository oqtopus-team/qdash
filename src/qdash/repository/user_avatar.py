"""MongoDB access for users' chosen glyph avatars."""

from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from qdash.datamodel.user_avatar import UserAvatarModel
from qdash.dbmodel.user import UserDocument
from qdash.dbmodel.user_avatar import UserAvatarDocument

# Records saved as "automatic" by an earlier version hold no choice; the username decides.
_CUSTOM: dict[str, Any] = {"source": {"$ne": "automatic"}}
# Fields an earlier version stored with the rendered SVG; removed when a record is rewritten.
_OBSOLETE_FIELDS: dict[str, str] = {"svg": "", "etag": "", "options": ""}


class MongoUserAvatarRepository:
    """Store custom avatar settings in the ``user_avatar`` collection, one per user."""

    def find_user_id(self, username: str) -> str | None:
        """Return the internal user ID for ``username``, or ``None`` if no such user."""
        user = UserDocument.find_one({"username": username}).run()
        return user.user_id if user else None

    def find_custom(self, user_id: str) -> UserAvatarModel | None:
        """Return the custom avatar saved for ``user_id``, if one exists."""
        raw = UserAvatarDocument.get_motor_collection().find_one({"user_id": user_id, **_CUSTOM})
        return UserAvatarModel.model_validate(raw) if raw is not None else None

    def find_custom_by_usernames(self, usernames: list[str]) -> list[UserAvatarModel]:
        """Return the custom avatars of the users with the given usernames."""
        if not usernames:
            return []
        users = UserDocument.get_motor_collection().find(
            {"username": {"$in": usernames}}, {"user_id": 1, "username": 1}
        )
        names_by_id = {user["user_id"]: user["username"] for user in users}
        if not names_by_id:
            return []
        raw_avatars = UserAvatarDocument.get_motor_collection().find(
            {"user_id": {"$in": list(names_by_id)}, **_CUSTOM}
        )
        avatars = []
        for raw in raw_avatars:
            # Report the current username; the stored one is only the name at save time.
            raw["username"] = names_by_id[raw["user_id"]]
            avatars.append(UserAvatarModel.model_validate(raw))
        return avatars

    def save(self, avatar: UserAvatarModel) -> UserAvatarModel:
        """Save ``avatar`` as the user's custom avatar, replacing any existing record."""
        fields: dict[str, Any] = avatar.model_dump()
        created_at = fields.pop("created_at")
        collection = UserAvatarDocument.get_motor_collection()
        update = {
            "$set": fields,
            "$setOnInsert": {"created_at": created_at},
            "$unset": _OBSOLETE_FIELDS,
        }
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
        if raw is None:  # pragma: no cover - the record exists after a successful upsert
            msg = f"Avatar record for user {avatar.user_id} was not saved"
            raise RuntimeError(msg)
        return UserAvatarModel.model_validate(raw)

    def delete(self, user_id: str) -> None:
        """Remove the user's avatar record so the automatic avatar applies."""
        UserAvatarDocument.get_motor_collection().delete_one({"user_id": user_id})
