"""Service layer for cool-down CRUD + chip association."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qdash.api.schemas.cooldown import (
    CooldownCreateRequest,
    CooldownResponse,
    CooldownUpdateRequest,
    ListCooldownsResponse,
)
from qdash.api.schemas.success import SuccessResponse
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.cooldown import CooldownDocument
from starlette.exceptions import HTTPException

if TYPE_CHECKING:
    from qdash.repository.cooldown import MongoCooldownRepository
    from qdash.repository.cryostat import MongoCryostatRepository


class CooldownService:
    """CRUD + chip-assign/unassign for CooldownDocument."""

    def __init__(
        self,
        cooldown_repository: MongoCooldownRepository,
        cryostat_repository: MongoCryostatRepository,
    ) -> None:
        self._repo = cooldown_repository
        self._cryostats = cryostat_repository

    @staticmethod
    def _to_response(doc: CooldownDocument) -> CooldownResponse:
        return CooldownResponse(
            cooldown_id=doc.cooldown_id,
            cryo_id=doc.cryo_id,
            description=doc.description,
            started_at=doc.started_at,
            ended_at=doc.ended_at,
            chip_ids=list(doc.chip_ids),
            note=doc.note,
        )

    def list_all(
        self,
        *,
        project_id: str,
        cryo_id: str | None = None,
        chip_id: str | None = None,
    ) -> ListCooldownsResponse:
        docs = self._repo.list_all(project_id=project_id, cryo_id=cryo_id, chip_id=chip_id)
        return ListCooldownsResponse(cooldowns=[self._to_response(d) for d in docs])

    def get(self, *, project_id: str, cooldown_id: str) -> CooldownResponse:
        doc = self._repo.get(project_id=project_id, cooldown_id=cooldown_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Cooldown not found")
        return self._to_response(doc)

    def create(self, *, project_id: str, body: CooldownCreateRequest) -> CooldownResponse:
        # cryostat must exist
        if self._cryostats.get(project_id=project_id, cryo_id=body.cryo_id) is None:
            raise HTTPException(status_code=400, detail=f"Cryostat {body.cryo_id} does not exist")
        if self._repo.get(project_id=project_id, cooldown_id=body.cooldown_id) is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Cooldown {body.cooldown_id} already exists",
            )
        doc = CooldownDocument(
            project_id=project_id,
            cooldown_id=body.cooldown_id,
            cryo_id=body.cryo_id,
            description=body.description,
            started_at=body.started_at,
            ended_at=body.ended_at,
            chip_ids=list(body.chip_ids),
        )
        self._repo.insert(doc)
        # Tag chips that were specified at creation time
        for chip_id in body.chip_ids:
            self._set_chip_current_cooldown(
                project_id=project_id,
                chip_id=chip_id,
                cooldown_id=doc.cooldown_id if doc.ended_at is None else None,
            )
        return self._to_response(doc)

    def update(
        self,
        *,
        project_id: str,
        cooldown_id: str,
        body: CooldownUpdateRequest,
    ) -> CooldownResponse:
        doc = self._repo.get(project_id=project_id, cooldown_id=cooldown_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Cooldown not found")
        was_active = doc.ended_at is None
        if body.description is not None:
            doc.description = body.description
        if body.started_at is not None:
            doc.started_at = body.started_at
        if body.ended_at is not None:
            doc.ended_at = body.ended_at
        self._repo.save(doc)
        # If the cool-down ended, clear chip.current_cooldown_id for any chip
        # that pointed to this one.
        is_active = doc.ended_at is None
        if was_active and not is_active:
            for chip_id in doc.chip_ids:
                self._maybe_clear_chip_current_cooldown(
                    project_id=project_id, chip_id=chip_id, cooldown_id=cooldown_id
                )
        return self._to_response(doc)

    def delete(self, *, project_id: str, cooldown_id: str) -> SuccessResponse:
        doc = self._repo.get(project_id=project_id, cooldown_id=cooldown_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Cooldown not found")
        for chip_id in doc.chip_ids:
            self._maybe_clear_chip_current_cooldown(
                project_id=project_id, chip_id=chip_id, cooldown_id=cooldown_id
            )
        doc.delete()
        return SuccessResponse(message="Cooldown deleted")

    # ---------- chip ↔ cooldown association ----------

    def assign_chip(self, *, project_id: str, cooldown_id: str, chip_id: str) -> CooldownResponse:
        doc = self._repo.get(project_id=project_id, cooldown_id=cooldown_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Cooldown not found")
        if chip_id not in doc.chip_ids:
            doc.chip_ids = [*doc.chip_ids, chip_id]
            self._repo.save(doc)
        # Only an *active* cool-down should set chip.current_cooldown_id
        if doc.ended_at is None:
            self._set_chip_current_cooldown(
                project_id=project_id, chip_id=chip_id, cooldown_id=cooldown_id
            )
        return self._to_response(doc)

    def unassign_chip(self, *, project_id: str, cooldown_id: str, chip_id: str) -> CooldownResponse:
        doc = self._repo.get(project_id=project_id, cooldown_id=cooldown_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Cooldown not found")
        if chip_id in doc.chip_ids:
            doc.chip_ids = [c for c in doc.chip_ids if c != chip_id]
            self._repo.save(doc)
        self._maybe_clear_chip_current_cooldown(
            project_id=project_id, chip_id=chip_id, cooldown_id=cooldown_id
        )
        return self._to_response(doc)

    # ---------- internal helpers ----------

    @staticmethod
    def _set_chip_current_cooldown(
        *, project_id: str, chip_id: str, cooldown_id: str | None
    ) -> None:
        chip = ChipDocument.find_one(
            ChipDocument.project_id == project_id,
            ChipDocument.chip_id == chip_id,
        ).run()
        if chip is None:
            return
        chip.current_cooldown_id = cooldown_id
        chip.system_info.update_time()
        chip.save()

    @classmethod
    def _maybe_clear_chip_current_cooldown(
        cls, *, project_id: str, chip_id: str, cooldown_id: str
    ) -> None:
        """Clear chip.current_cooldown_id only if it currently points to ``cooldown_id``."""
        chip = ChipDocument.find_one(
            ChipDocument.project_id == project_id,
            ChipDocument.chip_id == chip_id,
        ).run()
        if chip is None:
            return
        if getattr(chip, "current_cooldown_id", None) != cooldown_id:
            return
        chip.current_cooldown_id = None
        chip.system_info.update_time()
        chip.save()
