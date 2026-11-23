"""The execution barrier that every agent-session mutation honors.

MongoDB deployments of QDash are standalone servers, so no multi-document transaction is
available. The barrier is therefore built from single-document compare-and-set updates on
the session document, which MongoDB applies one at a time:

- A pause (an intervention, or an authorized ``request_human``) is one update that moves the
  session from ``active`` to ``waiting_for_human``, points it at the intervention, and stores
  the intervention record (and, for ``request_human``, the action record) as a pending
  payload. The separate records are written from that payload afterwards. Any load of the
  session writes a payload that a crash left behind, so a pause never exists without its
  record, and a record never exists without its pause.
- A submitted action is counted (state version and budget) by one update that also stores
  the action record as a pending payload; the record is written from it afterwards, and any
  load of the session writes a payload a crash left behind. A load therefore never returns
  a state version whose action is missing from the action collection, and the checks a
  submission makes on the session's history and its state-version compare-and-set are one
  decision.
- Every operation that reaches hardware, the backend, or calibration state first marks its
  own record as reserved, then passes a gate update on the session that matches only an
  ``active`` session, then confirms its reservation. An operation that passed the gate before
  a pause is in flight; one that reaches the gate after a pause is refused and released.
- A resume reads the in-flight records only while the session is paused, so no new
  operation can pass the gate between that read and the resume update.

A session's end (``completed``, ``cancelled``, ``expired``) is one update guarded by the
session's current status, and that update also stores the pending Slack end message
(``end_notification_update``). Only one end update can match, so a session has one logical
end event, and a crash after the transition leaves a pending delivery, never a lost one.

A session created in a calibration session is written with ``calibration_admission``
``pending``, and every gate update and operational check refuses it until the reservation it
rests on is finalized in the calibration session (``settle_calibration_admission``). The
outcome is read from the calibration session, where finalizing records the reservation in the
same update that removes it, so a crash between that update and the session's own admission
write is recovered by the next load. A session with no admission (created alone) is never
checked.

A reservation that never passed the gate (its request crashed) is released after
``ABANDONED_RESERVATION_TIMEOUT``. A confirmed reservation whose request crashed is never
released automatically, because QDash cannot tell whether the operation started.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any, cast

from fastapi import HTTPException, status
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from qdash.common.utils.datetime import ensure_timezone, now
from qdash.datamodel.agent_session import (
    AgentActionDecision,
    AgentActionType,
    AgentAutonomy,
    AgentNotificationStatus,
    AgentSessionLifecycleEvent,
    AgentSessionNotification,
    AgentSessionStatus,
)
from qdash.datamodel.calibration_session import CalibrationAdmission
from qdash.dbmodel.agent_session import (
    AgentActionDocument,
    AgentCandidateCommitDocument,
    AgentCandidateSetCommitDocument,
    AgentInterventionDocument,
    AgentSessionDocument,
)
from qdash.dbmodel.calibration_session import CalibrationSessionDocument

if TYPE_CHECKING:
    from datetime import datetime

logger = logging.getLogger(__name__)

# A reservation that has not passed the session gate after this long belongs to a crashed
# request and is released.
ABANDONED_RESERVATION_TIMEOUT = timedelta(seconds=60)
# Action states after which no measurement of that action is still running.
SETTLED_EXECUTION_STATUSES = frozenset(
    {"not_started", "completed", "failed", "cancelled", "crashed", "skipped"}
)
IN_FLIGHT_COMMIT_STATUSES = ("reserving", "committing")
IN_FLIGHT_BACKEND_STATUSES = ("dispatching", "queued", "applying")
# Admissions that refuse every operation. A missing field (a session created alone, or
# before admission existed) matches the filter below, so such a session behaves as before.
UNADMITTED = (CalibrationAdmission.PENDING.value, CalibrationAdmission.REJECTED.value)
ADMITTED_FILTER: dict[str, Any] = {"calibration_admission": {"$nin": list(UNADMITTED)}}
OPEN_STATUS_VALUES = (AgentSessionStatus.ACTIVE.value, AgentSessionStatus.WAITING_FOR_HUMAN.value)


def to_bson(value: Any) -> Any:
    """A model dump with enum members replaced by their values, for raw collection writes."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: to_bson(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_bson(item) for item in value]
    return value


def raw_document(doc: Any) -> dict[str, Any]:
    """A Bunnet document as a raw MongoDB document, without its database ids."""
    return cast("dict[str, Any]", to_bson(doc.model_dump(exclude={"id", "revision_id"})))


# ---------------------------------------------------------------------- session loading


def end_notification_update(
    doc: AgentSessionDocument, event: AgentSessionLifecycleEvent, *, actor: str = ""
) -> dict[str, Any]:
    """The ``$set`` fields that store a session's end message with the update that ends it.

    A session created before lifecycle messages existed gets none. The end message is pending
    when the start message was meant to be sent, and disabled when it was not, so a session
    never announces only its end.
    """
    start = doc.start_notification
    if start is None:
        return {}
    enabled = start.status != AgentNotificationStatus.DISABLED
    notification = AgentSessionNotification(
        event=event,
        actor=actor,
        status=AgentNotificationStatus.PENDING if enabled else AgentNotificationStatus.DISABLED,
        next_attempt_at=now() if enabled else None,
    )
    return {"end_notification": to_bson(notification.model_dump())}


def expire_session_if_due(doc: AgentSessionDocument, *, at: datetime | None = None) -> bool:
    """Expire an active or paused session whose expiry has passed.

    Returns whether this call made the transition; a concurrent one that won leaves False.
    """
    expires_at = ensure_timezone(doc.expires_at)
    timestamp = at or now()
    if (
        doc.status in {AgentSessionStatus.ACTIVE, AgentSessionStatus.WAITING_FOR_HUMAN}
        and expires_at is not None
        and expires_at <= timestamp
    ):
        ending = end_notification_update(doc, AgentSessionLifecycleEvent.EXPIRED)
        result = AgentSessionDocument.get_motor_collection().update_one(
            {
                "project_id": doc.project_id,
                "session_id": doc.session_id,
                "status": doc.status.value,
            },
            {
                "$set": {
                    "status": AgentSessionStatus.EXPIRED.value,
                    "updated_at": timestamp,
                    **ending,
                }
            },
        )
        if result.modified_count != 1:
            # Another update changed the session first; read what it stored.
            fresh = AgentSessionDocument.find_one(
                {"project_id": doc.project_id, "session_id": doc.session_id}
            ).run()
            if fresh is not None:
                doc.status = fresh.status
                doc.updated_at = fresh.updated_at
                doc.end_notification = fresh.end_notification
            return False
        doc.status = AgentSessionStatus.EXPIRED
        doc.updated_at = timestamp
        if ending:
            doc.end_notification = AgentSessionNotification.model_validate(
                ending["end_notification"]
            )
        return True
    return False


def materialize_pending_intervention(doc: AgentSessionDocument) -> None:
    """Write the records of a pause from the payload the pausing update stored.

    Idempotent: each record is inserted only if it does not exist yet, and the payload is
    cleared only while it still names the same intervention.
    """
    pending = doc.pending_intervention
    if not pending:
        return
    intervention_id = _write_pending_records(doc.session_id, pending)
    if intervention_id is None:
        return
    _clear_pending(doc, intervention_id)


def _write_pending_records(session_id: str, pending: dict[str, Any]) -> str | None:
    """Insert the pending records that do not exist yet; the intervention id on success."""
    intervention = pending.get("intervention") or {}
    intervention_id = intervention.get("intervention_id")
    if not intervention_id:
        logger.error("Agent session %s has a pending pause without a record", session_id)
        return None
    try:
        AgentInterventionDocument.get_motor_collection().update_one(
            {"intervention_id": intervention_id},
            {"$setOnInsert": intervention},
            upsert=True,
        )
        action = pending.get("action")
        if action:
            AgentActionDocument.get_motor_collection().update_one(
                {"action_id": action["action_id"]},
                {"$setOnInsert": action},
                upsert=True,
            )
    except DuplicateKeyError:
        # Another record already uses the idempotency key; keep the payload for inspection.
        logger.exception(
            "Agent session %s: pending intervention %s conflicts with an existing record",
            session_id,
            intervention_id,
        )
        return None
    return cast("str", intervention_id)


def _clear_pending(doc: AgentSessionDocument, intervention_id: str) -> None:
    AgentSessionDocument.get_motor_collection().update_one(
        {
            "project_id": doc.project_id,
            "session_id": doc.session_id,
            "pending_intervention.intervention.intervention_id": intervention_id,
        },
        {"$set": {"pending_intervention": None}},
    )
    doc.pending_intervention = None


def materialize_pending_action(doc: AgentSessionDocument) -> None:
    """Write the action record the counting update stored, then clear the payload.

    Idempotent: the record is inserted only if it does not exist yet, and the payload is
    cleared only while it still names the same action. A record that conflicts with an
    existing one keeps the payload, and ``AgentSessionService.submit_action`` refuses new
    submissions until it is resolved.
    """
    pending = doc.pending_action
    if not pending:
        return
    action_id = pending.get("action_id")
    if not action_id:
        logger.error("Agent session %s has a pending action without an id", doc.session_id)
        return
    try:
        AgentActionDocument.get_motor_collection().update_one(
            {"action_id": action_id},
            {"$setOnInsert": pending},
            upsert=True,
        )
    except DuplicateKeyError:
        logger.exception(
            "Agent session %s: pending action %s conflicts with an existing record",
            doc.session_id,
            action_id,
        )
        return
    AgentSessionDocument.get_motor_collection().update_one(
        {
            "project_id": doc.project_id,
            "session_id": doc.session_id,
            "pending_action.action_id": action_id,
        },
        {"$set": {"pending_action": None}},
    )
    doc.pending_action = None


# ---------------------------------------------------------------------- calibration admission


def admit_calibration_child(doc: AgentSessionDocument) -> None:
    """Record that the session's reservation was finalized; only from ``pending``."""
    timestamp = now()
    AgentSessionDocument.get_motor_collection().update_one(
        {
            "project_id": doc.project_id,
            "session_id": doc.session_id,
            "calibration_admission": CalibrationAdmission.PENDING.value,
        },
        {"$set": {"calibration_admission": CalibrationAdmission.ADMITTED.value}},
    )
    _reread_admission(doc, timestamp)


def reject_calibration_child(doc: AgentSessionDocument, *, actor: str = "") -> None:
    """Reject a session whose reservation was cleared without being finalized.

    Only from ``pending``. An open session is cancelled by the same update, with its end
    message; one that already ended keeps its status. Either way it never operates.
    """
    timestamp = now()
    collection = AgentSessionDocument.get_motor_collection()
    scope = {
        "project_id": doc.project_id,
        "session_id": doc.session_id,
        "calibration_admission": CalibrationAdmission.PENDING.value,
    }
    collection.update_one(
        {**scope, "status": {"$in": list(OPEN_STATUS_VALUES)}},
        {
            "$set": {
                "calibration_admission": CalibrationAdmission.REJECTED.value,
                "status": AgentSessionStatus.CANCELLED.value,
                "active_intervention_id": None,
                "updated_at": timestamp,
                **end_notification_update(doc, AgentSessionLifecycleEvent.CANCELLED, actor=actor),
            }
        },
    )
    collection.update_one(
        scope,
        {"$set": {"calibration_admission": CalibrationAdmission.REJECTED.value}},
    )
    _reread_admission(doc, timestamp)


def _reread_admission(doc: AgentSessionDocument, timestamp: datetime) -> None:
    fresh = AgentSessionDocument.find_one(
        {"project_id": doc.project_id, "session_id": doc.session_id}
    ).run()
    if fresh is None:
        return
    doc.calibration_admission = fresh.calibration_admission
    doc.status = fresh.status
    doc.active_intervention_id = fresh.active_intervention_id
    doc.end_notification = fresh.end_notification
    doc.updated_at = fresh.updated_at or timestamp


def settle_calibration_admission(doc: AgentSessionDocument) -> None:
    """Decide a ``pending`` admission from the reservation's outcome in the calibration session.

    Finalizing a reservation removes it and lists it in ``admitted_reservation_ids`` in one
    update, and a close clears it without listing it. So a reservation that is listed was
    finalized (the session is admitted), one that is still pending stays undecided, and one
    that is neither was cleared and can never be finalized (the session is rejected). A
    calibration session that cannot be read leaves the admission pending, which refuses every
    operation.
    """
    if doc.calibration_admission != CalibrationAdmission.PENDING:
        return
    reservation_id = doc.calibration_reservation_id
    if not reservation_id or not doc.calibration_session_id:
        return
    parent = CalibrationSessionDocument.find_one(
        {"project_id": doc.project_id, "calibration_session_id": doc.calibration_session_id}
    ).run()
    if parent is None:
        return
    if reservation_id in parent.admitted_reservation_ids:
        admit_calibration_child(doc)
    elif all(r.reservation_id != reservation_id for r in parent.pending_children):
        reject_calibration_child(doc)


def admission_refusal(session: AgentSessionDocument) -> None:
    """Refuse an operation of a session whose calibration admission is not granted.

    Call it, with the status check, wherever an operation is admitted; the gate updates repeat
    it with ``ADMITTED_FILTER``. A session with no admission passes.
    """
    admission = session.calibration_admission
    if admission == CalibrationAdmission.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Agent session {session.session_id} is not admitted yet: its start in "
                f"calibration session {session.calibration_session_id} has not been "
                "finalized, so it cannot operate. Retry after its creation returns."
            ),
        )
    if admission == CalibrationAdmission.REJECTED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Agent session {session.session_id} was rejected: calibration session "
                f"{session.calibration_session_id} was closed before its start was "
                "finalized, so it never operates. Start a new calibration session."
            ),
        )


def load_agent_session(project_id: str, session_id: str) -> AgentSessionDocument:
    """Load a session, finish records a crash left half written, and apply its expiry.

    A ``pending`` calibration admission is decided first, from the calibration session.
    """
    doc = AgentSessionDocument.find_one({"project_id": project_id, "session_id": session_id}).run()
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent session '{session_id}' not found",
        )
    settle_calibration_admission(doc)
    materialize_pending_action(doc)
    materialize_pending_intervention(doc)
    expire_session_if_due(doc)
    return doc


def autonomous_session_refusal(session: AgentSessionDocument, username: str) -> None:
    """Refuse an autonomous request unless the signed-in user approved this ``auto`` session.

    An autonomous request runs without a per-call approval, so it relies on the approval the
    session's creator gave once. ``username`` is the authenticated user of the request, never
    a value the agent supplies; an empty one is refused.
    """
    if not username or username != session.created_by:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Autonomous steps run only in an agent session the signed-in user created; "
                f"this session belongs to {session.created_by}. Use the reviewed tools, "
                "approved per call, or a session you approve."
            ),
        )
    if session.policy.autonomy != AgentAutonomy.AUTO:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The session was approved with autonomy "
                f"{session.policy.autonomy.value}; autonomous steps need autonomy auto"
            ),
        )


def pass_execution_gate(project_id: str, session_id: str) -> bool:
    """Serialize one operation against the pause; true only while the session is active.

    A session whose calibration admission is ``pending`` or ``rejected`` never passes.

    Call it after the operation's own record is marked as reserved: an operation that passes
    is ordered before any later pause, and its reservation is visible to the resume checks.
    """
    passed = AgentSessionDocument.get_motor_collection().find_one_and_update(
        {
            "project_id": project_id,
            "session_id": session_id,
            "status": AgentSessionStatus.ACTIVE.value,
            **ADMITTED_FILTER,
        },
        {"$set": {"execution_gate_at": now()}},
        return_document=ReturnDocument.AFTER,
    )
    return passed is not None


# ---------------------------------------------------------------------- abandoned reservations


def release_abandoned_reservations(
    project_id: str, session_id: str, *, at: datetime | None = None
) -> None:
    """Release reservations whose request crashed before passing the session gate.

    Each release is a compare-and-set on the unconfirmed reservation, so a slow request
    that later tries to confirm it fails instead of running.
    """
    cutoff = (at or now()) - ABANDONED_RESERVATION_TIMEOUT
    scope = {"project_id": project_id, "session_id": session_id}
    AgentActionDocument.get_motor_collection().update_many(
        {
            **scope,
            "execution_status": "dispatching",
            "dispatch_confirmed": False,
            "dispatch_reserved_at": {"$lt": cutoff},
        },
        {
            "$set": {
                "execution_status": "not_started",
                "dispatch_token": None,
                "dispatch_confirmed": None,
                "dispatch_reserved_at": None,
            }
        },
    )
    AgentCandidateCommitDocument.get_motor_collection().update_many(
        {
            **scope,
            "backend_status": "dispatching",
            "backend_dispatch_confirmed": False,
            "backend_requested_at": {"$lt": cutoff},
        },
        {
            "$set": {
                "backend_status": "failed",
                "backend_error": "The apply request stopped before it was dispatched",
                "backend_apply_idempotency_key": None,
                "backend_apply_request_hash": None,
                "backend_dispatch_token": None,
                "backend_dispatch_confirmed": None,
            }
        },
    )
    for model in (AgentCandidateCommitDocument, AgentCandidateSetCommitDocument):
        model.get_motor_collection().update_many(
            {**scope, "status": "reserving", "created_at": {"$lt": cutoff}},
            {
                "$set": {
                    "status": "failed",
                    "reason": "The commit request stopped before it was reserved; "
                    "nothing was persisted",
                }
            },
        )


def in_flight_operations(project_id: str, session_id: str) -> list[dict[str, Any]]:
    """Operations of the session that passed, or may still pass, the gate and have not settled.

    Each is ``{"kind", "id", "status", "execution_id", "operation_id"}``. A measurement
    still ``dispatching`` may have passed the gate just before a pause or an end and not
    confirmed yet, so it is listed: whether it starts is not known until it settles.
    """
    from qdash.api.services.agent_session_service import AgentSessionService

    release_abandoned_reservations(project_id, session_id)
    scope = {"project_id": project_id, "session_id": session_id}
    operations: list[dict[str, Any]] = []
    actions = cast(
        "list[AgentActionDocument]",
        AgentActionDocument.find(
            {
                **scope,
                "action_type": AgentActionType.RUN_TASK.value,
                "decision": AgentActionDecision.AUTHORIZED.value,
                "execution_status": {"$nin": sorted(SETTLED_EXECUTION_STATUSES)},
            }
        ).run(),
    )
    for action in actions:
        refreshed = AgentSessionService._refresh_action_execution(action)
        if refreshed.execution_status in SETTLED_EXECUTION_STATUSES:
            continue
        operations.append(
            {
                "kind": "measurement",
                "id": refreshed.action_id,
                "status": refreshed.execution_status,
                "execution_id": refreshed.execution_id,
                "operation_id": refreshed.operation_id,
            }
        )
    for kind, model in (
        ("candidate_commit", AgentCandidateCommitDocument),
        ("candidate_set_commit", AgentCandidateSetCommitDocument),
    ):
        commits = model.get_motor_collection().find(
            {**scope, "status": {"$in": list(IN_FLIGHT_COMMIT_STATUSES)}},
            {"commit_id": 1, "status": 1},
        )
        operations.extend(
            {
                "kind": kind,
                "id": commit["commit_id"],
                "status": commit["status"],
                "execution_id": None,
                "operation_id": None,
            }
            for commit in commits
        )
    applies = AgentCandidateCommitDocument.get_motor_collection().find(
        {**scope, "backend_status": {"$in": list(IN_FLIGHT_BACKEND_STATUSES)}},
        {"commit_id": 1, "backend_status": 1},
    )
    operations.extend(
        {
            "kind": "backend_apply",
            "id": commit["commit_id"],
            "status": commit["backend_status"],
            "execution_id": None,
            "operation_id": None,
        }
        for commit in applies
    )
    return operations


def in_flight_blockers(project_id: str, session_id: str) -> list[str]:
    """Operations that passed the gate and have not settled, as resume blockers."""
    blockers: list[str] = []
    for operation in in_flight_operations(project_id, session_id):
        kind, operation_id = operation["kind"], operation["id"]
        if kind == "measurement":
            if operation["status"] == "dispatching" and operation["operation_id"] is None:
                blockers.append(
                    f"A measurement is still running (action {operation_id} is being "
                    "dispatched; if its request crashed, QDash cannot tell whether it started, "
                    "so stop the session instead)"
                )
            else:
                blockers.append(
                    f"A measurement is still running (action {operation_id}); wait for it to finish"
                )
        elif kind == "backend_apply":
            blockers.append(f"A backend apply is still in progress (commit {operation_id})")
        else:
            blockers.append(f"A calibration commit is still being saved (commit {operation_id})")
    return blockers
