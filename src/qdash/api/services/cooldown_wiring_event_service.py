"""Service for the cool-down wiring change history (checkpoints).

Takes a snapshot of a cool-down's current wiring whenever the user records a
checkpoint. Kept independent from ``CooldownService`` so the feature can be
lifted out (e.g. into a dedicated ``cryowire`` package) without affecting
cool-down core CRUD.

The only legitimate cross-feature seam is reading the cool-down's *current*
wiring at checkpoint time. That read is encapsulated in
:meth:`_load_cooldown_for_snapshot` so a future abstraction (e.g. a
``WiringSource`` interface taking any target) has a single place to slot in.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from starlette.exceptions import HTTPException

from qdash.api.schemas.cooldown_wiring_event import (
    CooldownWiringEventResponse,
    ListCooldownWiringEventsResponse,
)

if TYPE_CHECKING:
    from qdash.dbmodel.cooldown import CooldownDocument
    from qdash.dbmodel.cooldown_wiring_event import CooldownWiringEventDocument
    from qdash.repository.cooldown import MongoCooldownRepository
    from qdash.repository.cooldown_wiring_event import MongoCooldownWiringEventRepository


class CooldownWiringEventService:
    """Append + read wiring checkpoints scoped to one cool-down."""

    def __init__(
        self,
        cooldown_repository: MongoCooldownRepository,
        wiring_event_repository: MongoCooldownWiringEventRepository,
    ) -> None:
        self._cooldowns = cooldown_repository
        self._events = wiring_event_repository

    def create_checkpoint(
        self,
        *,
        project_id: str,
        cooldown_id: str,
        comment: str,
        actor: str,
    ) -> CooldownWiringEventResponse:
        """Snapshot the cool-down's current wiring as an audit-log entry."""
        doc = self._load_cooldown_for_snapshot(project_id=project_id, cooldown_id=cooldown_id)
        event = self._events.append(
            project_id=project_id,
            cooldown_id=cooldown_id,
            actor=actor,
            action="checkpoint",
            comment=comment,
            wiring_info_snapshot=doc.wiring_info,
            block_count=len(doc.wiring_blocks),
            image_count=self._count_image_blocks(doc.wiring_blocks),
        )
        return self._to_response(event)

    def list_events(
        self,
        *,
        project_id: str,
        cooldown_id: str,
        limit: int = 100,
        skip: int = 0,
    ) -> ListCooldownWiringEventsResponse:
        # Surface a 404 for unknown cool-downs so the UI can distinguish that
        # from "no events yet".
        if self._cooldowns.get(project_id=project_id, cooldown_id=cooldown_id) is None:
            raise HTTPException(status_code=404, detail="Cooldown not found")
        events = self._events.list_by_cooldown(
            project_id=project_id, cooldown_id=cooldown_id, limit=limit, skip=skip
        )
        return ListCooldownWiringEventsResponse(events=[self._to_response(e) for e in events])

    # ---------- internal ----------

    def _load_cooldown_for_snapshot(self, *, project_id: str, cooldown_id: str) -> CooldownDocument:
        doc = self._cooldowns.get(project_id=project_id, cooldown_id=cooldown_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Cooldown not found")
        return doc

    @staticmethod
    def _to_response(doc: CooldownWiringEventDocument) -> CooldownWiringEventResponse:
        return CooldownWiringEventResponse(
            id=str(doc.id),
            cooldown_id=doc.cooldown_id,
            actor_user_id=doc.actor_user_id,
            actor=doc.actor,
            action=doc.action,
            comment=doc.comment,
            wiring_info_snapshot=doc.wiring_info_snapshot,
            block_count=doc.block_count,
            image_count=doc.image_count,
            created_at=doc.created_at,
        )

    @staticmethod
    def _count_image_blocks(blocks: list[dict[str, Any]]) -> int:
        return sum(1 for b in blocks if isinstance(b, dict) and b.get("type") == "image")
