"""Service layer for unified note CRUD across qubits, couplings, task results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime  # noqa: TC003
from typing import TYPE_CHECKING

from starlette.exceptions import HTTPException

from qdash.api.schemas.note import (
    ChipNotesSummaryResponse,
    ListNoteEventsResponse,
    NoteEventResponse,
    TargetNoteEntry,
    TaskNoteEntry,
)
from qdash.api.schemas.success import SuccessResponse
from qdash.common.datetime_utils import ensure_timezone, format_iso, now
from qdash.datamodel.note import NoteModel
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.cooldown import CooldownDocument
from qdash.dbmodel.coupling import CouplingDocument
from qdash.dbmodel.metric_note import MetricNoteDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.repository.note_event import MongoNoteEventRepository

if TYPE_CHECKING:
    from qdash.api.services.notification_service import NotificationService
    from qdash.dbmodel.note_event import NoteEventDocument


def _make_note(content: str, username: str) -> NoteModel:
    return NoteModel(content=content, updated_by=username, updated_at=now())


def _is_set(note: NoteModel) -> bool:
    return bool(note.content) or note.updated_at is not None


@dataclass(frozen=True)
class MetricNoteScope:
    """Resolved operational scope for a dashboard metric note."""

    scope_type: str
    scope_key: str
    cooldown_id: str | None
    started_at: datetime | None
    ended_at: datetime | None
    source: str


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

    @staticmethod
    def _current_cooldown(*, project_id: str, chip_id: str) -> CooldownDocument | None:
        chip = ChipDocument.find_one(
            ChipDocument.project_id == project_id,
            ChipDocument.chip_id == chip_id,
        ).run()
        if chip is None:
            return None
        cooldown_id = chip.current_cooldown_id
        if not isinstance(cooldown_id, str) or not cooldown_id:
            return None
        return CooldownDocument.find_one(
            CooldownDocument.project_id == project_id,
            CooldownDocument.cooldown_id == cooldown_id,
            CooldownDocument.chip_ids == chip_id,
        ).run()

    @staticmethod
    def _scope_key(
        *,
        scope_type: str,
        cooldown_id: str | None,
        started_at: datetime | None,
        ended_at: datetime | None,
    ) -> str:
        if scope_type == "cooldown" and cooldown_id:
            return f"cooldown:{cooldown_id}"
        if scope_type == "time_range":
            return f"time_range:{format_iso(started_at) or ''}:{format_iso(ended_at) or ''}"
        return "global"

    @staticmethod
    def _cooldown_scope(cooldown: CooldownDocument, source: str) -> MetricNoteScope:
        started_at = ensure_timezone(cooldown.started_at)
        ended_at = ensure_timezone(cooldown.ended_at)
        return MetricNoteScope(
            scope_type="cooldown",
            scope_key=f"cooldown:{cooldown.cooldown_id}",
            cooldown_id=cooldown.cooldown_id,
            started_at=started_at,
            ended_at=ended_at,
            source=source,
        )

    @classmethod
    def _find_cooldown_for_range(
        cls,
        *,
        project_id: str,
        chip_id: str,
        start_at: datetime,
        end_at: datetime | None,
    ) -> CooldownDocument | None:
        start_at = ensure_timezone(start_at) or start_at
        end_at = ensure_timezone(end_at)
        cooldowns = list(
            CooldownDocument.find(
                CooldownDocument.project_id == project_id,
                CooldownDocument.chip_ids == chip_id,
            ).run()
        )
        matches: list[CooldownDocument] = []
        for cooldown in cooldowns:
            cooldown_start = ensure_timezone(cooldown.started_at)
            cooldown_end = ensure_timezone(cooldown.ended_at)
            if cooldown_start is None or cooldown_start > start_at:
                continue
            if end_at is None:
                matches.append(cooldown)
                continue
            if cooldown_end is None or cooldown_end >= end_at:
                matches.append(cooldown)
        if len(matches) == 1:
            return matches[0]
        return None

    @classmethod
    def _resolve_metric_note_scope(
        cls,
        *,
        project_id: str,
        chip_id: str,
        cooldown_id: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> MetricNoteScope:
        if cooldown_id:
            cooldown = CooldownDocument.find_one(
                CooldownDocument.project_id == project_id,
                CooldownDocument.cooldown_id == cooldown_id,
                CooldownDocument.chip_ids == chip_id,
            ).run()
            if cooldown is not None:
                return cls._cooldown_scope(cooldown, "explicit_cooldown")
            return MetricNoteScope(
                scope_type="cooldown",
                scope_key=f"cooldown:{cooldown_id}",
                cooldown_id=cooldown_id,
                started_at=ensure_timezone(start_at),
                ended_at=ensure_timezone(end_at),
                source="explicit_cooldown",
            )

        normalized_start = ensure_timezone(start_at)
        normalized_end = ensure_timezone(end_at)
        if normalized_start is not None:
            cooldown = cls._find_cooldown_for_range(
                project_id=project_id,
                chip_id=chip_id,
                start_at=normalized_start,
                end_at=normalized_end,
            )
            if cooldown is not None:
                return cls._cooldown_scope(cooldown, "inferred_from_range")
            return MetricNoteScope(
                scope_type="time_range",
                scope_key=cls._scope_key(
                    scope_type="time_range",
                    cooldown_id=None,
                    started_at=normalized_start,
                    ended_at=normalized_end,
                ),
                cooldown_id=None,
                started_at=normalized_start,
                ended_at=normalized_end,
                source="manual_time_range",
            )

        current = cls._current_cooldown(project_id=project_id, chip_id=chip_id)
        if current is not None:
            return cls._cooldown_scope(current, "current_cooldown")

        return MetricNoteScope(
            scope_type="global",
            scope_key="global",
            cooldown_id=None,
            started_at=None,
            ended_at=None,
            source="legacy_global",
        )

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
        cooldown_id: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> NoteModel:
        doc = QubitDocument.find_one(
            QubitDocument.project_id == project_id,
            QubitDocument.chip_id == chip_id,
            QubitDocument.qid == qid,
        ).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Qubit not found")
        note = _make_note(content, username)
        scope = self._resolve_metric_note_scope(
            project_id=project_id,
            chip_id=chip_id,
            cooldown_id=cooldown_id,
            start_at=start_at,
            end_at=end_at,
        )
        metric_note = MetricNoteDocument.find_one(
            MetricNoteDocument.project_id == project_id,
            MetricNoteDocument.chip_id == chip_id,
            MetricNoteDocument.target_type == "qubit",
            MetricNoteDocument.target_id == qid,
            MetricNoteDocument.metric_key == metric_key,
            MetricNoteDocument.scope_key == scope.scope_key,
        ).run()
        if metric_note is None:
            metric_note = MetricNoteDocument(
                project_id=project_id,
                chip_id=chip_id,
                target_type="qubit",
                target_id=qid,
                metric_key=metric_key,
                note=note,
                scope_type=scope.scope_type,
                scope_key=scope.scope_key,
                cooldown_id=scope.cooldown_id,
                scope_started_at=scope.started_at,
                scope_ended_at=scope.ended_at,
                scope_source=scope.source,
            )
            metric_note.insert()
        else:
            metric_note.note = note
            metric_note.scope_type = scope.scope_type
            metric_note.cooldown_id = scope.cooldown_id
            metric_note.scope_started_at = scope.started_at
            metric_note.scope_ended_at = scope.ended_at
            metric_note.scope_source = scope.source
            metric_note.system_info.update_time()
            metric_note.save()
        self._log(
            project_id=project_id,
            chip_id=chip_id,
            scope="qubit_metric",
            target_id=qid,
            metric_key=metric_key,
            action="upsert",
            actor=username,
            content=content,
            extra={
                "scope_key": scope.scope_key,
                "scope_type": scope.scope_type,
                "cooldown_id": scope.cooldown_id or "",
            },
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
        cooldown_id: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> SuccessResponse:
        doc = QubitDocument.find_one(
            QubitDocument.project_id == project_id,
            QubitDocument.chip_id == chip_id,
            QubitDocument.qid == qid,
        ).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Metric note not found")
        scope = self._resolve_metric_note_scope(
            project_id=project_id,
            chip_id=chip_id,
            cooldown_id=cooldown_id,
            start_at=start_at,
            end_at=end_at,
        )
        metric_note = MetricNoteDocument.find_one(
            MetricNoteDocument.project_id == project_id,
            MetricNoteDocument.chip_id == chip_id,
            MetricNoteDocument.target_type == "qubit",
            MetricNoteDocument.target_id == qid,
            MetricNoteDocument.metric_key == metric_key,
            MetricNoteDocument.scope_key == scope.scope_key,
        ).run()
        if metric_note is None:
            if scope.scope_type != "global" or metric_key not in doc.metric_notes:
                raise HTTPException(status_code=404, detail="Metric note not found")
            del doc.metric_notes[metric_key]
            doc.system_info.update_time()
            doc.save()
        else:
            metric_note.delete()
        self._log(
            project_id=project_id,
            chip_id=chip_id,
            scope="qubit_metric",
            target_id=qid,
            metric_key=metric_key,
            action="delete",
            actor=username,
            content="",
            extra={
                "scope_key": scope.scope_key,
                "scope_type": scope.scope_type,
                "cooldown_id": scope.cooldown_id or "",
            },
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
        cooldown_id: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> NoteModel:
        doc = CouplingDocument.find_one(
            CouplingDocument.project_id == project_id,
            CouplingDocument.chip_id == chip_id,
            CouplingDocument.qid == coupling_id,
        ).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Coupling not found")
        note = _make_note(content, username)
        scope = self._resolve_metric_note_scope(
            project_id=project_id,
            chip_id=chip_id,
            cooldown_id=cooldown_id,
            start_at=start_at,
            end_at=end_at,
        )
        metric_note = MetricNoteDocument.find_one(
            MetricNoteDocument.project_id == project_id,
            MetricNoteDocument.chip_id == chip_id,
            MetricNoteDocument.target_type == "coupling",
            MetricNoteDocument.target_id == coupling_id,
            MetricNoteDocument.metric_key == metric_key,
            MetricNoteDocument.scope_key == scope.scope_key,
        ).run()
        if metric_note is None:
            metric_note = MetricNoteDocument(
                project_id=project_id,
                chip_id=chip_id,
                target_type="coupling",
                target_id=coupling_id,
                metric_key=metric_key,
                note=note,
                scope_type=scope.scope_type,
                scope_key=scope.scope_key,
                cooldown_id=scope.cooldown_id,
                scope_started_at=scope.started_at,
                scope_ended_at=scope.ended_at,
                scope_source=scope.source,
            )
            metric_note.insert()
        else:
            metric_note.note = note
            metric_note.scope_type = scope.scope_type
            metric_note.cooldown_id = scope.cooldown_id
            metric_note.scope_started_at = scope.started_at
            metric_note.scope_ended_at = scope.ended_at
            metric_note.scope_source = scope.source
            metric_note.system_info.update_time()
            metric_note.save()
        self._log(
            project_id=project_id,
            chip_id=chip_id,
            scope="coupling_metric",
            target_id=coupling_id,
            metric_key=metric_key,
            action="upsert",
            actor=username,
            content=content,
            extra={
                "scope_key": scope.scope_key,
                "scope_type": scope.scope_type,
                "cooldown_id": scope.cooldown_id or "",
            },
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
        cooldown_id: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> SuccessResponse:
        doc = CouplingDocument.find_one(
            CouplingDocument.project_id == project_id,
            CouplingDocument.chip_id == chip_id,
            CouplingDocument.qid == coupling_id,
        ).run()
        if doc is None:
            raise HTTPException(status_code=404, detail="Metric note not found")
        scope = self._resolve_metric_note_scope(
            project_id=project_id,
            chip_id=chip_id,
            cooldown_id=cooldown_id,
            start_at=start_at,
            end_at=end_at,
        )
        metric_note = MetricNoteDocument.find_one(
            MetricNoteDocument.project_id == project_id,
            MetricNoteDocument.chip_id == chip_id,
            MetricNoteDocument.target_type == "coupling",
            MetricNoteDocument.target_id == coupling_id,
            MetricNoteDocument.metric_key == metric_key,
            MetricNoteDocument.scope_key == scope.scope_key,
        ).run()
        if metric_note is None:
            if scope.scope_type != "global" or metric_key not in doc.metric_notes:
                raise HTTPException(status_code=404, detail="Metric note not found")
            del doc.metric_notes[metric_key]
            doc.system_info.update_time()
            doc.save()
        else:
            metric_note.delete()
        self._log(
            project_id=project_id,
            chip_id=chip_id,
            scope="coupling_metric",
            target_id=coupling_id,
            metric_key=metric_key,
            action="delete",
            actor=username,
            content="",
            extra={
                "scope_key": scope.scope_key,
                "scope_type": scope.scope_type,
                "cooldown_id": scope.cooldown_id or "",
            },
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

    def chip_notes_summary(
        self,
        *,
        project_id: str,
        chip_id: str,
        cooldown_id: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> ChipNotesSummaryResponse:
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

        scope = self._resolve_metric_note_scope(
            project_id=project_id,
            chip_id=chip_id,
            cooldown_id=cooldown_id,
            start_at=start_at,
            end_at=end_at,
        )
        metric_note_docs = list(
            MetricNoteDocument.find(
                MetricNoteDocument.project_id == project_id,
                MetricNoteDocument.chip_id == chip_id,
                MetricNoteDocument.scope_key == scope.scope_key,
            ).run()
        )
        if scope.scope_type == "cooldown" and scope.started_at is not None:
            range_query: dict[str, object] = {
                "project_id": project_id,
                "chip_id": chip_id,
                "scope_type": "time_range",
                "scope_started_at": {"$gte": scope.started_at},
            }
            if scope.ended_at is not None:
                range_query["scope_ended_at"] = {"$lte": scope.ended_at}
            metric_note_docs.extend(MetricNoteDocument.find(range_query).run())
        metric_notes_by_target: dict[str, dict[str, NoteModel]] = {}
        for metric_note in metric_note_docs:
            key = f"{metric_note.target_type}:{metric_note.target_id}"
            notes = metric_notes_by_target.setdefault(key, {})
            if metric_note.metric_key in notes and metric_note.scope_key != scope.scope_key:
                continue
            notes[metric_note.metric_key] = metric_note.note

        def metric_notes_for_target(
            *, target_type: str, target_id: str, legacy: dict[str, NoteModel]
        ) -> dict[str, NoteModel]:
            notes = dict(metric_notes_by_target.get(f"{target_type}:{target_id}", {}))
            if scope.scope_type == "global":
                notes = {**legacy, **notes}
            return notes

        qubits = [
            TargetNoteEntry(
                target_id=d.qid,
                note=d.note,
                metric_notes=metric_notes_for_target(
                    target_type="qubit", target_id=d.qid, legacy=d.metric_notes
                ),
            )
            for d in qubit_docs
            if _is_set(d.note)
            or metric_notes_for_target(target_type="qubit", target_id=d.qid, legacy=d.metric_notes)
        ]
        couplings = [
            TargetNoteEntry(
                target_id=d.qid,
                note=d.note,
                metric_notes=metric_notes_for_target(
                    target_type="coupling", target_id=d.qid, legacy=d.metric_notes
                ),
            )
            for d in coupling_docs
            if _is_set(d.note)
            or metric_notes_for_target(
                target_type="coupling", target_id=d.qid, legacy=d.metric_notes
            )
        ]
        task_notes = [
            TaskNoteEntry(task_id=d.task_id, qid=d.qid, note=d.user_note)
            for d in task_docs
            if _is_set(d.user_note)
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
