"""MongoDB repository for CryostatDocument."""

from __future__ import annotations

from qdash.dbmodel.cryostat import CryostatDocument


class MongoCryostatRepository:
    """CRUD helpers for CryostatDocument."""

    def list_all(self, *, project_id: str) -> list[CryostatDocument]:
        return list(
            CryostatDocument.find(
                CryostatDocument.project_id == project_id,
            ).run()
        )

    def get(self, *, project_id: str, cryo_id: str) -> CryostatDocument | None:
        return CryostatDocument.find_one(
            CryostatDocument.project_id == project_id,
            CryostatDocument.cryo_id == cryo_id,
        ).run()

    def insert(self, doc: CryostatDocument) -> CryostatDocument:
        doc.insert()
        return doc

    def save(self, doc: CryostatDocument) -> CryostatDocument:
        doc.system_info.update_time()
        doc.save()
        return doc

    def delete(self, *, project_id: str, cryo_id: str) -> bool:
        existing = self.get(project_id=project_id, cryo_id=cryo_id)
        if existing is None:
            return False
        existing.delete()
        return True
