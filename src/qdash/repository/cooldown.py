"""MongoDB repository for CooldownDocument."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bunnet import SortDirection
from qdash.dbmodel.cooldown import CooldownDocument

if TYPE_CHECKING:
    from datetime import datetime


class MongoCooldownRepository:
    """CRUD + lookup helpers for CooldownDocument."""

    def list_all(
        self,
        *,
        project_id: str,
        cryo_id: str | None = None,
        chip_id: str | None = None,
    ) -> list[CooldownDocument]:
        query: dict[str, object] = {"project_id": project_id}
        if cryo_id:
            query["cryo_id"] = cryo_id
        if chip_id:
            query["chip_ids"] = chip_id
        return list(
            CooldownDocument.find(query).sort([("started_at", SortDirection.DESCENDING)]).run()
        )

    def get(self, *, project_id: str, cooldown_id: str) -> CooldownDocument | None:
        return CooldownDocument.find_one(
            CooldownDocument.project_id == project_id,
            CooldownDocument.cooldown_id == cooldown_id,
        ).run()

    def find_active_for_chip(self, *, project_id: str, chip_id: str) -> CooldownDocument | None:
        """Return the chip's currently-active cool-down (ended_at is None)."""
        return CooldownDocument.find_one(
            {
                "project_id": project_id,
                "chip_ids": chip_id,
                "ended_at": None,
            }
        ).run()

    def find_for_timestamp(
        self, *, project_id: str, chip_id: str, when: datetime
    ) -> CooldownDocument | None:
        """Find which cool-down the chip was in at the given timestamp."""
        return CooldownDocument.find_one(
            {
                "project_id": project_id,
                "chip_ids": chip_id,
                "started_at": {"$lte": when},
                "$or": [{"ended_at": None}, {"ended_at": {"$gte": when}}],
            }
        ).run()

    def insert(self, doc: CooldownDocument) -> CooldownDocument:
        doc.insert()
        return doc

    def save(self, doc: CooldownDocument) -> CooldownDocument:
        doc.system_info.update_time()
        doc.save()
        return doc

    def delete(self, *, project_id: str, cooldown_id: str) -> bool:
        existing = self.get(project_id=project_id, cooldown_id=cooldown_id)
        if existing is None:
            return False
        existing.delete()
        return True
