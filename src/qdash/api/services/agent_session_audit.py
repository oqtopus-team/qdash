"""Chronological experiment audit of one agent session, built from QDash's own records.

The timeline is read, not stored: every event comes from an authoritative record that already
exists (the session, its actions, executions, task results, evaluations, candidate commits,
backend applies, and interventions). The only records this module writes are agent decisions
(``AgentDecisionDocument``): the agent's concise reading of a result and the step it chose,
with a frozen snapshot of what QDash's records said about the cited evidence at that moment.
Decisions are append-only; a correction is a new decision that supersedes an earlier one.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from bunnet import SortDirection
from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError

from qdash.api.schemas.agent_session import (
    AgentAuditEvent,
    AgentAuditSessionHeader,
    AgentDecisionResponse,
    AgentSessionAuditResponse,
    ListAgentDecisionsResponse,
    RecordAgentDecisionRequest,
)
from qdash.api.services.agent_execution_links import resolve_chip_links, utc
from qdash.api.services.agent_session_gate import load_agent_session
from qdash.api.services.agent_session_service import AgentSessionService
from qdash.common.utils.datetime import now
from qdash.datamodel.agent_session import AgentActionDecision, AgentActionType
from qdash.dbmodel.agent_session import (
    AgentActionDocument,
    AgentCandidateCommitDocument,
    AgentCandidateSetCommitDocument,
    AgentDecisionDocument,
    AgentInterventionDocument,
    AgentSessionDocument,
)
from qdash.dbmodel.evaluation import EvaluationDocument
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

AUDIT_SCHEMA_VERSION = "qdash.agent-session-audit.v1"
# Decisions one session may record; far above any real loop, it bounds a runaway client.
MAX_DECISIONS_PER_SESSION = 2000
# Inserts one recording tries while concurrent recordings keep taking the slot it chose.
MAX_SLOT_ATTEMPTS = 20
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500
# An export larger than this is refused rather than cut short.
MAX_EXPORT_EVENTS = 100_000
# Per-record bounds of copied scalars; an event says when a bound dropped entries.
MAX_PARAMETERS = 50
MAX_TEXT = 500
# Cursors name the snapshot they page through; v1 cursors (a sort key) are refused.
CURSOR_PREFIX = "v2"
# Reads of the whole record set one snapshot takes at most before it gives up (see
# AgentSessionAuditService._read_snapshot).
SNAPSHOT_ATTEMPTS = 3

# Order of events that share a timestamp: cause before effect.
KIND_RANK = {
    "session_created": 0,
    "action_proposed": 1,
    "measurement": 2,
    "evaluation": 3,
    "decision": 4,
    "intervention_opened": 5,
    "candidate_commit": 6,
    "candidate_set_commit": 7,
    "backend_apply": 8,
    "intervention_response": 9,
    "intervention_resumed": 10,
    "resume_outcome": 11,
}

AUDIT_NOTES = [
    "Every event comes from a QDash record; nothing is inferred to fill a gap. A fact the "
    "records do not hold is listed in the event's `missing`.",
    "`agent_reported` text (intent, decisions, intervention summaries) is the agent's own "
    "statement; `server_record` and `server_computed` fields are QDash's. A decision's "
    "`evidence_snapshot` is what QDash's records said when the decision was recorded.",
    "`status_is_current` marks a status read live from a record that can still change "
    "(a running measurement, a commit, a backend apply, an evaluation, an intervention).",
    "Candidate gate results are recomputed from the task result and the session's immutable "
    "policy. Figures and raw data are referenced by task_id; read them through the task-result "
    "API, which checks project access.",
    "A response is one snapshot of the records, read when its first page or the export was "
    "requested: two consecutive reads of every record agreed, so it is what the records held "
    "at one instant, provided no record changed and then changed back in between. Records "
    "written later are not in it; a new read includes them. Pages of one snapshot share its "
    "`snapshot_id`; a page is refused when the records changed since the first page.",
    "Records are append-only through the QDash API. This is an application audit, not a "
    "tamper-proof ledger: a database administrator can change stored records.",
]


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _text(value: Any, limit: int = MAX_TEXT) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _scalar(value: Any) -> Any:
    """A JSON scalar copy of a value, or None when it is not a finite scalar."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value if math.isfinite(float(value)) else None
    if isinstance(value, str):
        return _text(value, 200)
    return None


def _parameters(raw: dict[str, Any] | None) -> tuple[dict[str, dict[str, Any]], int]:
    """Scalar parameter values with their unit and error; arrays and objects are left out."""
    items: dict[str, dict[str, Any]] = {}
    dropped = 0
    for name, entry in sorted((raw or {}).items()):
        if isinstance(entry, dict):
            value = _scalar(entry.get("value"))
            row: dict[str, Any] = {"value": value}
            if entry.get("unit"):
                row["unit"] = _text(entry.get("unit"), 50)
            error = _scalar(entry.get("error"))
            if isinstance(error, (int, float)) and not isinstance(error, bool) and error:
                row["error"] = error
        else:
            value = _scalar(entry)
            row = {"value": value}
        if value is None and not (isinstance(entry, dict) and entry.get("value") is None):
            dropped += 1
            continue
        if len(items) >= MAX_PARAMETERS:
            dropped += 1
            continue
        items[name] = row
    return items, dropped


def _snapshot_value(snapshot: dict[str, Any] | None) -> Any:
    if snapshot is None:
        return None
    return _scalar(snapshot.get("value"))


class _Records:
    """Every record of one session the timeline reads, loaded once with batched queries."""

    def __init__(self, session: AgentSessionDocument) -> None:
        project_id = session.project_id
        session_id = session.session_id
        scope = {"project_id": project_id, "session_id": session_id}
        self.session = session
        self.execution_links = resolve_chip_links(project_id, session.chip_id)
        self.actions = cast(
            "list[AgentActionDocument]",
            AgentActionDocument.find(scope, sort=[("created_at", SortDirection.ASCENDING)]).run(),
        )
        self.commits = cast(
            "list[AgentCandidateCommitDocument]", AgentCandidateCommitDocument.find(scope).run()
        )
        self.set_commits = cast(
            "list[AgentCandidateSetCommitDocument]",
            AgentCandidateSetCommitDocument.find(scope).run(),
        )
        self.interventions = cast(
            "list[AgentInterventionDocument]", AgentInterventionDocument.find(scope).run()
        )
        self.decisions = cast(
            "list[AgentDecisionDocument]",
            AgentDecisionDocument.find(
                scope, sort=[("recorded_at", SortDirection.ASCENDING)]
            ).run(),
        )

        # Executions: operation_id is the Prefect flow run id; older actions stored the
        # QDash execution id there or in execution_id.
        operation_ids = sorted({a.operation_id for a in self.actions if a.operation_id})
        execution_ids = sorted({a.execution_id for a in self.actions if a.execution_id})
        self.executions: dict[str, ExecutionHistoryDocument] = {}
        if operation_ids or execution_ids:
            found = cast(
                "list[ExecutionHistoryDocument]",
                ExecutionHistoryDocument.find(
                    {
                        "project_id": project_id,
                        "$or": [
                            {"note.flow_run_id": {"$in": operation_ids}},
                            {"execution_id": {"$in": operation_ids + execution_ids}},
                        ],
                    }
                ).run(),
            )
            # The order the Execution grouping resolves in (``agent_execution_links``): a flow
            # run id several executions carry names the earliest, never the database's order.
            found.sort(
                key=lambda e: (
                    utc(e.start_at) or datetime.min.replace(tzinfo=UTC),
                    e.execution_id,
                )
            )
            for execution in found:
                self.executions[execution.execution_id] = execution
            for execution in found:
                flow_run_id = (execution.note or {}).get("flow_run_id")
                if isinstance(flow_run_id, str):
                    self.executions.setdefault(flow_run_id, execution)

        result_execution_ids = sorted(
            {
                execution_id
                for execution_id in (self.execution_id_of(action) for action in self.actions)
                if execution_id
            }
        )
        by_key: dict[tuple[str, str, str], TaskResultHistoryDocument] = {}
        if result_execution_ids:
            results = cast(
                "list[TaskResultHistoryDocument]",
                TaskResultHistoryDocument.find(
                    {"project_id": project_id, "execution_id": {"$in": result_execution_ids}},
                    sort=[("end_at", SortDirection.ASCENDING)],
                ).run(),
            )
            for result in results:
                # Ascending end_at, so the latest result of a task on a qubit wins, as the
                # candidate reader picks it.
                by_key[(result.execution_id, result.name, result.qid)] = result
        self.task_results: dict[str, TaskResultHistoryDocument] = {}
        for action in self.actions:
            execution_id = self.execution_id_of(action)
            if execution_id is None or not action.task_name or len(action.qids) != 1:
                continue
            matched = by_key.get((execution_id, action.task_name, action.qids[0]))
            if matched is not None and matched.chip_id == session.chip_id:
                self.task_results[action.action_id] = matched

        task_ids = sorted({result.task_id for result in self.task_results.values()})
        self.evaluations: list[EvaluationDocument] = []
        if task_ids:
            self.evaluations = cast(
                "list[EvaluationDocument]",
                EvaluationDocument.find(
                    {"project_id": project_id, "task_id": {"$in": task_ids}},
                    sort=[("requested_at", SortDirection.ASCENDING)],
                ).run(),
            )

    def execution_of(self, action: AgentActionDocument) -> ExecutionHistoryDocument | None:
        link = self.execution_links.by_action.get(action.action_id)
        return self.executions.get(link.execution_id) if link is not None else None

    def execution_id_of(self, action: AgentActionDocument) -> str | None:
        """The execution attributed to this action by the shared ownership resolver."""
        link = self.execution_links.by_action.get(action.action_id)
        return link.execution_id if link is not None else None


# ---------------------------------------------------------------------- evidence snapshots


def _gate_rows(
    session: AgentSessionDocument, action_id: str, result: TaskResultHistoryDocument
) -> list[dict[str, Any]]:
    if result.status != "completed":
        return []
    rows = AgentSessionService.gate_task_result(session, action_id, result)
    return [
        {
            "parameter_name": row.parameter_name,
            "value": row.value,
            "error": row.error,
            "unit": row.unit,
            "accepted": row.accepted,
            "reason": _text(row.reason, 300),
            "minimum": row.minimum,
            "maximum": row.maximum,
        }
        for row in rows[:MAX_PARAMETERS]
    ]


def _measurement_facts(
    records: _Records, action: AgentActionDocument
) -> tuple[dict[str, Any], list[str]]:
    """What QDash's records say about one action's measurement, and what they do not hold."""
    missing: list[str] = []
    execution = records.execution_of(action)
    result = records.task_results.get(action.action_id)
    conflict = records.execution_links.unlinked.get(action.action_id)
    if conflict is not None:
        missing.append(f"execution_link_{conflict.reason}")
    execution_status = execution.status if execution is not None else action.execution_status
    facts: dict[str, Any] = {
        "dispatch_status": action.execution_status,
        "execution_status": execution_status,
        "execution_id": records.execution_id_of(action),
        "operation_id": action.operation_id,
        "requested_overrides": dict(action.parameter_overrides),
    }
    if action.metadata.get("execution_error"):
        # The dispatch error text can carry transport details; the audit keeps only the fact.
        facts["dispatch_error_recorded"] = True
    if action.metadata.get("source_execution_id"):
        facts["source_execution_id"] = action.metadata["source_execution_id"]
    if execution is not None:
        facts["started_at"] = _utc(execution.start_at)
        facts["finished_at"] = _utc(execution.end_at)
    elif action.operation_id and not action.execution_id:
        missing.append("execution")
    if result is None:
        if execution_status in {"completed", "failed"}:
            missing.append("task_result")
        return facts, missing
    effective, dropped_inputs = _parameters(result.input_parameters)
    outputs, dropped_outputs = _parameters(result.output_parameters)
    metrics = {
        name: value
        for name, value in sorted(result.quality_metrics.items())
        if isinstance(value, (int, float)) and math.isfinite(float(value))
    }
    facts |= {
        "task_id": result.task_id,
        "task_result_status": result.status,
        "task_result_message": _text(result.message, 300),
        "effective_inputs": effective,
        "outputs": outputs,
        "quality_metrics": metrics,
        "gate": _gate_rows(records.session, action.action_id, result),
        "artifacts": {
            "task_result_path": f"/tasks/{result.task_id}/result",
            "figures": len(result.figure_path),
            "interactive_figures": len(result.json_figure_path),
            "raw_data_files": len(result.raw_data_path),
        },
    }
    if dropped_inputs or dropped_outputs:
        facts["omitted_non_scalar_or_extra_parameters"] = dropped_inputs + dropped_outputs
    return facts, missing


def _evaluation_facts(evaluation: EvaluationDocument) -> dict[str, Any]:
    diagnosis: dict[str, Any] = {}
    output = evaluation.output
    if output is not None and isinstance(output.diagnosis, dict):
        for key, value in list(output.diagnosis.items())[:20]:
            scalar = _scalar(value)
            if scalar is not None:
                diagnosis[key] = scalar
    return {
        "evaluation_id": evaluation.evaluation_id,
        "run_id": evaluation.run_id,
        "task_id": evaluation.task_id,
        "status": evaluation.status,
        "completed_at": _utc(evaluation.completed_at),
        "evaluator_model": output.model if output is not None else None,
        "diagnosis": diagnosis,
        "error_recorded": bool(evaluation.error),
        "reviewer_verdicts": [
            {
                "username": verdict.username,
                "agree": verdict.agree,
                "note": _text(verdict.note, 300) if verdict.note else None,
                "updated_at": _utc(verdict.updated_at),
            }
            for verdict in evaluation.verdicts[:20]
        ],
    }


# ---------------------------------------------------------------------- service


class AgentSessionAuditService:
    """Record agent decisions and read a session's chronological experiment audit."""

    # ------------------------------------------------------------------ decisions

    @staticmethod
    def _decision_response(doc: AgentDecisionDocument) -> AgentDecisionResponse:
        return AgentDecisionResponse.model_validate(doc.model_dump())

    @staticmethod
    def _decision_hash(body: RecordAgentDecisionRequest) -> str:
        payload = json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    def record_decision(
        self,
        *,
        project_id: str,
        session_id: str,
        username: str,
        body: RecordAgentDecisionRequest,
    ) -> AgentDecisionResponse:
        """Append one agent decision to a session the signed-in user created.

        Recording changes no session state and passes no execution gate, so it is allowed in
        every session status, including a paused, completed, stopped, or expired session.
        A retry with the same idempotency key returns the same record.
        """
        session = load_agent_session(project_id, session_id)
        if username != session.created_by:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Only {session.created_by}, who created this agent session, records its "
                    "decisions"
                ),
            )
        request_hash = self._decision_hash(body)
        scope = {"project_id": project_id, "session_id": session_id}
        existing = self._by_key(scope, body.idempotency_key)
        if existing is not None:
            return self._replay(existing, request_hash)
        if self._used_slots(scope) >= MAX_DECISIONS_PER_SESSION:
            raise self._quota_full()

        records = _Records(session)
        actions = {action.action_id: action for action in records.actions}
        evidence_ids = list(dict.fromkeys(body.evidence_action_ids))
        referenced = [
            *evidence_ids,
            *([body.next_action_id] if body.next_action_id else []),
        ]
        unknown = [action_id for action_id in referenced if action_id not in actions]
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Not actions of this session: {', '.join(unknown)}",
            )
        session_task_ids = {result.task_id for result in records.task_results.values()}
        evaluations = {evaluation.evaluation_id: evaluation for evaluation in records.evaluations}
        evaluation_ids = list(dict.fromkeys(body.evaluation_ids))
        foreign = [
            evaluation_id
            for evaluation_id in evaluation_ids
            if evaluation_id not in evaluations
            or evaluations[evaluation_id].task_id not in session_task_ids
        ]
        if foreign:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=("Not evaluations of this session's task results: " + ", ".join(foreign)),
            )
        if body.intervention_id and body.intervention_id not in {
            item.intervention_id for item in records.interventions
        }:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Not an intervention of this session: {body.intervention_id}",
            )
        if body.supersedes_decision_id and body.supersedes_decision_id not in {
            item.decision_id for item in records.decisions
        }:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Not a decision of this session: {body.supersedes_decision_id}",
            )

        snapshot_actions: list[dict[str, Any]] = []
        for action_id in evidence_ids:
            action = actions[action_id]
            facts, missing = _measurement_facts(records, action)
            snapshot_actions.append(
                {
                    "action_id": action_id,
                    "action_type": action.action_type.value,
                    "task_name": action.task_name,
                    "qids": list(action.qids),
                    "decision": action.decision.value,
                    **facts,
                    "missing": missing,
                }
            )
        fields: dict[str, Any] = {
            "project_id": project_id,
            "session_id": session_id,
            "chip_id": session.chip_id,
            "idempotency_key": body.idempotency_key,
            "request_hash": request_hash,
            "recorded_by": username,
            "session_status_at_record": session.status.value,
            "session_state_version_at_record": session.state_version,
            "assessment": body.assessment,
            "interpretation": body.interpretation,
            "next_action": body.next_action,
            "next_detail": body.next_detail,
            "evidence_action_ids": evidence_ids,
            "evaluation_ids": evaluation_ids,
            "next_action_id": body.next_action_id,
            "intervention_id": body.intervention_id,
            "supersedes_decision_id": body.supersedes_decision_id,
            "evidence_snapshot": json.loads(
                json.dumps(
                    {
                        "actions": snapshot_actions,
                        "evaluations": [
                            _evaluation_facts(evaluations[evaluation_id])
                            for evaluation_id in evaluation_ids
                        ],
                    },
                    default=lambda value: (
                        value.isoformat() if isinstance(value, datetime) else str(value)
                    ),
                )
            ),
        }
        return self._insert_in_free_slot(scope, fields, request_hash)

    @staticmethod
    def _by_key(scope: dict[str, str], key: str) -> AgentDecisionDocument | None:
        return cast(
            "AgentDecisionDocument | None",
            AgentDecisionDocument.find_one({**scope, "idempotency_key": key}).run(),
        )

    @staticmethod
    def _used_slots(scope: dict[str, str]) -> int:
        """The next free quota slot: one past the highest slot a decision of the session holds.

        Slots are taken in order, so this is also the number of decisions. A record removed
        outside the API leaves its slot unused rather than reused.
        """
        last = cast(
            "list[AgentDecisionDocument]",
            AgentDecisionDocument.find(scope)
            .sort([("quota_slot", SortDirection.DESCENDING)])
            .limit(1)
            .run(),
        )
        return last[0].quota_slot + 1 if last else 0

    @staticmethod
    def _quota_full() -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"The session's audit is full: it already holds {MAX_DECISIONS_PER_SESSION} "
                "decisions, so no further decision is recorded"
            ),
        )

    def _insert_in_free_slot(
        self, scope: dict[str, str], fields: dict[str, Any], request_hash: str
    ) -> AgentDecisionResponse:
        """Insert the decision in the session's lowest free quota slot.

        The quota check and the record are one insert: the unique (session, slot) and
        (session, idempotency key) indexes make Mongo refuse a second record for a slot or a
        key, without a transaction. A refused insert means a concurrent recording won; the
        loop then replays that record when it carries the same key, or takes the next slot.
        Nothing is reserved apart from the record itself, so a crash before the insert
        leaves no slot held and a crash after it leaves a complete record that a retry with
        the same key returns.
        """
        for _ in range(MAX_SLOT_ATTEMPTS):
            slot = self._used_slots(scope)
            if slot >= MAX_DECISIONS_PER_SESSION:
                raced = self._by_key(scope, fields["idempotency_key"])
                if raced is not None:
                    return self._replay(raced, request_hash)
                raise self._quota_full()
            doc = AgentDecisionDocument(
                decision_id=str(uuid4()), recorded_at=now(), quota_slot=slot, **fields
            )
            try:
                doc.insert()
            except DuplicateKeyError:
                raced = self._by_key(scope, fields["idempotency_key"])
                if raced is not None:
                    return self._replay(raced, request_hash)
                continue
            return self._decision_response(doc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Other decisions of the session were being recorded at the same time; retry",
            headers={"Retry-After": "1"},
        )

    def _replay(self, existing: AgentDecisionDocument, request_hash: str) -> AgentDecisionResponse:
        if existing.request_hash != request_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency key was already used for a different decision",
            )
        return self._decision_response(existing)

    def list_decisions(self, *, project_id: str, session_id: str) -> ListAgentDecisionsResponse:
        """A session's decisions, oldest first."""
        load_agent_session(project_id, session_id)
        docs = cast(
            "list[AgentDecisionDocument]",
            AgentDecisionDocument.find(
                {"project_id": project_id, "session_id": session_id},
                sort=[("recorded_at", SortDirection.ASCENDING)],
            ).run(),
        )
        return ListAgentDecisionsResponse(
            items=[self._decision_response(doc) for doc in docs], total=len(docs)
        )

    # ------------------------------------------------------------------ timeline

    @staticmethod
    def _header(session: AgentSessionDocument) -> AgentAuditSessionHeader:
        missing = [
            name
            for name in ("skill_name", "skill_version", "skill_hash", "model_name")
            if not getattr(session, name)
        ]
        return AgentAuditSessionHeader(
            session_id=session.session_id,
            project_id=session.project_id,
            chip_id=session.chip_id,
            created_by=session.created_by,
            created_at=cast("datetime", _utc(session.created_at)),
            expires_at=cast("datetime", _utc(session.expires_at)),
            status=session.status,
            state_version=session.state_version,
            action_count=session.action_count,
            policy=session.policy,
            skill_name=session.skill_name,
            skill_version=session.skill_version,
            skill_hash=session.skill_hash,
            model_name=session.model_name,
            missing=missing,
        )

    def timeline(self, session: AgentSessionDocument) -> list[AgentAuditEvent]:
        """Every event of the session, in stable chronological order."""
        records = _Records(session)
        events: list[AgentAuditEvent] = []
        decided = {
            action_id
            for decision in records.decisions
            for action_id in decision.evidence_action_ids
        }
        superseded_by = {
            decision.supersedes_decision_id: decision.decision_id
            for decision in records.decisions
            if decision.supersedes_decision_id
        }

        def add(**fields: Any) -> None:
            fields["at"] = _utc(fields["at"])
            events.append(AgentAuditEvent(sequence=0, **fields))

        identity = {
            name: getattr(session, name) or None
            for name in ("skill_name", "skill_version", "skill_hash", "model_name")
        }
        add(
            event_id=f"session_created:{session.session_id}",
            state_version=0,
            at=session.created_at,
            kind="session_created",
            summary=(
                f"{session.created_by} approved a session on {session.chip_id} for "
                f"{', '.join(session.policy.qids)} ({session.policy.autonomy.value})"
            ),
            actor=session.created_by,
            actor_kind="human",
            provenance="server_record",
            missing=[name for name, value in identity.items() if value is None],
            data={
                "policy": session.policy.model_dump(mode="json"),
                "expires_at": _utc(session.expires_at),
                # Reported by the client that created the session.
                "client_reported_identity": identity,
            },
        )

        for action in records.actions:
            submitted_by = action.metadata.get("submitted_by")
            autonomous = bool(action.metadata.get("autonomous", False))
            actor = submitted_by or (session.created_by if autonomous else None)
            rejected = action.decision == AgentActionDecision.REJECTED
            target = f"{action.task_name} on {', '.join(action.qids)}" if action.task_name else ""
            if action.action_type == AgentActionType.RUN_TASK:
                summary = (
                    f"Rejected {target}: {action.reason} (not executed)"
                    if rejected
                    else f"Authorized {target}"
                )
            elif action.action_type == AgentActionType.REQUEST_HUMAN:
                summary = "Rejected a request for an expert" if rejected else "Asked for an expert"
            else:
                summary = "Rejected completing the session" if rejected else "Completed the session"
            add(
                event_id=f"action_proposed:{action.action_id}",
                state_version=action.state_version_before,
                at=action.created_at,
                kind="action_proposed",
                summary=summary,
                actor=actor,
                actor_kind="agent",
                provenance="server_record",
                status=action.decision.value,
                action_id=action.action_id,
                task_name=action.task_name,
                qid=action.qids[0] if len(action.qids) == 1 else None,
                intervention_id=action.metadata.get("intervention_id"),
                missing=[] if actor else ["actor"],
                data={
                    "action_type": action.action_type.value,
                    "qids": list(action.qids),
                    "requested_overrides": dict(action.parameter_overrides),
                    "intent": action.diagnosis,
                    "agent_reported_fields": ["intent"] if action.diagnosis else [],
                    "authorization": action.decision.value,
                    "authorization_reason": action.reason,
                    "autonomous": autonomous,
                    "repeat_of_action_id": action.metadata.get("repeat_of_action_id"),
                    "state_version_before": action.state_version_before,
                    "state_version_after": action.state_version_after,
                    "dispatch_status": action.execution_status,
                },
            )
            if action.action_type != AgentActionType.RUN_TASK or rejected:
                continue
            if action.execution_status == "not_started" and not action.operation_id:
                continue
            facts, missing = _measurement_facts(records, action)
            execution_status = facts["execution_status"]
            if execution_status in {"completed", "failed"} and action.action_id not in decided:
                missing.append("decision")
            outputs = facts.get("outputs") or {}
            accepted = [row["parameter_name"] for row in facts.get("gate", []) if row["accepted"]]
            detail = (f"; outputs {', '.join(sorted(outputs)[:6])}" if outputs else "") + (
                f"; gate accepted {', '.join(accepted)}" if accepted else ""
            )
            add(
                event_id=f"measurement:{action.action_id}",
                state_version=action.state_version_after,
                # The dispatch time is fixed once set, so the event keeps its place.
                at=action.dispatch_reserved_at or facts.get("started_at") or action.created_at,
                kind="measurement",
                summary=f"{target}: {execution_status}{detail}",
                actor=session.created_by,
                actor_kind="worker",
                provenance="server_record",
                status=execution_status,
                status_is_current=True,
                action_id=action.action_id,
                execution_id=facts.get("execution_id"),
                task_id=facts.get("task_id"),
                task_name=action.task_name,
                qid=action.qids[0] if action.qids else None,
                missing=missing,
                data=facts,
            )

        task_versions = {
            result.task_id: action.state_version_after
            for action in records.actions
            if (result := records.task_results.get(action.action_id)) is not None
        }
        for evaluation in records.evaluations:
            facts = _evaluation_facts(evaluation)
            add(
                event_id=f"evaluation:{evaluation.evaluation_id}",
                state_version=task_versions.get(evaluation.task_id, 0),
                at=evaluation.requested_at,
                kind="evaluation",
                summary=(
                    f"Evaluation of {evaluation.task_name} on {evaluation.qid}: "
                    f"{evaluation.status}"
                    + (
                        f" ({facts['diagnosis']['status']})"
                        if isinstance(facts["diagnosis"].get("status"), str)
                        else ""
                    )
                ),
                actor=None,
                actor_kind="agent",
                provenance="evaluator_reported",
                status=evaluation.status,
                status_is_current=True,
                execution_id=evaluation.execution_id or None,
                task_id=evaluation.task_id,
                task_name=evaluation.task_name,
                qid=evaluation.qid,
                evaluation_id=evaluation.evaluation_id,
                data=facts,
            )

        for decision in records.decisions:
            assessment = decision.assessment.value if decision.assessment else "not stated"
            add(
                event_id=f"decision:{decision.decision_id}",
                state_version=decision.session_state_version_at_record,
                at=decision.recorded_at,
                kind="decision",
                summary=(
                    f"Assessed {assessment}; next {decision.next_action.value}"
                    + (f": {decision.next_detail}" if decision.next_detail else "")
                ),
                actor=decision.recorded_by,
                actor_kind="agent",
                provenance="agent_reported",
                status="superseded" if decision.decision_id in superseded_by else "recorded",
                action_id=decision.evidence_action_ids[0] if decision.evidence_action_ids else None,
                intervention_id=decision.intervention_id,
                decision_id=decision.decision_id,
                missing=[] if decision.assessment else ["assessment"],
                data={
                    "assessment": decision.assessment.value if decision.assessment else None,
                    "interpretation": decision.interpretation,
                    "next_action": decision.next_action.value,
                    "next_detail": decision.next_detail,
                    "evidence_action_ids": decision.evidence_action_ids,
                    "evaluation_ids": decision.evaluation_ids,
                    "next_action_id": decision.next_action_id,
                    "supersedes_decision_id": decision.supersedes_decision_id,
                    "superseded_by_decision_id": superseded_by.get(decision.decision_id),
                    "session_status_at_record": decision.session_status_at_record,
                    "session_state_version_at_record": decision.session_state_version_at_record,
                    "evidence_snapshot": decision.evidence_snapshot,
                },
            )

        for commit in records.commits:
            before = _snapshot_value(commit.before_snapshot)
            after = _snapshot_value(commit.after_snapshot)
            reason = "Candidate persistence failed" if commit.status == "failed" else commit.reason
            add(
                event_id=f"candidate_commit:{commit.commit_id}",
                state_version=commit.state_version_before,
                at=commit.created_at,
                kind="candidate_commit",
                summary=(
                    f"Commit of {commit.parameter_name} = {commit.value} on {commit.qid}: "
                    f"{commit.status}"
                    + (f" (was {before})" if commit.status == "committed" else "")
                ),
                actor=commit.committed_by,
                actor_kind="human",
                provenance="server_record",
                status=commit.status,
                status_is_current=True,
                action_id=commit.action_id,
                execution_id=commit.execution_id,
                task_id=commit.task_id,
                task_name=commit.task_name,
                qid=commit.qid,
                commit_id=commit.commit_id,
                missing=[]
                if commit.status != "committed" or commit.after_snapshot is not None
                else ["after_snapshot"],
                data={
                    "parameter_name": commit.parameter_name,
                    "value": commit.value,
                    "before_value": before,
                    "after_value": after,
                    "reason": reason,
                    "committed_at": _utc(commit.committed_at),
                    "state_version_before": commit.state_version_before,
                    "state_version_after": commit.state_version_after,
                },
            )
            if commit.backend_requested_at is not None:
                add(
                    event_id=f"backend_apply:{commit.commit_id}",
                    state_version=commit.state_version_after,
                    at=commit.backend_requested_at,
                    kind="backend_apply",
                    summary=(
                        f"Backend apply of {commit.parameter_name} on {commit.qid}: "
                        f"{commit.backend_status}"
                        + (" (verified)" if commit.backend_verified else "")
                    ),
                    actor=None,
                    actor_kind="worker",
                    provenance="server_record",
                    status=commit.backend_status,
                    status_is_current=True,
                    action_id=commit.action_id,
                    task_id=commit.task_id,
                    qid=commit.qid,
                    commit_id=commit.commit_id,
                    data={
                        "operation_id": commit.backend_operation_id,
                        "backend_name": commit.backend_name,
                        "target_files": commit.backend_target_files,
                        "changed_files": commit.backend_changed_files,
                        "verified": commit.backend_verified,
                        "base_git_commit": commit.backend_base_git_commit,
                        "git_commit": commit.backend_git_commit,
                        "push_to_github": commit.backend_push_to_github,
                        "applied_at": _utc(commit.backend_applied_at),
                        "error_recorded": bool(commit.backend_error),
                    },
                )

        for set_commit in records.set_commits:
            names = [str(item.get("parameter_name")) for item in set_commit.candidates]
            add(
                event_id=f"candidate_set_commit:{set_commit.commit_id}",
                state_version=set_commit.state_version_before,
                at=set_commit.created_at,
                kind="candidate_set_commit",
                summary=(f"Commit of {', '.join(names)} on {set_commit.qid}: {set_commit.status}"),
                actor=set_commit.committed_by,
                actor_kind="human",
                provenance="server_record",
                status=set_commit.status,
                status_is_current=True,
                qid=set_commit.qid,
                commit_id=set_commit.commit_id,
                data={
                    "candidates": [
                        {
                            "parameter_name": item.get("parameter_name"),
                            "value": item.get("value"),
                            "action_id": item.get("action_id"),
                            "task_id": item.get("task_id"),
                            "execution_id": item.get("execution_id"),
                            "before_value": _snapshot_value(
                                set_commit.before_snapshot.get(str(item.get("parameter_name")))
                            ),
                            "after_value": _snapshot_value(
                                set_commit.after_snapshot.get(str(item.get("parameter_name")))
                            ),
                        }
                        for item in set_commit.candidates
                    ],
                    "reason": "Candidate persistence failed"
                    if set_commit.status == "failed"
                    else set_commit.reason,
                    "committed_at": _utc(set_commit.committed_at),
                },
            )

        for item in records.interventions:
            answered_version = (
                item.response.expected_state_version
                if item.response is not None
                else item.session_state_version_at_open
            )
            add(
                event_id=f"intervention_opened:{item.intervention_id}",
                state_version=item.session_state_version_at_open,
                at=item.created_at,
                kind="intervention_opened",
                summary=f"Asked an expert ({item.reason.value}): {_text(item.question, 200)}",
                actor=item.created_by,
                actor_kind="agent",
                provenance="agent_reported",
                status=item.status.value,
                status_is_current=True,
                action_id=item.action_id,
                task_name=item.task_name,
                qid=item.qids[0] if len(item.qids) == 1 else None,
                intervention_id=item.intervention_id,
                data={
                    "reason": item.reason.value,
                    "summary": item.summary,
                    "question": item.question,
                    "qids": list(item.qids),
                    "node_id": item.node_id,
                    "attempts": [attempt.model_dump(mode="json") for attempt in item.attempts],
                    "previous_intervention_id": item.previous_intervention_id,
                    "pauses_session": item.pauses_session,
                    "session_status_at_open": item.session_status_at_open.value,
                    "plan_hash": item.plan_hash or None,
                    "stopped_node_id": item.checkpoint.stopped_node_id if item.checkpoint else None,
                    "notification_status": item.notification.status.value,
                },
            )
            if item.response is not None:
                response = item.response
                add(
                    event_id=f"intervention_response:{response.response_id}",
                    state_version=response.expected_state_version,
                    at=response.responded_at,
                    kind="intervention_response",
                    summary=(
                        f"{response.responded_by} chose {response.decision.value}"
                        + (f": {_text(response.guidance, 200)}" if response.guidance else "")
                    ),
                    actor=response.responded_by,
                    actor_kind="human",
                    provenance="human_reported",
                    status=response.decision.value,
                    intervention_id=item.intervention_id,
                    data={
                        "decision": response.decision.value,
                        "guidance": response.guidance,
                        "resume_node_id": response.resume_node_id,
                        "note": "Guidance is evidence for the agent; it grants no new scope.",
                    },
                )
            if item.resumed_at is not None:
                add(
                    event_id=f"intervention_resumed:{item.intervention_id}",
                    state_version=answered_version,
                    at=item.resumed_at,
                    kind="intervention_resumed",
                    summary=f"The runner of {item.resumed_by or 'an unknown user'} resumed",
                    actor=item.resumed_by,
                    actor_kind="agent",
                    provenance="server_record",
                    intervention_id=item.intervention_id,
                    missing=[] if item.resumed_by else ["actor"],
                )
            if item.resume_outcome is not None:
                outcome = item.resume_outcome
                add(
                    event_id=f"resume_outcome:{item.intervention_id}",
                    state_version=answered_version,
                    at=outcome.recorded_at,
                    kind="resume_outcome",
                    summary=f"The resumed run ended: {outcome.transition}",
                    actor=outcome.recorded_by,
                    actor_kind="agent",
                    provenance="agent_reported",
                    status=outcome.transition,
                    intervention_id=item.intervention_id,
                    data={
                        "transition": outcome.transition,
                        "reason": outcome.reason,
                        "follow_up_intervention_id": outcome.follow_up_intervention_id,
                    },
                )

        events.sort(key=_sort_key)
        for index, event in enumerate(events):
            event.sequence = index
        return events

    # ------------------------------------------------------------------ reads

    def _read_once(self, project_id: str, session_id: str) -> _Snapshot:
        """One read of every record of the session, with the fingerprint of what it read."""
        session = load_agent_session(project_id, session_id)
        header = self._header(session)
        events = self.timeline(session)
        digest = hashlib.sha256()
        digest.update(header.model_dump_json().encode())
        for event in events:
            digest.update(b"\n")
            digest.update(event.model_dump_json().encode())
        return _Snapshot(header=header, events=events, snapshot_id=digest.hexdigest()[:32])

    def _read_snapshot(self, project_id: str, session_id: str) -> _Snapshot:
        """Return two matching projected reads, or 503 if observed changes persist.

        Collections are read sequentially without a transaction. Matching fingerprints do
        not establish an atomic point-in-time snapshot: a value can change and revert
        between reads, for example when a dispatch reservation is released. The fingerprint
        binds pagination to matching projected content, not to an immutable database view.
        """
        previous = self._read_once(project_id, session_id)
        for _ in range(SNAPSHOT_ATTEMPTS - 1):
            current = self._read_once(project_id, session_id)
            if current.snapshot_id == previous.snapshot_id:
                return current
            previous = current
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "The session's records kept changing while its audit was read, so no "
                "consistent snapshot was taken; try again"
            ),
            headers={"Retry-After": "2"},
        )

    def _response(
        self, snapshot: _Snapshot, events: list[AgentAuditEvent], next_cursor: str | None
    ) -> AgentSessionAuditResponse:
        return AgentSessionAuditResponse(
            generated_at=cast("datetime", _utc(now())),
            snapshot_id=snapshot.snapshot_id,
            session=snapshot.header,
            events=events,
            total_events=len(snapshot.events),
            next_cursor=next_cursor,
            complete=next_cursor is None,
            notes=AUDIT_NOTES,
        )

    def read_audit(
        self,
        *,
        project_id: str,
        session_id: str,
        cursor: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
    ) -> AgentSessionAuditResponse:
        """One page of a snapshot of the timeline, oldest first.

        The first page takes a snapshot (see ``_read_snapshot``); its cursor names the
        snapshot and the position after the page. A later page reads the records again and
        is served only when they still fingerprint as that snapshot, so every page of one
        cursor chain comes from the same records. When they changed (a late task result, a
        new decision, a status that moved), the read is refused with 409 and the client
        starts again from the first page; it never receives a page of a different snapshot.
        """
        limit = max(1, min(limit, MAX_PAGE_SIZE))
        if cursor is None:
            snapshot = self._read_snapshot(project_id, session_id)
            offset = 0
        else:
            position = _decode_cursor(cursor)
            if position.project_id != project_id or position.session_id != session_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The audit cursor belongs to another session; read from the first page",
                )
            snapshot = self._read_once(project_id, session_id)
            if snapshot.snapshot_id != position.snapshot_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "The session's audit changed after its first page was read; the pages "
                        "already read belong to an older snapshot. Read it again from the first "
                        "page"
                    ),
                )
            if position.offset >= len(snapshot.events):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid audit cursor"
                )
            offset = position.offset
        end = offset + limit
        page = snapshot.events[offset:end]
        next_cursor = (
            _encode_cursor(_CursorPosition(project_id, session_id, snapshot.snapshot_id, end))
            if end < len(snapshot.events)
            else None
        )
        return self._response(snapshot, page, next_cursor)

    def export_audit(self, *, project_id: str, session_id: str) -> AgentSessionAuditResponse:
        """The whole of one snapshot of the timeline; refused, never cut short, when it
        exceeds the export bound."""
        snapshot = self._read_snapshot(project_id, session_id)
        if len(snapshot.events) > MAX_EXPORT_EVENTS:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(
                    f"The session's audit has {len(snapshot.events)} events, more than one "
                    f"export holds ({MAX_EXPORT_EVENTS}); read it in pages with the audit "
                    "endpoint"
                ),
            )
        return self._response(snapshot, snapshot.events, None)


@dataclass(frozen=True)
class _Snapshot:
    header: AgentAuditSessionHeader
    events: list[AgentAuditEvent]
    snapshot_id: str


@dataclass(frozen=True)
class _CursorPosition:
    project_id: str
    session_id: str
    snapshot_id: str
    offset: int


SortKey = tuple[str, int, int, str]


def _sort_key(event: AgentAuditEvent) -> SortKey:
    """Time, then the session state version (stored times have millisecond precision, so
    records of one millisecond share a time), then cause before effect, then the id."""
    at = cast("datetime", _utc(event.at))
    return (
        at.isoformat(timespec="milliseconds"),
        event.state_version,
        KIND_RANK.get(event.kind, 99),
        event.event_id,
    )


def _encode_cursor(position: _CursorPosition) -> str:
    raw = json.dumps(
        [
            CURSOR_PREFIX,
            position.project_id,
            position.session_id,
            position.snapshot_id,
            position.offset,
        ],
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> _CursorPosition:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        prefix, project_id, session_id, snapshot_id, offset = json.loads(
            base64.urlsafe_b64decode(padded.encode())
        )
        if (
            prefix != CURSOR_PREFIX
            or not all(isinstance(item, str) for item in (project_id, session_id, snapshot_id))
            or not isinstance(offset, int)
            or isinstance(offset, bool)
            or offset < 1
        ):
            raise ValueError("unknown cursor")
        return _CursorPosition(project_id, session_id, snapshot_id, offset)
    except (ValueError, TypeError, binascii.Error, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid audit cursor; read the audit again from the first page",
        ) from exc
