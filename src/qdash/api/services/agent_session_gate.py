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
- Every operation that reaches hardware, the backend, or calibration state first marks its
  own record as reserved, then passes a gate update on the session that matches only an
  ``active`` session, then confirms its reservation. An operation that passed the gate before
  a pause is in flight; one that reaches the gate after a pause is refused and released.
- A resume reads the in-flight records only while the session is paused, so no new
  operation can pass the gate between that read and the resume update.

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
    AgentSessionStatus,
)
from qdash.dbmodel.agent_session import (
    AgentActionDocument,
    AgentCandidateCommitDocument,
    AgentCandidateSetCommitDocument,
    AgentInterventionDocument,
    AgentSessionDocument,
)

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


def expire_session_if_due(doc: AgentSessionDocument, *, at: datetime | None = None) -> None:
    """Expire an active or paused session whose expiry has passed."""
    expires_at = ensure_timezone(doc.expires_at)
    timestamp = at or now()
    if (
        doc.status in {AgentSessionStatus.ACTIVE, AgentSessionStatus.WAITING_FOR_HUMAN}
        and expires_at is not None
        and expires_at <= timestamp
    ):
        AgentSessionDocument.get_motor_collection().update_one(
            {
                "project_id": doc.project_id,
                "session_id": doc.session_id,
                "status": doc.status.value,
            },
            {"$set": {"status": AgentSessionStatus.EXPIRED.value, "updated_at": timestamp}},
        )
        doc.status = AgentSessionStatus.EXPIRED
        doc.updated_at = timestamp


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


def load_agent_session(project_id: str, session_id: str) -> AgentSessionDocument:
    """Load a session, finish a pause a crash left half written, and apply its expiry."""
    doc = AgentSessionDocument.find_one({"project_id": project_id, "session_id": session_id}).run()
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent session '{session_id}' not found",
        )
    materialize_pending_intervention(doc)
    expire_session_if_due(doc)
    return doc


def pass_execution_gate(project_id: str, session_id: str) -> bool:
    """Serialize one operation against the pause; true only while the session is active.

    Call it after the operation's own record is marked as reserved: an operation that passes
    is ordered before any later pause, and its reservation is visible to the resume checks.
    """
    passed = AgentSessionDocument.get_motor_collection().find_one_and_update(
        {
            "project_id": project_id,
            "session_id": session_id,
            "status": AgentSessionStatus.ACTIVE.value,
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


def in_flight_blockers(project_id: str, session_id: str) -> list[str]:
    """Operations that passed the gate and have not settled, as resume blockers."""
    from qdash.api.services.agent_session_service import AgentSessionService

    release_abandoned_reservations(project_id, session_id)
    scope = {"project_id": project_id, "session_id": session_id}
    blockers: list[str] = []
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
        if refreshed.execution_status == "dispatching" and refreshed.operation_id is None:
            blockers.append(
                f"A measurement is still running (action {refreshed.action_id} is being "
                "dispatched; if its request crashed, QDash cannot tell whether it started, "
                "so stop the session instead)"
            )
        else:
            blockers.append(
                f"A measurement is still running (action {refreshed.action_id}); "
                "wait for it to finish"
            )
    for model in (AgentCandidateCommitDocument, AgentCandidateSetCommitDocument):
        commits = model.get_motor_collection().find(
            {**scope, "status": {"$in": list(IN_FLIGHT_COMMIT_STATUSES)}},
            {"commit_id": 1},
        )
        blockers.extend(
            f"A calibration commit is still being saved (commit {commit['commit_id']})"
            for commit in commits
        )
    applies = AgentCandidateCommitDocument.get_motor_collection().find(
        {**scope, "backend_status": {"$in": list(IN_FLIGHT_BACKEND_STATUSES)}},
        {"commit_id": 1},
    )
    blockers.extend(
        f"A backend apply is still in progress (commit {commit['commit_id']})" for commit in applies
    )
    return blockers
