"""MongoDB repository for the cool-down wiring event audit log."""

from __future__ import annotations

from bunnet import SortDirection

from qdash.dbmodel.cooldown_wiring_event import CooldownWiringEventDocument
from qdash.dbmodel.user import UserDocument


class MongoCooldownWiringEventRepository:
    """Append + query helpers for CooldownWiringEventDocument."""

    @staticmethod
    def _user_id_for_username(username: str) -> str | None:
        user = UserDocument.find_one({"username": username}).run()
        return user.user_id if user else None

    def append(
        self,
        *,
        project_id: str,
        cooldown_id: str,
        actor: str,
        action: str,
        comment: str,
        wiring_info_snapshot: str,
        block_count: int,
        image_count: int,
        extra: dict[str, str] | None = None,
    ) -> CooldownWiringEventDocument:
        doc = CooldownWiringEventDocument(
            project_id=project_id,
            cooldown_id=cooldown_id,
            actor_user_id=self._user_id_for_username(actor),
            actor=actor,
            action=action,
            comment=comment,
            wiring_info_snapshot=wiring_info_snapshot,
            block_count=block_count,
            image_count=image_count,
            extra=extra or {},
        )
        doc.insert()
        return doc

    def list_by_cooldown(
        self,
        *,
        project_id: str,
        cooldown_id: str,
        limit: int = 100,
        skip: int = 0,
    ) -> list[CooldownWiringEventDocument]:
        return list(
            CooldownWiringEventDocument.find(
                CooldownWiringEventDocument.project_id == project_id,
                CooldownWiringEventDocument.cooldown_id == cooldown_id,
            )
            .sort([("created_at", SortDirection.DESCENDING)])
            .skip(skip)
            .limit(limit)
            .run()
        )
