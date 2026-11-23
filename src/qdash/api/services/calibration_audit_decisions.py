"""Decision recording for a calibration session's audit.

Appends a decision to the session's ledger (authorized to the session's creator, idempotent by
key and request hash, bounded per session) after its evidence is validated, and turns stored
decisions into responses with the runs that carry them out and the decision that supersedes
them. Recording a decision changes no session state and grants no execution.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, status

from qdash.api.schemas.calibration_session import CalibrationDecisionResponse
from qdash.api.services.audit_timeline import DecisionLedger, decision_request_hash, json_safe
from qdash.api.services.calibration_audit_evidence import (
    check_conclusion,
    check_evidence_tasks,
    conflict,
    evidence_snapshot,
)
from qdash.api.services.calibration_audit_records import CalibrationAuditRecords, load_session
from qdash.dbmodel.calibration_session import (
    CalibrationConclusion,
    CalibrationDecisionDocument,
    CalibrationExperimentPlan,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from qdash.api.schemas.calibration_session import RecordCalibrationDecisionRequest

# Decisions one calibration session may record, as for an agent session.
MAX_DECISIONS_PER_SESSION = 2000

_LEDGER: DecisionLedger[CalibrationDecisionDocument] = DecisionLedger(
    CalibrationDecisionDocument, limit=MAX_DECISIONS_PER_SESSION, noun="calibration session"
)


def decision_response(
    doc: CalibrationDecisionDocument,
    carried_out_by: Iterable[str] = (),
    superseded_by: str | None = None,
) -> CalibrationDecisionResponse:
    """A stored decision as the API returns it, without ledger internals."""
    data = doc.model_dump(exclude={"id", "request_hash", "quota_slot", "revision_id"})
    return CalibrationDecisionResponse.model_validate(
        {
            **data,
            "carried_out_by_run_ids": list(carried_out_by),
            "superseded_by_decision_id": superseded_by,
        }
    )


def decision_responses(records: CalibrationAuditRecords) -> list[CalibrationDecisionResponse]:
    """Every decision of the session, oldest first, with its runs and its successor."""
    carried: dict[str, list[str]] = defaultdict(list)
    for run in records.runs:
        if run.decision_id:
            carried[run.decision_id].append(run.run_id)
    superseded = {
        d.supersedes_decision_id: d.decision_id
        for d in records.decisions
        if d.supersedes_decision_id
    }
    return [
        decision_response(d, carried.get(d.decision_id, []), superseded.get(d.decision_id))
        for d in records.decisions
    ]


def record_decision(
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
    session = load_session(project_id, calibration_session_id)
    if username != session.created_by:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Only {session.created_by}, who created this calibration session, records "
                "its decisions"
            ),
        )
    request_hash = decision_request_hash(body)
    scope = {"project_id": project_id, "calibration_session_id": calibration_session_id}
    existing = _LEDGER.precheck(scope, body.idempotency_key, request_hash)
    if existing is not None:
        return decision_response(existing)

    records = CalibrationAuditRecords(session)
    runs = {run.run_id: run for run in records.runs}
    decisions = {d.decision_id: d for d in records.decisions}
    run_ids = list(dict.fromkeys(body.evidence_run_ids))
    unknown_runs = [run_id for run_id in run_ids if run_id not in runs]
    if unknown_runs:
        raise conflict(f"Not pipeline runs of this session: {', '.join(unknown_runs)}")
    decision_ids = list(dict.fromkeys(body.evidence_decision_ids))
    referenced = decision_ids + (
        [body.supersedes_decision_id] if body.supersedes_decision_id else []
    )
    unknown_decisions = [d for d in referenced if d not in decisions]
    if unknown_decisions:
        raise conflict(f"Not decisions of this session: {', '.join(unknown_decisions)}")
    task_ids = list(dict.fromkeys(body.evidence_task_ids))
    tasks = check_evidence_tasks(session, task_ids, body.experiment)
    if body.conclusion is not None:
        check_conclusion(body.conclusion, run_ids, decision_ids, runs, decisions)

    fields: dict[str, Any] = {
        "project_id": project_id,
        "calibration_session_id": calibration_session_id,
        "chip_id": session.chip_id,
        "idempotency_key": body.idempotency_key,
        "request_hash": request_hash,
        "recorded_by": username,
        "session_status_at_record": session.status.value,
        "assessment": body.assessment,
        "interpretation": body.interpretation,
        "next_action": body.next_action,
        "next_detail": body.next_detail,
        "evidence_run_ids": run_ids,
        "evidence_task_ids": task_ids,
        "evidence_decision_ids": decision_ids,
        "supersedes_decision_id": body.supersedes_decision_id,
        "experiment": (
            CalibrationExperimentPlan.model_validate(body.experiment.model_dump())
            if body.experiment
            else None
        ),
        "conclusion": (
            CalibrationConclusion.model_validate(body.conclusion.model_dump())
            if body.conclusion
            else None
        ),
        "model": body.model,
        "evidence_snapshot": json_safe(
            evidence_snapshot(records, run_ids, tasks, decision_ids, body.experiment)
        ),
    }
    return decision_response(_LEDGER.insert(scope, fields, request_hash))
