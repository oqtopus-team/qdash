"""Service layer for cryostat CRUD."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qdash.api.schemas.cryostat import (
    CryostatCreateRequest,
    CryostatResponse,
    CryostatUpdateRequest,
    ListCryostatsResponse,
)
from qdash.api.schemas.success import SuccessResponse
from qdash.dbmodel.cryostat import CryostatDocument
from starlette.exceptions import HTTPException

if TYPE_CHECKING:
    from qdash.repository.cryostat import MongoCryostatRepository


class CryostatService:
    """CRUD operations for CryostatDocument."""

    def __init__(self, cryostat_repository: MongoCryostatRepository) -> None:
        self._repo = cryostat_repository

    @staticmethod
    def _to_response(doc: CryostatDocument) -> CryostatResponse:
        return CryostatResponse(
            cryo_id=doc.cryo_id,
            name=doc.name,
            manufacturer=doc.manufacturer,
            model=doc.model,
            location=doc.location,
            status=doc.status,
            commissioned_at=doc.commissioned_at,
            decommissioned_at=doc.decommissioned_at,
            note=doc.note,
        )

    def list_all(self, *, project_id: str) -> ListCryostatsResponse:
        docs = self._repo.list_all(project_id=project_id)
        return ListCryostatsResponse(cryostats=[self._to_response(d) for d in docs])

    def get(self, *, project_id: str, cryo_id: str) -> CryostatResponse:
        doc = self._repo.get(project_id=project_id, cryo_id=cryo_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Cryostat not found")
        return self._to_response(doc)

    def create(self, *, project_id: str, body: CryostatCreateRequest) -> CryostatResponse:
        existing = self._repo.get(project_id=project_id, cryo_id=body.cryo_id)
        if existing is not None:
            raise HTTPException(status_code=409, detail=f"Cryostat {body.cryo_id} already exists")
        doc = CryostatDocument(
            project_id=project_id,
            cryo_id=body.cryo_id,
            name=body.name,
            manufacturer=body.manufacturer,
            model=body.model,
            location=body.location,
            status=body.status,
            commissioned_at=body.commissioned_at,
        )
        self._repo.insert(doc)
        return self._to_response(doc)

    def update(
        self,
        *,
        project_id: str,
        cryo_id: str,
        body: CryostatUpdateRequest,
    ) -> CryostatResponse:
        doc = self._repo.get(project_id=project_id, cryo_id=cryo_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Cryostat not found")
        if body.name is not None:
            doc.name = body.name
        if body.manufacturer is not None:
            doc.manufacturer = body.manufacturer
        if body.model is not None:
            doc.model = body.model
        if body.location is not None:
            doc.location = body.location
        if body.status is not None:
            doc.status = body.status
        if body.commissioned_at is not None:
            doc.commissioned_at = body.commissioned_at
        if body.decommissioned_at is not None:
            doc.decommissioned_at = body.decommissioned_at
        self._repo.save(doc)
        return self._to_response(doc)

    def delete(self, *, project_id: str, cryo_id: str) -> SuccessResponse:
        deleted = self._repo.delete(project_id=project_id, cryo_id=cryo_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Cryostat not found")
        return SuccessResponse(message="Cryostat deleted")
