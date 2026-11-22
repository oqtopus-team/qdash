"""Slack start and end messages of agent sessions, sent to a fake Slack client."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from qdash.api.schemas.agent_session import (
    CreateAgentSessionRequest,
    RespondAgentInterventionRequest,
    SubmitAgentActionRequest,
)
from qdash.api.services.agent_intervention_service import (
    MAX_AUTOMATIC_DELIVERY_ATTEMPTS,
    AgentInterventionService,
)
from qdash.api.services.agent_intervention_slack import AgentInterventionSlackNotifier
from qdash.api.services.agent_session_gate import expire_session_if_due
from qdash.api.services.agent_session_notifications import AgentSessionNotificationService
from qdash.api.services.agent_session_service import AgentSessionService
from qdash.common.utils.datetime import now
from qdash.config import get_settings
from qdash.datamodel.agent_session import (
    AgentActionType,
    AgentInterventionDecision,
    AgentModelIdentity,
    AgentSessionNotification,
    AgentSessionPolicy,
    AgentSessionStatus,
)
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.agent_session import AgentSessionDocument
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.project import ProjectDocument

PROJECT = "project-1"
OWNER = "owner"


class FakeSlack:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.failures = 0

    def chat_postMessage(self, *, channel: str, **kwargs: Any) -> dict[str, str]:
        if self.failures:
            self.failures -= 1
            error = RuntimeError("POST https://slack.com/api?token=xoxb-secret failed")
            error.response = {"error": "ratelimited"}  # type: ignore[attr-defined]
            raise error
        self.calls.append({"channel": channel, **kwargs})
        return {"channel": channel, "ts": f"{len(self.calls)}.000"}


def _services(slack: FakeSlack | None, *, enabled: bool = True) -> AgentSessionService:
    settings = get_settings().model_copy(
        update={
            "slack_bot_token": "xoxb-test" if enabled else "",
            "slack_agent_notification": enabled,
            "slack_agent_channel_id": "C-agent" if enabled else "",
            "client_url": "https://qdash.example",
        }
    )
    notifier = AgentInterventionSlackNotifier(settings=settings, client=slack)
    return AgentSessionService(intervention_service=AgentInterventionService(notifier=notifier))


@pytest.fixture
def chip(init_db) -> None:
    ProjectDocument(
        project_id=PROJECT, name="Lab <A> *bold*", owner_user_id="u", owner_username=OWNER
    ).insert()
    ChipDocument(
        project_id=PROJECT,
        chip_id="chip-001",
        username=OWNER,
        size=4,
        system_info=SystemInfoModel(),
    ).insert()


def _create(service: AgentSessionService, *, expires: int = 3600) -> str:
    return service.create_session(
        project_id=PROJECT,
        username=OWNER,
        body=CreateAgentSessionRequest(
            chip_id="chip-001",
            policy=AgentSessionPolicy(qids=["Q00"], allowed_tasks=["CheckRabi"]),
            expires_in_seconds=expires,
            skill_name="pi-qdash",
            model=AgentModelIdentity(provider="vllm", model_id="qwen3"),
        ),
    ).session_id


def _session(session_id: str) -> AgentSessionDocument:
    doc = AgentSessionDocument.find_one({"session_id": session_id}).run()
    assert doc is not None
    return doc


def _sent(notification: AgentSessionNotification | None) -> AgentSessionNotification:
    assert notification is not None
    return notification


def _submit(service: AgentSessionService, session_id: str, action: AgentActionType) -> None:
    service.submit_action(
        project_id=PROJECT,
        session_id=session_id,
        username=OWNER,
        body=SubmitAgentActionRequest(
            idempotency_key=f"{action.value}-{_session(session_id).state_version}",
            expected_state_version=_session(session_id).state_version,
            action_type=action,
            diagnosis="ask" if action == AgentActionType.REQUEST_HUMAN else "",
        ),
    )


def _texts(call: dict[str, Any]) -> list[str]:
    return [
        field["text"]
        for block in call["attachments"][0]["blocks"]
        for field in block.get("fields", [])
    ]


def test_start_is_stored_with_the_session_and_sent_once(chip: None) -> None:
    slack = FakeSlack()
    service = _services(slack)
    session_id = _create(service)
    assert _sent(_session(session_id).start_notification).status == "pending"

    service.notifications.deliver(session_id, "start_notification")
    service.notifications.deliver(session_id, "start_notification")
    assert service.notifications.sweep() == 0

    assert len(slack.calls) == 1
    call = slack.calls[0]
    assert call["channel"] == "C-agent"
    assert "thread_ts" not in call
    texts = _texts(call)
    assert "Project: Lab <A> *bold*" in texts
    assert "Targets: Q00" in texts
    assert "Created by: owner" in texts
    assert "Model: vllm/qwen3" in texts
    assert "Client: pi-qdash" in texts
    # Recorded values are plain text; only the static title and the links are mrkdwn.
    fields = [f for b in call["attachments"][0]["blocks"] for f in b.get("fields", [])]
    assert {field["type"] for field in fields} == {"plain_text"}
    title = call["attachments"][0]["blocks"][0]["text"]["text"]
    assert f"https://qdash.example/agent-sessions/{session_id}?project=project-1" in title
    assert f"https://qdash.example/execution/chip-001/sessions/{session_id}?project=project-1" in (
        title
    )
    stored = _sent(_session(session_id).start_notification)
    assert (stored.status, stored.message_ts, stored.attempts) == ("sent", "1.000", 1)


def test_completion_stores_one_end_event_and_replies_in_the_start_thread(chip: None) -> None:
    slack = FakeSlack()
    service = _services(slack)
    session_id = _create(service)
    service.notifications.deliver(session_id, "start_notification")
    _submit(service, session_id, AgentActionType.COMPLETE_SESSION)

    end = _sent(_session(session_id).end_notification)
    assert (end.event, end.actor, end.status) == ("completed", OWNER, "pending")
    service.notifications.deliver(session_id, "end_notification")
    service.notifications.sweep()

    assert len(slack.calls) == 2
    reply = slack.calls[1]
    assert (reply["thread_ts"], reply["reply_broadcast"]) == ("1.000", True)
    assert reply["text"].startswith("Agent session completed")
    texts = _texts(reply)
    assert "Status: completed by owner" in texts
    assert "Measurements: 0" in texts
    assert "Committed updates: 0" in texts
    # A completed session cannot expire into a second end event.
    doc = _session(session_id)
    assert expire_session_if_due(doc, at=now() + timedelta(days=2)) is False
    assert _sent(_session(session_id).end_notification).event == "completed"


def test_a_pause_is_not_an_end_and_an_expert_stop_is_a_cancel(chip: None) -> None:
    slack = FakeSlack()
    service = _services(slack)
    session_id = _create(service)
    _submit(service, session_id, AgentActionType.REQUEST_HUMAN)
    paused = _session(session_id)
    assert paused.status == "waiting_for_human"
    assert paused.end_notification is None

    service.interventions.respond(
        project_id=PROJECT,
        session_id=session_id,
        intervention_id=paused.active_intervention_id or "",
        username="expert",
        body=RespondAgentInterventionRequest(
            idempotency_key="stop",
            expected_state_version=paused.state_version,
            decision=AgentInterventionDecision.STOP,
        ),
    )
    end = _sent(_session(session_id).end_notification)
    assert (end.event, end.actor) == ("cancelled", "expert")
    service.notifications.deliver(session_id, "end_notification")
    lifecycle = [c for c in slack.calls if c["text"].startswith("Agent session ")]
    # The pending start goes first, then the end replies in its thread.
    assert [c["text"].split(":")[0] for c in lifecycle] == [
        "Agent session started",
        "Agent session cancelled",
    ]
    assert "Status: stopped by expert" in _texts(lifecycle[1])


def test_the_sweeper_expires_an_unread_session_and_announces_it_once(chip: None) -> None:
    slack = FakeSlack()
    service = _services(slack)
    session_id = _create(service, expires=60)
    service.notifications.deliver(session_id, "start_notification")
    AgentSessionDocument.get_motor_collection().update_one(
        {"session_id": session_id}, {"$set": {"expires_at": now() - timedelta(seconds=1)}}
    )

    assert service.notifications.sweep() == 1
    assert service.notifications.sweep() == 0
    doc = _session(session_id)
    assert doc.status == "expired"
    assert (_sent(doc.end_notification).event, _sent(doc.end_notification).status) == (
        "expired",
        "sent",
    )
    assert [c["text"].split(":")[0] for c in slack.calls] == [
        "Agent session started",
        "Agent session expired",
    ]
    # A racing loader that read the session before the expiry cannot add a second event.
    stale = doc.model_copy(update={"status": AgentSessionStatus.ACTIVE})
    assert expire_session_if_due(stale) is False


def test_failed_attempts_back_off_keep_no_error_text_and_end_failed(chip: None) -> None:
    slack = FakeSlack()
    slack.failures = MAX_AUTOMATIC_DELIVERY_ATTEMPTS + 1
    service = _services(slack)
    session_id = _create(service)

    service.notifications.deliver(session_id, "start_notification")
    start = _sent(_session(session_id).start_notification)
    assert (start.status, start.attempts) == ("pending", 1)
    assert start.last_error == "RuntimeError: ratelimited"
    assert start.next_attempt_at is not None
    # The session itself is unaffected by the failed message.
    assert _session(session_id).status == "active"

    for _ in range(MAX_AUTOMATIC_DELIVERY_ATTEMPTS):
        AgentSessionDocument.get_motor_collection().update_one(
            {"session_id": session_id}, {"$set": {"start_notification.next_attempt_at": None}}
        )
        service.notifications.deliver(session_id, "start_notification")
    start = _sent(_session(session_id).start_notification)
    assert (start.status, start.attempts, start.next_attempt_at) == (
        "failed",
        MAX_AUTOMATIC_DELIVERY_ATTEMPTS,
        None,
    )
    assert slack.calls == []


def test_a_crash_after_the_transition_or_after_slack_answered_is_finished_once(
    chip: None,
) -> None:
    slack = FakeSlack()
    service = _services(slack)
    session_id = _create(service)
    # A crash left the start leased with Slack's answer already recorded: no second post.
    AgentSessionDocument.get_motor_collection().update_one(
        {"session_id": session_id},
        {
            "$set": {
                "start_notification.status": "sending",
                "start_notification.lease_until": now() - timedelta(seconds=1),
                "start_notification.message_ts": "9.000",
                "start_notification.channel_id": "C-agent",
            }
        },
    )
    # The request that completed the session crashed before it sent the end message.
    _submit(service, session_id, AgentActionType.COMPLETE_SESSION)

    service.notifications.sweep()
    assert len(slack.calls) == 1
    assert slack.calls[0]["thread_ts"] == "9.000"
    doc = _session(session_id)
    assert (_sent(doc.start_notification).status, _sent(doc.end_notification).status) == (
        "sent",
        "sent",
    )


def test_disabled_by_default_sends_nothing_and_records_disabled(chip: None) -> None:
    slack = FakeSlack()
    service = _services(slack, enabled=False)
    session_id = _create(service)
    _submit(service, session_id, AgentActionType.COMPLETE_SESSION)
    service.notifications.deliver(session_id, "end_notification")

    doc = _session(session_id)
    assert (_sent(doc.start_notification).status, _sent(doc.end_notification).status) == (
        "disabled",
        "disabled",
    )
    assert AgentSessionNotificationService(service.interventions.notifier).sweep() == 0
    assert slack.calls == []


def test_a_session_created_before_lifecycle_messages_gets_no_end_message(chip: None) -> None:
    slack = FakeSlack()
    service = _services(slack)
    session_id = _create(service)
    AgentSessionDocument.get_motor_collection().update_one(
        {"session_id": session_id}, {"$set": {"start_notification": None}}
    )
    _submit(service, session_id, AgentActionType.COMPLETE_SESSION)

    assert _session(session_id).end_notification is None
    service.notifications.sweep()
    assert slack.calls == []
