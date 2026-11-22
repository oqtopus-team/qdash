"""Slack start and end messages for agent sessions, delivered from the session record.

The message state lives on the session document: ``start_notification`` is stored with the
new session, and ``end_notification`` by the single status-guarded update that ends it
(``agent_session_gate.end_notification_update``). Delivery reuses the intervention
notifications' channel, bot, toggle, lease, and backoff: an attempt takes a lease on the
record, a sent message is never posted again, and failed attempts are retried by the API's
notification sweeper until ``MAX_AUTOMATIC_DELIVERY_ATTEMPTS`` is used up. A Slack request
that times out after Slack accepted it cannot be told apart from a lost one, so delivery is
at least once: a retry may post a second message for the same event.

A message never changes the session. Failures are recorded on the record and logged as the
error's type and Slack error code only.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal, cast

from pymongo import ReturnDocument

from qdash.api.services.agent_intervention_service import (
    DELIVERY_LEASE,
    MAX_AUTOMATIC_DELIVERY_ATTEMPTS,
    _delivery_backoff,
    _short_error,
)
from qdash.api.services.agent_intervention_slack import (
    AgentInterventionSlackNotifier,
    post_session_event,
)
from qdash.api.services.agent_session_gate import expire_session_if_due
from qdash.common.utils.datetime import now
from qdash.datamodel.agent_session import (
    AgentActionDecision,
    AgentActionType,
    AgentNotificationDelivery,
    AgentNotificationStatus,
    AgentSessionLifecycleEvent,
    AgentSessionNotification,
    AgentSessionStatus,
    model_label,
)
from qdash.dbmodel.agent_session import (
    AgentActionDocument,
    AgentCandidateCommitDocument,
    AgentInterventionDocument,
    AgentSessionDocument,
)
from qdash.dbmodel.project import ProjectDocument

if TYPE_CHECKING:
    from datetime import datetime

logger = logging.getLogger(__name__)

Slot = Literal["start_notification", "end_notification"]
SLOTS: tuple[Slot, ...] = ("start_notification", "end_notification")
OPEN_STATUSES = (AgentSessionStatus.ACTIVE.value, AgentSessionStatus.WAITING_FOR_HUMAN.value)


def initial_start_notification(enabled: bool) -> AgentSessionNotification:
    """The start message state stored with a new session."""
    return AgentSessionNotification(
        event=AgentSessionLifecycleEvent.STARTED,
        status=AgentNotificationStatus.PENDING if enabled else AgentNotificationStatus.DISABLED,
        next_attempt_at=now() if enabled else None,
    )


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value is not None else "-"


class AgentSessionNotificationService:
    """Send the Slack start and end messages of agent sessions."""

    def __init__(self, notifier: AgentInterventionSlackNotifier | None = None) -> None:
        """Initialize with the agent channel notifier the interventions use."""
        self._notifier = notifier or AgentInterventionSlackNotifier()

    @property
    def enabled(self) -> bool:
        """Whether Slack agent notifications are configured."""
        return self._notifier.is_enabled()

    @staticmethod
    def _collection() -> Any:
        return AgentSessionDocument.get_motor_collection()

    def deliver(self, session_id: str, slot: Slot) -> None:
        """Make one attempt at a due message. Never raises."""
        try:
            if slot == "end_notification":
                # Send a pending start first, so the end can reply in its thread.
                self._deliver(session_id, "start_notification")
            self._deliver(session_id, slot)
        except Exception:
            logger.exception("Agent session %s: Slack %s bookkeeping failed", session_id, slot)

    def _deliver(self, session_id: str, slot: Slot) -> None:
        timestamp = now()
        if not self.enabled:
            self._collection().update_one(
                {"session_id": session_id, f"{slot}.status": {"$in": ["pending", "failed"]}},
                {"$set": {f"{slot}.status": AgentNotificationStatus.DISABLED.value}},
            )
            return
        leased = self._collection().find_one_and_update(
            {
                "session_id": session_id,
                "$or": [
                    {
                        f"{slot}.status": "pending",
                        "$or": [
                            {f"{slot}.next_attempt_at": None},
                            {f"{slot}.next_attempt_at": {"$lte": timestamp}},
                        ],
                    },
                    {f"{slot}.status": "sending", f"{slot}.lease_until": {"$lt": timestamp}},
                ],
            },
            {
                "$set": {
                    f"{slot}.status": AgentNotificationStatus.SENDING.value,
                    f"{slot}.lease_until": timestamp + DELIVERY_LEASE,
                    f"{slot}.last_attempt_at": timestamp,
                },
                "$inc": {f"{slot}.attempts": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        if leased is None:
            return
        doc = AgentSessionDocument.find_one({"session_id": session_id}).run()
        notification = getattr(doc, slot) if doc is not None else None
        if doc is None or notification is None:
            return
        if notification.message_ts:
            # A crash after Slack answered but before the record was finished.
            self._finish(session_id, slot, {f"{slot}.status": "sent"})
            return
        project = ProjectDocument.find_by_id(doc.project_id)
        project_name = project.name if project is not None else doc.project_id
        start = doc.start_notification
        thread = (
            (start.channel_id, start.message_ts)
            if slot == "end_notification"
            and start is not None
            and start.channel_id
            and start.message_ts
            else None
        )
        try:
            channel_id, message_ts = post_session_event(
                self._notifier,
                doc,
                notification,
                project_name=project_name,
                facts=self._facts(doc, notification),
                thread=thread,
            )
        except Exception as exc:
            attempts = notification.attempts
            exhausted = attempts >= MAX_AUTOMATIC_DELIVERY_ATTEMPTS
            self._finish(
                session_id,
                slot,
                {
                    f"{slot}.status": "failed" if exhausted else "pending",
                    f"{slot}.last_error": _short_error(exc),
                    f"{slot}.next_attempt_at": (
                        None if exhausted else now() + _delivery_backoff(attempts)
                    ),
                },
            )
            logger.warning(
                "Agent session %s: Slack %s attempt %d failed: %s",
                session_id,
                slot,
                attempts,
                _short_error(exc),
            )
            return
        self._finish(
            session_id,
            slot,
            {
                f"{slot}.status": "sent",
                f"{slot}.channel_id": channel_id,
                f"{slot}.message_ts": message_ts,
                f"{slot}.sent_at": now(),
                f"{slot}.last_error": "",
                f"{slot}.next_attempt_at": None,
            },
        )

    def _finish(self, session_id: str, slot: Slot, fields: dict[str, Any]) -> None:
        self._collection().update_one(
            {"session_id": session_id},
            {"$set": {**fields, f"{slot}.lease_until": None}},
        )

    @staticmethod
    def _facts(
        doc: AgentSessionDocument, notification: AgentNotificationDelivery
    ) -> list[tuple[str, str]]:
        """What the message states, read from QDash's records only."""
        model = model_label(doc.model) or "not reported"
        event = cast("AgentSessionNotification", notification).event
        if event == AgentSessionLifecycleEvent.STARTED:
            return [
                ("Model", model),
                ("Tasks", ", ".join(doc.policy.allowed_tasks)),
                ("Autonomy", doc.policy.autonomy.value),
                ("Client", doc.skill_name or "not reported"),
                ("Expires", _iso(doc.expires_at)),
            ]
        actions = cast(
            "list[AgentActionDocument]",
            AgentActionDocument.find(
                {"session_id": doc.session_id, "decision": AgentActionDecision.AUTHORIZED.value}
            ).run(),
        )
        measurements = sum(
            1 for action in actions if action.action_type == AgentActionType.RUN_TASK
        )
        commits = AgentCandidateCommitDocument.find(
            {"session_id": doc.session_id, "status": "committed"}
        ).count()
        interventions = AgentInterventionDocument.find(
            {"session_id": doc.session_id, "status": {"$ne": "discarded"}}
        ).count()
        actor = cast("AgentSessionNotification", notification).actor
        ended_by = {
            AgentSessionLifecycleEvent.COMPLETED: f"completed by {actor or doc.created_by}",
            AgentSessionLifecycleEvent.CANCELLED: f"stopped by {actor or 'an expert'}",
            AgentSessionLifecycleEvent.EXPIRED: f"expired at {_iso(doc.expires_at)}",
        }.get(event, event.value)
        return [
            ("Model", model),
            ("Status", ended_by),
            ("Measurements", str(measurements)),
            ("Committed updates", str(commits)),
            ("Interventions", str(interventions)),
            ("Actions used", f"{doc.action_count} of {doc.policy.max_actions}"),
        ]

    def sweep(self, *, limit: int = 20) -> int:
        """Expire sessions whose expiry passed and attempt every due lifecycle message.

        The API's notification sweeper calls it, so an expired session is announced even
        when nobody reads it.
        """
        if not self.enabled:
            return 0
        timestamp = now()
        overdue = cast(
            "list[AgentSessionDocument]",
            AgentSessionDocument.find(
                {
                    "status": {"$in": list(OPEN_STATUSES)},
                    "expires_at": {"$lte": timestamp},
                    "start_notification": {"$ne": None},
                },
                limit=limit,
            ).run(),
        )
        for session in overdue:
            expire_session_if_due(session, at=timestamp)
        # Read the due messages after the expiries, which store end messages due now.
        timestamp = now()
        attempted = 0
        for slot in SLOTS:
            due = cast(
                "list[AgentSessionDocument]",
                AgentSessionDocument.find(
                    {
                        "$or": [
                            {
                                f"{slot}.status": "pending",
                                "$or": [
                                    {f"{slot}.next_attempt_at": None},
                                    {f"{slot}.next_attempt_at": {"$lte": timestamp}},
                                ],
                            },
                            {
                                f"{slot}.status": "sending",
                                f"{slot}.lease_until": {"$lt": timestamp},
                            },
                        ]
                    },
                    limit=limit,
                ).run(),
            )
            for session in due:
                self.deliver(session.session_id, slot)
                attempted += 1
        return attempted
