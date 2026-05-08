"""Service layer for unified note CRUD across qubits, couplings, task results."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qdash.api.schemas.note import (
    ChipNotesSummaryResponse,
    ListNoteEventsResponse,
    NoteEventResponse,
    TargetNoteEntry,
    TaskNoteEntry,
)
from qdash.api.schemas.success import SuccessResponse
from qdash.common.datetime_utils import now
from qdash.datamodel.note import NoteModel
from qdash.dbmodel.coupling import CouplingDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.repository.note_event import MongoNoteEventRepository
from starlette.exceptions import HTTPException

if TYPE_CHECKING:
    from qdash.api.services.notification_service import NotificationService
    from qdash.dbmodel.note_event import NoteEventDocument


def _make_note(content: str, username: str) -> NoteModel:
    return NoteModel(content=content, updated_by=username, updated_at=now())


class NoteService:
    """Note CRUD across QubitDocument, CouplingDocument, TaskResultHistoryDocument.

    Every successful upsert/delete also appends a row to ``note_event`` (audit
    log + knowledge feed).
    """

    def __init__(
        self,
        event_repo: MongoNoteEventRepository | None = None,
        notification_service: NotificationService | None = None,
    ) -> None:
        self._events = event_repo or MongoNoteEventRepository()
        self._notifications = notification_service

    def _log(
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
        event = self._events.append(
            project_id=project_id,
            chip_id=chip_id,
            scope=scope,
            target_id=target_id,
            metric_key=metric_key,
            action=action,
            actor=actor,
            content=content,
            extra=extra or {},
        )
        if action == "upsert":
            self._notify_note_mentions(
                event_id=str(event.id),
                project_id=project_id,
                chip_id=chip_id,
                scope=scope,
                target_id=target_id,
                actor=actor,
                content=content,
            )
        return event

    @staticmethod
    def _note_target_url(*, scope: str, chip_id: str, target_id: str) -> str:
        if scope == "task_result":
            return f"/task-results/{target_id}"
        return f"/chip?chip_id={chip_id}"

    def _notify_note_mentions(
        self,
        *,
        event_id: str,
        project_id: str,
        chip_id: str,
        scope: str,
        target_id: str,
        actor: str,
        content: str,
    ) -> None:
        if not self._notifications or not content:
            return
        label = scope.replace("_", " ")
        self._notifications.notify_note_mentions(
            project_id=project_id,
            note_event_id=event_id,
            actor_username=actor,
            content=content,
            target_url=self._note_target_url(scope=scope, chip_id=chip_id, target_id=target_id),
            title=f"{actor} mentioned you in a {label} note",
        )

    # ---------- qubit ----------

    def upsert_qubit_note(
        self,
        *,
        project_id: str,
        chip_id: str,
        qid: str,
        content: str,
        username: str,
    ) -> NoteModel:
        doc = QubitDocument.find_one(
            QubitDocument.project_id == project_id,
            QubitDocument.chip_id == chip_id,
            QubitDocument.qid == qid,
        ).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Qubit not found")
        doc.note = _make_note(content, username)
        doc.system_info.update_time()
        doc.save()
        self._log(
            project_id=project_id,
            chip_id=chip_id,
            scope="qubit",
            target_id=qid,
            metric_key="",
            action="upsert",
            actor=username,
            content=content,
        )
        return doc.note

    def delete_qubit_note(
        self, *, project_id: str, chip_id: str, qid: str, username: str
    ) -> SuccessResponse:
        doc = QubitDocument.find_one(
            QubitDocument.project_id == project_id,
            QubitDocument.chip_id == chip_id,
            QubitDocument.qid == qid,
        ).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Qubit not found")
        doc.note = NoteModel()
        doc.system_info.update_time()
        doc.save()
        self._log(
            project_id=project_id,
            chip_id=chip_id,
            scope="qubit",
            target_id=qid,
            metric_key="",
            action="delete",
            actor=username,
            content="",
        )
        return SuccessResponse(message="Qubit note cleared")

    def upsert_qubit_metric_note(
        self,
        *,
        project_id: str,
        chip_id: str,
        qid: str,
        metric_key: str,
        content: str,
        username: str,
    ) -> NoteModel:
        doc = QubitDocument.find_one(
            QubitDocument.project_id == project_id,
            QubitDocument.chip_id == chip_id,
            QubitDocument.qid == qid,
        ).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Qubit not found")
        note = _make_note(content, username)
        doc.metric_notes[metric_key] = note
        doc.system_info.update_time()
        doc.save()
        self._log(
            project_id=project_id,
            chip_id=chip_id,
            scope="qubit_metric",
            target_id=qid,
            metric_key=metric_key,
            action="upsert",
            actor=username,
            content=content,
        )
        return note

    def delete_qubit_metric_note(
        self,
        *,
        project_id: str,
        chip_id: str,
        qid: str,
        metric_key: str,
        username: str,
    ) -> SuccessResponse:
        doc = QubitDocument.find_one(
            QubitDocument.project_id == project_id,
            QubitDocument.chip_id == chip_id,
            QubitDocument.qid == qid,
        ).run()
        if doc is None or metric_key not in doc.metric_notes:
            raise HTTPException(status_code=404, detail="Metric note not found")
        del doc.metric_notes[metric_key]
        doc.system_info.update_time()
        doc.save()
        self._log(
            project_id=project_id,
            chip_id=chip_id,
            scope="qubit_metric",
            target_id=qid,
            metric_key=metric_key,
            action="delete",
            actor=username,
            content="",
        )
        return SuccessResponse(message="Qubit metric note deleted")

    # ---------- coupling ----------

    def upsert_coupling_note(
        self,
        *,
        project_id: str,
        chip_id: str,
        coupling_id: str,
        content: str,
        username: str,
    ) -> NoteModel:
        doc = CouplingDocument.find_one(
            CouplingDocument.project_id == project_id,
            CouplingDocument.chip_id == chip_id,
            CouplingDocument.qid == coupling_id,
        ).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Coupling not found")
        doc.note = _make_note(content, username)
        doc.system_info.update_time()
        doc.save()
        self._log(
            project_id=project_id,
            chip_id=chip_id,
            scope="coupling",
            target_id=coupling_id,
            metric_key="",
            action="upsert",
            actor=username,
            content=content,
        )
        return doc.note

    def delete_coupling_note(
        self, *, project_id: str, chip_id: str, coupling_id: str, username: str
    ) -> SuccessResponse:
        doc = CouplingDocument.find_one(
            CouplingDocument.project_id == project_id,
            CouplingDocument.chip_id == chip_id,
            CouplingDocument.qid == coupling_id,
        ).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Coupling not found")
        doc.note = NoteModel()
        doc.system_info.update_time()
        doc.save()
        self._log(
            project_id=project_id,
            chip_id=chip_id,
            scope="coupling",
            target_id=coupling_id,
            metric_key="",
            action="delete",
            actor=username,
            content="",
        )
        return SuccessResponse(message="Coupling note cleared")

    def upsert_coupling_metric_note(
        self,
        *,
        project_id: str,
        chip_id: str,
        coupling_id: str,
        metric_key: str,
        content: str,
        username: str,
    ) -> NoteModel:
        doc = CouplingDocument.find_one(
            CouplingDocument.project_id == project_id,
            CouplingDocument.chip_id == chip_id,
            CouplingDocument.qid == coupling_id,
        ).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Coupling not found")
        note = _make_note(content, username)
        doc.metric_notes[metric_key] = note
        doc.system_info.update_time()
        doc.save()
        self._log(
            project_id=project_id,
            chip_id=chip_id,
            scope="coupling_metric",
            target_id=coupling_id,
            metric_key=metric_key,
            action="upsert",
            actor=username,
            content=content,
        )
        return note

    def delete_coupling_metric_note(
        self,
        *,
        project_id: str,
        chip_id: str,
        coupling_id: str,
        metric_key: str,
        username: str,
    ) -> SuccessResponse:
        doc = CouplingDocument.find_one(
            CouplingDocument.project_id == project_id,
            CouplingDocument.chip_id == chip_id,
            CouplingDocument.qid == coupling_id,
        ).run()
        if doc is None or metric_key not in doc.metric_notes:
            raise HTTPException(status_code=404, detail="Metric note not found")
        del doc.metric_notes[metric_key]
        doc.system_info.update_time()
        doc.save()
        self._log(
            project_id=project_id,
            chip_id=chip_id,
            scope="coupling_metric",
            target_id=coupling_id,
            metric_key=metric_key,
            action="delete",
            actor=username,
            content="",
        )
        return SuccessResponse(message="Coupling metric note deleted")

    # ---------- task result ----------

    def get_task_note(self, *, project_id: str, task_id: str) -> NoteModel | None:
        doc = TaskResultHistoryDocument.find_one(
            TaskResultHistoryDocument.project_id == project_id,
            TaskResultHistoryDocument.task_id == task_id,
        ).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Task result not found")
        note: NoteModel = doc.user_note
        # Treat empty content + None timestamp as "no note set yet"
        if not note.content and note.updated_at is None:
            return None
        return note

    def upsert_task_note(
        self,
        *,
        project_id: str,
        task_id: str,
        content: str,
        username: str,
    ) -> NoteModel:
        doc = TaskResultHistoryDocument.find_one(
            TaskResultHistoryDocument.project_id == project_id,
            TaskResultHistoryDocument.task_id == task_id,
        ).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Task result not found")
        doc.user_note = _make_note(content, username)
        doc.save()
        self._log(
            project_id=project_id,
            chip_id=doc.chip_id,
            scope="task_result",
            target_id=task_id,
            metric_key="",
            action="upsert",
            actor=username,
            content=content,
            extra={"qid": doc.qid or "", "task_name": doc.name},
        )
        return doc.user_note

    def delete_task_note(self, *, project_id: str, task_id: str, username: str) -> SuccessResponse:
        doc = TaskResultHistoryDocument.find_one(
            TaskResultHistoryDocument.project_id == project_id,
            TaskResultHistoryDocument.task_id == task_id,
        ).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Task result not found")
        doc.user_note = NoteModel()
        doc.save()
        self._log(
            project_id=project_id,
            chip_id=doc.chip_id,
            scope="task_result",
            target_id=task_id,
            metric_key="",
            action="delete",
            actor=username,
            content="",
            extra={"qid": doc.qid or "", "task_name": doc.name},
        )
        return SuccessResponse(message="Task note cleared")

    # ---------- chip-wide summary for the dashboard ----------

    def chip_notes_summary(self, *, project_id: str, chip_id: str) -> ChipNotesSummaryResponse:
        qubit_docs = list(
            QubitDocument.find(
                QubitDocument.project_id == project_id,
                QubitDocument.chip_id == chip_id,
            ).run()
        )
        coupling_docs = list(
            CouplingDocument.find(
                CouplingDocument.project_id == project_id,
                CouplingDocument.chip_id == chip_id,
            ).run()
        )
        # Use the partial sparse index on user_note.updated_at so we only scan
        # the small subset of task results that actually have a note set.
        task_docs = list(
            TaskResultHistoryDocument.find(
                {
                    "project_id": project_id,
                    "chip_id": chip_id,
                    "user_note.updated_at": {"$ne": None},
                }
            ).run()
        )

        def is_set(n: NoteModel) -> bool:
            return bool(n.content) or n.updated_at is not None

        qubits = [
            TargetNoteEntry(
                target_id=d.qid,
                note=d.note,
                metric_notes=d.metric_notes,
            )
            for d in qubit_docs
            if is_set(d.note) or d.metric_notes
        ]
        couplings = [
            TargetNoteEntry(
                target_id=d.qid,
                note=d.note,
                metric_notes=d.metric_notes,
            )
            for d in coupling_docs
            if is_set(d.note) or d.metric_notes
        ]
        task_notes = [
            TaskNoteEntry(task_id=d.task_id, qid=d.qid, note=d.user_note)
            for d in task_docs
            if is_set(d.user_note)
        ]
        return ChipNotesSummaryResponse(
            chip_id=chip_id,
            qubits=qubits,
            couplings=couplings,
            task_notes=task_notes,
        )

    # ---------- note-event feed (audit log / knowledge view) ----------

    @staticmethod
    def _event_to_response(doc) -> NoteEventResponse:  # type: ignore[no-untyped-def]
        return NoteEventResponse(
            project_id=doc.project_id,
            chip_id=doc.chip_id,
            scope=doc.scope,
            target_id=doc.target_id,
            metric_key=doc.metric_key,
            action=doc.action,
            actor_user_id=doc.actor_user_id,
            actor=doc.actor,
            content=doc.content,
            extra=doc.extra,
            created_at=doc.created_at,
        )

    def list_chip_events(
        self,
        *,
        project_id: str,
        chip_id: str,
        skip: int = 0,
        limit: int = 50,
    ) -> ListNoteEventsResponse:
        docs = self._events.list_by_chip(
            project_id=project_id, chip_id=chip_id, skip=skip, limit=limit
        )
        return ListNoteEventsResponse(events=[self._event_to_response(d) for d in docs])

    def list_target_events(
        self,
        *,
        project_id: str,
        scope: str,
        target_id: str,
        skip: int = 0,
        limit: int = 50,
    ) -> ListNoteEventsResponse:
        docs = self._events.list_by_target(
            project_id=project_id,
            scope=scope,
            target_id=target_id,
            skip=skip,
            limit=limit,
        )
        return ListNoteEventsResponse(events=[self._event_to_response(d) for d in docs])

    def search_events(
        self,
        *,
        project_id: str,
        query: str,
        skip: int = 0,
        limit: int = 50,
    ) -> ListNoteEventsResponse:
        docs = self._events.search(project_id=project_id, query=query, skip=skip, limit=limit)
        return ListNoteEventsResponse(events=[self._event_to_response(d) for d in docs])
