"""The audit of a calibration session: the same history an agent session keeps, for its work.

A calibration session groups the pipeline runs and agent sessions started for one objective.
Its audit uses the agent session audit's mechanisms (``audit_timeline``) and event schema
(``AgentAuditEvent``): a read-time projection of authoritative records, snapshots bound to a
fingerprint, cursors, an export, and one kind of written record, an append-only decision with
a frozen snapshot of its evidence. History and execution control stay separate: recording a
decision grants nothing, and a pipeline run keeps the approval of its exact request, the
execution lock, and the session's admission rules; an agent session keeps its policy and gates.

The events, each from a record that already exists:

- ``session_created`` and ``session_closed``: the calibration session record.
- ``decision``: a ``CalibrationDecisionDocument``. Its interpretation and recommendation are
  the recorder's statements; a decision without a reported model is ``client_reported``.
- ``pipeline_requested``: a ``CalibrationPipelineRunDocument``, with the exact normalized spec
  QDash validated, the decision it carries out (named by the request, never inferred), and
  the launch origin the client reported.
- ``pipeline_dispatch``: the run's dispatch state, including refused and unknown outcomes.
- ``measurement``: each step execution of the run, with the target task results'
  executed run parameters and outputs.
- ``agent_session_linked``: each agent session created in the session; the events of an
  admitted one follow with ``agent_session_id`` set, exactly as its own audit shows them.

What QDash never receives is never shown as if it were recorded: a host's approval card or
dialog, and a declined approval, are outside QDash. An event lists such facts in ``missing``.

The facade composes narrower modules, each with one responsibility:

- ``calibration_audit_records``: loads the session and every record its audit reads.
- ``calibration_audit_evidence``: validates the evidence a decision or run request cites and
  builds a decision's frozen evidence snapshot.
- ``calibration_audit_decisions``: records decisions in the session's ledger and lists them.
- ``calibration_audit_search``: projects the search the detail read shows.
- ``calibration_audit_events``: projects the audit timeline's events.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from qdash.api.schemas.calibration_session import (
    CalibrationAuditSessionHeader,
    CalibrationSessionAuditResponse,
    ListCalibrationDecisionsResponse,
)
from qdash.api.services.audit_timeline import (
    DEFAULT_PAGE_SIZE,
    AuditSnapshot,
    fingerprint,
    read_export,
    read_page,
    utc,
)
from qdash.api.services.calibration_audit_decisions import (
    MAX_DECISIONS_PER_SESSION,
    decision_responses,
)
from qdash.api.services.calibration_audit_decisions import (
    record_decision as _record_decision,
)
from qdash.api.services.calibration_audit_events import (
    KIND_RANK,
    MAX_TASKS_PER_EVENT,
    session_timeline,
)
from qdash.api.services.calibration_audit_evidence import (
    MAX_SNAPSHOT_TASKS,
    PAIR_STEP_TYPES,
    check_run_decision,
)
from qdash.api.services.calibration_audit_records import (
    CalibrationAuditRecords,
    load_session,
    requested_task_calls,
    run_dispatch_status,
    run_target_qids,
)
from qdash.api.services.calibration_audit_search import (
    MAX_DETAIL_DECISIONS,
    MEASURED_PARAMETERS,
    OPEN_TASK_STATUSES,
    STOPPED_STATUSES,
    SearchView,
    measure,
    search_view,
)
from qdash.common.utils.datetime import now
from qdash.datamodel.calibration_session import CalibrationRunKind
from qdash.dbmodel.agent_session import AgentSessionDocument
from qdash.dbmodel.calibration_session import (
    CalibrationDecisionDocument,
    CalibrationPipelineRunDocument,
)

if TYPE_CHECKING:
    from datetime import datetime

    from qdash.api.schemas.agent_session import AgentAuditEvent
    from qdash.api.schemas.calibration_session import (
        CalibrationDecisionResponse,
        RecordCalibrationDecisionRequest,
    )
    from qdash.dbmodel.calibration_session import CalibrationSessionDocument

__all__ = [
    "CALIBRATION_AUDIT_NOTES",
    "KIND_RANK",
    "MAX_DECISIONS_PER_SESSION",
    "MAX_DETAIL_DECISIONS",
    "MAX_SNAPSHOT_TASKS",
    "MAX_TASKS_PER_EVENT",
    "MEASURED_PARAMETERS",
    "OPEN_TASK_STATUSES",
    "PAIR_STEP_TYPES",
    "STOPPED_STATUSES",
    "CalibrationSessionAuditService",
    "SearchView",
    "check_run_decision",
    "measure",
    "requested_task_calls",
    "run_dispatch_status",
    "run_target_qids",
]

CALIBRATION_AUDIT_NOTES = [
    "Every event comes from a QDash record; nothing is inferred to fill a gap, and no causal "
    "link is drawn from timestamps. A fact the records do not hold is listed in the event's "
    "`missing`.",
    "A pipeline run carries out a decision only when the request that started it named the "
    "decision (`decision_id`). Execution outcomes are the server's records; decision text is "
    "the recorder's statement (`agent_reported` when the client reported a model, otherwise "
    "`client_reported`).",
    "QDash records the request the signed-in user's client sent. A host's approval card or "
    "dialog, and an approval that was declined, never reach QDash: an approved run shows as "
    "its request, a declined one only as a decision no run carries out. `host_approval` in "
    "`missing` says so for a run an agent tool reported.",
    "`model` and the launch origin are what the client reported; QDash does not verify them. "
    "The signed-in user stays responsible for every request.",
    "An admitted agent session's events appear with `agent_session_id`, exactly as its own "
    "audit shows them; that audit keeps its own snapshot and export.",
    "Closing the session records no verdict, and no status says the objective was met. A "
    "recommendation is a decision's conclusion, never inferred.",
    "A response is one snapshot: two consecutive reads of every record agreed. Pages of one "
    "snapshot share its `snapshot_id`; a page is refused when the records changed since the "
    "first page. Records are append-only through the QDash API; this is an application audit, "
    "not a tamper-proof ledger.",
]


class CalibrationSessionAuditService:
    """Record decisions in a calibration session and read its audit."""

    # ------------------------------------------------------------------ decisions

    def record_decision(
        self,
        *,
        project_id: str,
        calibration_session_id: str,
        username: str,
        body: RecordCalibrationDecisionRequest,
    ) -> CalibrationDecisionResponse:
        """Append one decision to a calibration session the signed-in user created.

        Like an agent session decision, recording changes no state and passes no execution
        gate, so it is allowed in every status, including a closed session. A retry with the
        same idempotency key and request returns the same record.
        """
        return _record_decision(
            project_id=project_id,
            calibration_session_id=calibration_session_id,
            username=username,
            body=body,
        )

    def list_decisions(
        self, *, project_id: str, calibration_session_id: str
    ) -> ListCalibrationDecisionsResponse:
        """A calibration session's decisions, oldest first."""
        session = load_session(project_id, calibration_session_id)
        items = decision_responses(CalibrationAuditRecords(session))
        return ListCalibrationDecisionsResponse(items=items, total=len(items))

    # ------------------------------------------------------------------ search view

    def search(self, session: CalibrationSessionDocument) -> SearchView:
        """Experiments, decisions, the recommendation, and the latest requested run."""
        return search_view(session)

    # ------------------------------------------------------------------ timeline

    def timeline(self, session: CalibrationSessionDocument) -> list[AgentAuditEvent]:
        """Every event of the calibration session, in stable chronological order."""
        return session_timeline(session)

    # ------------------------------------------------------------------ reads

    @staticmethod
    def _header(session: CalibrationSessionDocument) -> CalibrationAuditSessionHeader:
        scope = {
            "project_id": session.project_id,
            "calibration_session_id": session.calibration_session_id,
        }
        return CalibrationAuditSessionHeader(
            calibration_session_id=session.calibration_session_id,
            project_id=session.project_id,
            chip_id=session.chip_id,
            objective=session.objective,
            created_by=session.created_by,
            created_at=cast("datetime", utc(session.created_at)),
            status=session.status,
            pipeline_run_total=CalibrationPipelineRunDocument.find(
                {**scope, "run_kind": {"$ne": CalibrationRunKind.AGENT_ACTION.value}}
            ).count(),
            agent_session_total=AgentSessionDocument.find(scope).count(),
            decision_total=CalibrationDecisionDocument.find(scope).count(),
        )

    def _read_once(
        self, project_id: str, calibration_session_id: str
    ) -> AuditSnapshot[CalibrationAuditSessionHeader]:
        session = load_session(project_id, calibration_session_id)
        header = self._header(session)
        events = self.timeline(session)
        return AuditSnapshot(header, events, fingerprint(header, events))

    @staticmethod
    def _response(
        snapshot: AuditSnapshot[CalibrationAuditSessionHeader],
        events: list[AgentAuditEvent],
        next_cursor: str | None,
    ) -> CalibrationSessionAuditResponse:
        return CalibrationSessionAuditResponse(
            generated_at=cast("datetime", utc(now())),
            snapshot_id=snapshot.snapshot_id,
            calibration_session=snapshot.header,
            events=events,
            total_events=len(snapshot.events),
            next_cursor=next_cursor,
            complete=next_cursor is None,
            notes=CALIBRATION_AUDIT_NOTES,
        )

    def read_audit(
        self,
        *,
        project_id: str,
        calibration_session_id: str,
        cursor: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
    ) -> CalibrationSessionAuditResponse:
        """One page of a snapshot of the audit, oldest first, as an agent session's audit pages."""
        page = read_page(
            project_id=project_id,
            scope_id=calibration_session_id,
            noun="calibration session",
            read_once=lambda: self._read_once(project_id, calibration_session_id),
            cursor=cursor,
            limit=limit,
        )
        return self._response(page.snapshot, page.events, page.next_cursor)

    def export_audit(
        self, *, project_id: str, calibration_session_id: str
    ) -> CalibrationSessionAuditResponse:
        """The whole of one snapshot; refused, never cut short, beyond the export bound."""
        snapshot = read_export(
            lambda: self._read_once(project_id, calibration_session_id), "calibration session"
        )
        return self._response(snapshot, snapshot.events, None)
