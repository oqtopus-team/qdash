"""MongoDB repository for the NoteEvent audit log."""

from __future__ import annotations

from bunnet import SortDirection

from qdash.dbmodel.note_event import NoteEventDocument
from qdash.dbmodel.user import UserDocument


class MongoNoteEventRepository:
    """Append + query helpers for NoteEventDocument."""

    @staticmethod
    def _user_id_for_username(username: str) -> str | None:
        user = UserDocument.find_one({"username": username}).run()
        return user.user_id if user else None

    def append(
        self,
        *,
        project_id: str,
        chip_id: str,
        scope: str,
        target_id: str,
        metric_key: str,
        action: str,
        actor: str,
        content: str,
        extra: dict[str, str] | None = None,
    ) -> NoteEventDocument:
        doc = NoteEventDocument(
            project_id=project_id,
            chip_id=chip_id,
            scope=scope,
            target_id=target_id,
            metric_key=metric_key,
            action=action,
            actor_user_id=self._user_id_for_username(actor),
            actor=actor,
            content=content,
            extra=extra or {},
        )
        doc.insert()
        return doc

    def list_by_chip(
        self,
        *,
        project_id: str,
        chip_id: str,
        limit: int = 50,
        skip: int = 0,
    ) -> list[NoteEventDocument]:
        return list(
            NoteEventDocument.find(
                NoteEventDocument.project_id == project_id,
                NoteEventDocument.chip_id == chip_id,
            )
            .sort([("created_at", SortDirection.DESCENDING)])
            .skip(skip)
            .limit(limit)
            .run()
        )

    def list_by_target(
        self,
        *,
        project_id: str,
        scope: str,
        target_id: str,
        limit: int = 50,
        skip: int = 0,
    ) -> list[NoteEventDocument]:
        return list(
            NoteEventDocument.find(
                NoteEventDocument.project_id == project_id,
                NoteEventDocument.scope == scope,
                NoteEventDocument.target_id == target_id,
            )
            .sort([("created_at", SortDirection.DESCENDING)])
            .skip(skip)
            .limit(limit)
            .run()
        )

    def search(
        self,
        *,
        project_id: str,
        query: str,
        limit: int = 50,
        skip: int = 0,
    ) -> list[NoteEventDocument]:
        """Full-text search over note contents within a project."""
        # Use raw motor collection so we can pass $text + meta sort
        collection = NoteEventDocument.get_motor_collection()
        cursor = (
            collection.find(
                {"project_id": project_id, "$text": {"$search": query}},
                {"score": {"$meta": "textScore"}},
            )
            .sort([("score", {"$meta": "textScore"})])
            .skip(skip)
            .limit(limit)
        )
        return [NoteEventDocument.model_validate(doc) for doc in cursor]
