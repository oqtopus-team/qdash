"""Shared document lookups used when denormalizing identifiers at write time."""

from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.user import UserDocument


def user_id_for_username(username: str | None) -> str | None:
    """Return the user ID for *username*, or None when it is empty or unknown."""
    if not username:
        return None
    user = UserDocument.find_one({"username": username}).run()
    return user.user_id if user else None


def current_cooldown_id(*, project_id: str | None, chip_id: str | None) -> str:
    """Return the chip's current cool-down ID, or an empty string when there is none."""
    if not project_id or not chip_id:
        return ""
    chip = ChipDocument.find_one({"project_id": project_id, "chip_id": chip_id}).run()
    if chip is None:
        return ""
    return chip.current_cooldown_id or ""
