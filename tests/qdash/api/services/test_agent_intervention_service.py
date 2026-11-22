"""Tests for durable agent interventions: pause, Slack delivery, expert response, and resume."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from fastapi import HTTPException

from qdash.api.schemas.agent_session import (
    AgentActionResponse,
    ClaimAgentResumeRequest,
    CreateAgentInterventionRequest,
    CreateAgentSessionRequest,
    RecordAgentResumeOutcomeRequest,
    RespondAgentInterventionRequest,
    SubmitAgentActionRequest,
)
from qdash.api.services.agent_intervention_service import AgentInterventionService
from qdash.api.services.agent_intervention_slack import AgentInterventionSlackNotifier
from qdash.api.services.agent_session_service import AgentSessionService
from qdash.common.utils.datetime import now
from qdash.config import get_settings
from qdash.datamodel.agent_session import (
    AgentActionType,
    AgentSessionPolicy,
    NumericBounds,
)
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.agent_session import (
    AgentActionDocument,
    AgentInterventionDocument,
    AgentSessionDocument,
)
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

PROJECT = "project-1"


class FakeSlack:
    """Records chat.postMessage calls; fails while ``failures`` is positive."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.failures = 0

    def chat_postMessage(self, *, channel: str, **kwargs: Any) -> dict[str, str]:
        kwargs["channel"] = channel
        self.calls.append(kwargs)
        if self.failures > 0:
            self.failures -= 1
            raise ConnectionError("slack unreachable")
        return {"channel": kwargs["channel"], "ts": f"{len(self.calls)}.000"}


def _notifier(slack: FakeSlack, *, enabled: bool = True) -> AgentInterventionSlackNotifier:
    settings = get_settings().model_copy(
        update={
            "slack_bot_token": "xoxb-test",
            "slack_agent_notification": enabled,
            "slack_agent_channel_id": "C-agent" if enabled else "",
            "slack_forum_channel_id": "C-forum",
        }
    )
    return AgentInterventionSlackNotifier(settings=settings, client=slack)


@pytest.fixture
def slack() -> FakeSlack:
    return FakeSlack()


@pytest.fixture
def interventions(init_db, slack: FakeSlack) -> AgentInterventionService:
    ChipDocument(
        project_id=PROJECT,
        chip_id="chip-001",
        username="tester",
        size=4,
        system_info=SystemInfoModel(),
    ).insert()
    ProjectDocument(
        project_id=PROJECT, name="Lab A", owner_user_id="u-1", owner_username="tester"
    ).insert()
    return AgentInterventionService(notifier=_notifier(slack))


@pytest.fixture
def sessions(interventions: AgentInterventionService) -> AgentSessionService:
    return AgentSessionService(intervention_service=interventions)


def _session(sessions: AgentSessionService, *, max_actions: int = 10, expires: int = 3600):
    return sessions.create_session(
        project_id=PROJECT,
        username="tester",
        body=CreateAgentSessionRequest(
            chip_id="chip-001",
            policy=AgentSessionPolicy(
                qids=["Q00"],
                allowed_tasks=["CheckRabi", "CheckChevron"],
                allowed_overrides={"control_amplitude": NumericBounds(minimum=0.0, maximum=1.0)},
                max_actions=max_actions,
            ),
            expires_in_seconds=expires,
        ),
    )


# The action key of the first visit of plan node 0 ("rabi") under prefix "plan-1".
RABI_KEY = "plan-1-node-0-action"


def _run_task(
    sessions: AgentSessionService, session_id: str, key: str = RABI_KEY
) -> AgentActionResponse:
    version = sessions.get_session(project_id=PROJECT, session_id=session_id).state_version
    return sessions.submit_action(
        project_id=PROJECT,
        session_id=session_id,
        body=SubmitAgentActionRequest(
            idempotency_key=key,
            expected_state_version=version,
            action_type=AgentActionType.RUN_TASK,
            task_name="CheckRabi",
            qids=["Q00"],
        ),
    )


def _completed_run(
    sessions: AgentSessionService, session_id: str, key: str = RABI_KEY, ref: str = "a-1"
) -> str:
    """A run_task action whose measurement finished, with its execution and task result."""
    action = _run_task(sessions, session_id, key)
    key = ref
    doc = AgentActionDocument.find_one({"action_id": action.action_id}).run()
    assert doc is not None
    doc.execution_status = "completed"
    doc.execution_id = f"exec-{key}"
    doc.save()
    ExecutionHistoryDocument(
        project_id=PROJECT,
        username="tester",
        name="agent:CheckRabi",
        execution_id=f"exec-{key}",
        calib_data_path="",
        note={},
        status="completed",
        tags=[],
        chip_id="chip-001",
        start_at=now(),
        end_at=now(),
        elapsed_time=1.0,
        message="",
        system_info=SystemInfoModel(),
    ).insert()
    TaskResultHistoryDocument(
        project_id=PROJECT,
        username="tester",
        task_id=f"task-{key}",
        name="CheckRabi",
        upstream_id="",
        status="completed",
        message="",
        input_parameters={},
        output_parameters={},
        output_parameter_names=[],
        run_parameters={},
        note={},
        figure_path=[],
        json_figure_path=[],
        raw_data_path=[],
        start_at=None,
        end_at=None,
        elapsed_time=None,
        task_type="qubit",
        system_info=SystemInfoModel(),
        qid="Q00",
        execution_id=f"exec-{key}",
        tags=[],
        chip_id="chip-001",
    ).insert()
    return action.action_id


def _checkpoint(**overrides: Any) -> dict[str, Any]:
    checkpoint = {
        "qid": "Q00",
        "nodes": [
            {"id": "rabi", "task_name": "CheckRabi", "candidate_parameter": "control_amplitude"},
            {
                "id": "chevron",
                "task_name": "CheckChevron",
                "candidate_parameter": "qubit_frequency",
                "on_pass": "rabi",
            },
        ],
        "idempotency_prefix": "plan-1",
        "node_path": ["rabi"],
        "visit_counts": {"rabi": 1},
        "stopped_node_id": "rabi",
        "max_node_executions": 4,
        "max_node_visits": 2,
    }
    checkpoint.update(overrides)
    return checkpoint


def _request(action_id: str | None = None, key: str = "int-1", **overrides: Any):
    body: dict[str, Any] = {
        "idempotency_key": key,
        "reason": "unknown_outcome",
        "summary": "CheckRabi evaluation reported LOW_CONTRAST, which has no next action",
        "question": "Is the Rabi oscillation usable, or should the plan stop?",
        "node_id": "rabi",
        "task_name": "CheckRabi",
        "qids": ["Q00"],
        "attempts": (
            [
                {
                    "node_id": "rabi",
                    "task_name": "CheckRabi",
                    "qid": "Q00",
                    "transition": "pass",
                    "status": "LOW_CONTRAST",
                    "action_id": action_id,
                    "execution_id": "exec-a-1",
                    "task_id": "task-a-1",
                }
            ]
            if action_id
            else []
        ),
        "checkpoint": _checkpoint(),
    }
    body.update(overrides)
    return CreateAgentInterventionRequest.model_validate(body)


def _create(interventions: AgentInterventionService, session_id: str, body=None):
    response = interventions.create_intervention(
        project_id=PROJECT, session_id=session_id, username="tester", body=body
    )
    interventions.deliver_notification(response.intervention_id)
    return interventions.get_intervention(
        project_id=PROJECT, session_id=session_id, intervention_id=response.intervention_id
    )


def _respond(interventions, session_id, intervention, decision="resume", key="r-1", **extra):
    return interventions.respond(
        project_id=PROJECT,
        session_id=session_id,
        intervention_id=intervention.intervention_id,
        username="expert",
        body=RespondAgentInterventionRequest(
            idempotency_key=key,
            expected_state_version=extra.pop("version", intervention.session_state_version),
            decision=decision,
            guidance=extra.pop("guidance", "Contrast is low but the fit is fine; rerun Rabi."),
            **extra,
        ),
    )


def test_unknown_outcome_pauses_session_notifies_once_and_resumes_without_replay(
    sessions: AgentSessionService, interventions: AgentInterventionService, slack: FakeSlack
) -> None:
    """The full loop: stop, persist, notify, expert answer, runner claim, outcome."""
    session = _session(sessions)
    action_id = _completed_run(sessions, session.session_id)

    opened = _create(interventions, session.session_id, _request(action_id))
    paused = sessions.get_session(project_id=PROJECT, session_id=session.session_id)

    assert opened.status.value == "open"
    assert opened.pauses_session is True
    assert paused.status.value == "waiting_for_human"
    assert paused.active_intervention_id == opened.intervention_id
    assert opened.notification.status.value == "sent"
    assert len(slack.calls) == 1
    root = slack.calls[0]
    assert root["channel"] == "C-agent"
    assert "?project=project-1" in str(root["attachments"])
    assert f"/interventions/{opened.intervention_id}" in str(root["attachments"])
    assert opened.can_resume is True
    assert opened.plan_hash.startswith("sha256:")

    # The pause blocks every further proposal for the session.
    with pytest.raises(HTTPException) as blocked:
        _run_task(sessions, session.session_id, key="a-2")
    assert blocked.value.status_code == 409

    # A repeated escalation with the same key is the same record and posts nothing new.
    again = _create(interventions, session.session_id, _request(action_id))
    assert again.intervention_id == opened.intervention_id
    assert len(slack.calls) == 1

    authorized = _respond(interventions, session.session_id, opened)
    still_paused = sessions.get_session(project_id=PROJECT, session_id=session.session_id)
    assert authorized.status.value == "resume_authorized"
    assert authorized.response is not None
    assert authorized.response.responded_by == "expert"
    assert authorized.response.resume_node_id == "rabi"
    assert authorized.resume_command is not None
    assert "resume-plan" in authorized.resume_command
    # Authorizing does not reactivate the session: nothing runs until a runner claims it.
    assert still_paused.status.value == "waiting_for_human"

    claim = ClaimAgentResumeRequest(claim_key="claim-1")
    resumed = interventions.claim_resume(
        project_id=PROJECT,
        session_id=session.session_id,
        intervention_id=opened.intervention_id,
        username="tester",
        body=claim,
    )
    active = sessions.get_session(project_id=PROJECT, session_id=session.session_id)
    assert resumed.status.value == "resumed"
    assert active.status.value == "active"
    # The budget was not reset by the pause or the resume.
    assert active.action_count == 1

    # The same claim is idempotent; another runner cannot take over.
    assert (
        interventions.claim_resume(
            project_id=PROJECT,
            session_id=session.session_id,
            intervention_id=opened.intervention_id,
            username="tester",
            body=claim,
        ).status.value
        == "resumed"
    )
    with pytest.raises(HTTPException) as concurrent:
        interventions.claim_resume(
            project_id=PROJECT,
            session_id=session.session_id,
            intervention_id=opened.intervention_id,
            username="tester",
            body=ClaimAgentResumeRequest(claim_key="claim-2"),
        )
    assert concurrent.value.status_code == 409

    # The resumed runner can propose the next measurement; the earlier action is not replayed.
    next_action = _run_task(sessions, session.session_id, key="plan-1-node-0-visit-1-action")
    assert next_action.action_id != action_id
    assert sessions.list_actions(project_id=PROJECT, session_id=session.session_id).total == 2

    done = interventions.record_resume_outcome(
        project_id=PROJECT,
        session_id=session.session_id,
        intervention_id=opened.intervention_id,
        username="tester",
        body=RecordAgentResumeOutcomeRequest(
            claim_key="claim-1", transition="pass", reason="Plan completed 1 nodes"
        ),
    )
    assert done.resume_outcome is not None
    assert done.resume_outcome.transition == "pass"
    with pytest.raises(HTTPException):
        interventions.record_resume_outcome(
            project_id=PROJECT,
            session_id=session.session_id,
            intervention_id=opened.intervention_id,
            username="tester",
            body=RecordAgentResumeOutcomeRequest(claim_key="claim-2", transition="pass"),
        )
    kinds = [event.kind for event in done.events]
    assert kinds == ["created", "resume", "resumed", "resume_outcome"]


def test_an_intervention_keeps_the_model_its_request_reported(
    sessions: AgentSessionService, interventions: AgentInterventionService
) -> None:
    session = _session(sessions)
    action_id = _completed_run(sessions, session.session_id)
    model = {"provider": "vllm", "model_id": "qwen3-32b", "host": "qdash-web-agent"}
    opened = _create(interventions, session.session_id, _request(action_id, model=model))
    assert opened.model is not None and opened.model.model_dump() == model
    # A retry under another model is the same request and returns the record unchanged.
    retried = interventions.create_intervention(
        project_id=PROJECT,
        session_id=session.session_id,
        username="tester",
        body=_request(action_id, model={"provider": "ollama", "model_id": "qwen3:8b"}),
    )
    assert retried.intervention_id == opened.intervention_id
    assert retried.model is not None and retried.model.model_dump() == model


def test_stale_and_duplicate_responses_are_rejected(
    sessions: AgentSessionService, interventions: AgentInterventionService
) -> None:
    session = _session(sessions)
    opened = _create(interventions, session.session_id, _request())

    with pytest.raises(HTTPException) as stale:
        _respond(
            interventions, session.session_id, opened, version=opened.session_state_version - 1
        )
    assert stale.value.status_code == 409
    assert "reload" in str(stale.value.detail)

    first = _respond(interventions, session.session_id, opened, decision="stop", key="r-1")
    # Retrying the same request returns the recorded answer.
    retried = _respond(interventions, session.session_id, opened, decision="stop", key="r-1")
    assert retried.status == first.status
    with pytest.raises(HTTPException) as second:
        _respond(interventions, session.session_id, opened, decision="resume", key="r-2")
    assert second.value.status_code == 409


def test_stop_cancels_the_session_and_it_is_not_reactivated(
    sessions: AgentSessionService, interventions: AgentInterventionService, slack: FakeSlack
) -> None:
    session = _session(sessions)
    opened = _create(interventions, session.session_id, _request())

    stopped = _respond(interventions, session.session_id, opened, decision="stop")
    cancelled = sessions.get_session(project_id=PROJECT, session_id=session.session_id)
    interventions.post_update(opened.intervention_id, "expert stopped the session.")

    assert stopped.status.value == "stopped"
    assert cancelled.status.value == "cancelled"
    assert slack.calls[-1]["thread_ts"] == "1.000"
    with pytest.raises(HTTPException):
        interventions.claim_resume(
            project_id=PROJECT,
            session_id=session.session_id,
            intervention_id=opened.intervention_id,
            username="tester",
            body=ClaimAgentResumeRequest(claim_key="claim-1"),
        )
    # A later escalation on the cancelled session is recorded but cannot resume.
    later = _create(interventions, session.session_id, _request(key="int-2"))
    assert later.pauses_session is False
    assert later.can_resume is False
    assert any("cancelled" in blocker for blocker in later.resume_blockers)


def test_exhausted_budget_still_records_help_but_blocks_resume(
    sessions: AgentSessionService, interventions: AgentInterventionService
) -> None:
    session = _session(sessions, max_actions=1)
    _completed_run(sessions, session.session_id)

    opened = _create(
        interventions,
        session.session_id,
        _request(reason="policy_limit", summary="The session has no actions left"),
    )

    assert opened.status.value == "open"
    assert opened.can_resume is False
    assert any("newly authorized session" in blocker for blocker in opened.resume_blockers)
    with pytest.raises(HTTPException) as refused:
        _respond(interventions, session.session_id, opened)
    assert refused.value.status_code == 409
    assert "newly authorized session" in str(refused.value.detail)
    # Stopping stays possible.
    assert _respond(interventions, session.session_id, opened, decision="stop").status.value == (
        "stopped"
    )


def test_expired_session_records_a_terminal_intervention(
    sessions: AgentSessionService, interventions: AgentInterventionService
) -> None:
    session = _session(sessions)
    doc = AgentSessionDocument.find_one({"session_id": session.session_id}).run()
    assert doc is not None
    doc.expires_at = now() - timedelta(seconds=1)
    doc.save()

    opened = _create(
        interventions, session.session_id, _request(reason="policy_limit", summary="Expired")
    )

    assert opened.session_status.value == "expired"
    assert opened.pauses_session is False
    assert opened.can_resume is False
    assert any("expired" in blocker for blocker in opened.resume_blockers)


def test_a_paused_session_expires_and_its_authorized_resume_cannot_be_claimed(
    sessions: AgentSessionService, interventions: AgentInterventionService
) -> None:
    session = _session(sessions)
    opened = _create(interventions, session.session_id, _request())
    _respond(interventions, session.session_id, opened)
    doc = AgentSessionDocument.find_one({"session_id": session.session_id}).run()
    assert doc is not None
    doc.expires_at = now() - timedelta(seconds=1)
    doc.save()

    with pytest.raises(HTTPException) as refused:
        interventions.claim_resume(
            project_id=PROJECT,
            session_id=session.session_id,
            intervention_id=opened.intervention_id,
            username="tester",
            body=ClaimAgentResumeRequest(claim_key="claim-1"),
        )
    assert refused.value.status_code == 409
    assert "expired" in str(refused.value.detail)
    assert (
        sessions.get_session(project_id=PROJECT, session_id=session.session_id).status.value
        == "expired"
    )


def test_running_measurement_and_visit_limit_block_resume(
    sessions: AgentSessionService, interventions: AgentInterventionService
) -> None:
    session = _session(sessions)
    action = _run_task(sessions, session.session_id)
    doc = AgentActionDocument.find_one({"action_id": action.action_id}).run()
    assert doc is not None
    doc.execution_status = "running"
    doc.save()

    opened = _create(
        interventions,
        session.session_id,
        _request(checkpoint=_checkpoint(visit_counts={"rabi": 2}, node_path=["rabi", "rabi"])),
    )

    assert any("still running" in blocker for blocker in opened.resume_blockers)
    options = {option.node_id: option for option in opened.resume_options}
    assert options["rabi"].available is False
    assert options["chevron"].available is True

    doc.execution_status = "completed"
    doc.save()
    with pytest.raises(HTTPException) as over_budget:
        _respond(interventions, session.session_id, opened)
    assert "already ran 2 times" in str(over_budget.value.detail)
    chosen = _respond(interventions, session.session_id, opened, resume_node_id="chevron")
    assert chosen.response is not None
    assert chosen.response.resume_node_id == "chevron"


def test_references_outside_the_session_are_rejected(
    sessions: AgentSessionService, interventions: AgentInterventionService
) -> None:
    session = _session(sessions)
    other = _session(sessions)
    foreign_action = _completed_run(sessions, other.session_id)

    with pytest.raises(HTTPException) as foreign:
        interventions.create_intervention(
            project_id=PROJECT,
            session_id=session.session_id,
            username="tester",
            body=_request(foreign_action),
        )
    assert foreign.value.status_code == 422
    with pytest.raises(HTTPException) as scope:
        interventions.create_intervention(
            project_id=PROJECT,
            session_id=session.session_id,
            username="tester",
            body=_request(qids=["Q09"]),
        )
    assert scope.value.status_code == 422
    with pytest.raises(HTTPException) as other_project:
        interventions.get_intervention(
            project_id="project-2", session_id=session.session_id, intervention_id="x"
        )
    assert other_project.value.status_code == 404
    assert AgentInterventionDocument.count() == 0
    assert (
        sessions.get_session(project_id=PROJECT, session_id=session.session_id).status.value
        == "active"
    )


def test_failed_slack_delivery_keeps_the_pause_and_retries(
    sessions: AgentSessionService, interventions: AgentInterventionService, slack: FakeSlack
) -> None:
    slack.failures = 1
    session = _session(sessions)

    opened = _create(interventions, session.session_id, _request())

    assert opened.notification.status.value == "pending"
    assert opened.notification.attempts == 1
    assert "ConnectionError" in opened.notification.last_error
    assert opened.notification.next_attempt_at is not None
    assert (
        sessions.get_session(project_id=PROJECT, session_id=session.session_id).status.value
        == "waiting_for_human"
    )
    # Not due yet: the sweeper leaves it alone.
    interventions.retry_due_notifications()
    assert len(slack.calls) == 1

    retried = interventions.retry_notification(
        project_id=PROJECT,
        session_id=session.session_id,
        intervention_id=opened.intervention_id,
        username="expert",
    )
    assert retried.notification.status.value == "sent"
    assert retried.notification.message_ts == "2.000"
    # A sent message is never posted again.
    interventions.retry_notification(
        project_id=PROJECT,
        session_id=session.session_id,
        intervention_id=opened.intervention_id,
        username="expert",
    )
    interventions.deliver_notification(opened.intervention_id, explicit=True)
    assert len(slack.calls) == 2


def test_due_deliveries_are_retried_until_marked_failed(
    sessions: AgentSessionService, interventions: AgentInterventionService, slack: FakeSlack
) -> None:
    slack.failures = 100
    session = _session(sessions)
    opened = _create(interventions, session.session_id, _request())
    collection = AgentInterventionDocument.get_motor_collection()
    for _ in range(10):
        collection.update_one(
            {"intervention_id": opened.intervention_id},
            {"$set": {"notification.next_attempt_at": now() - timedelta(seconds=1)}},
        )
        interventions.retry_due_notifications()

    failed = interventions.get_intervention(
        project_id=PROJECT, session_id=session.session_id, intervention_id=opened.intervention_id
    )
    assert failed.notification.status.value == "failed"
    assert failed.notification.attempts == 6
    assert failed.status.value == "open"


def test_disabled_slack_is_recorded_and_the_intervention_still_works(
    init_db, slack: FakeSlack
) -> None:
    ChipDocument(
        project_id=PROJECT,
        chip_id="chip-001",
        username="tester",
        size=4,
        system_info=SystemInfoModel(),
    ).insert()
    interventions = AgentInterventionService(notifier=_notifier(slack, enabled=False))
    sessions = AgentSessionService(intervention_service=interventions)
    session = _session(sessions)

    opened = _create(interventions, session.session_id, _request())

    assert opened.notification.status.value == "disabled"
    assert slack.calls == []
    with pytest.raises(HTTPException) as refused:
        interventions.retry_notification(
            project_id=PROJECT,
            session_id=session.session_id,
            intervention_id=opened.intervention_id,
            username="expert",
        )
    assert refused.value.status_code == 409
    assert _respond(interventions, session.session_id, opened).status.value == "resume_authorized"


def test_request_human_action_records_an_intervention_without_budget(
    sessions: AgentSessionService, interventions: AgentInterventionService, slack: FakeSlack
) -> None:
    session = _session(sessions, max_actions=1)
    _run_task(sessions, session.session_id)
    version = sessions.get_session(project_id=PROJECT, session_id=session.session_id).state_version

    action = sessions.submit_action(
        project_id=PROJECT,
        session_id=session.session_id,
        username="agent-user",
        body=SubmitAgentActionRequest(
            idempotency_key="human-1",
            expected_state_version=version,
            action_type=AgentActionType.REQUEST_HUMAN,
            diagnosis="The resonator dip moved by 5 MHz; I do not know why.",
        ),
    )
    assert action.decision.value == "authorized"
    assert action.intervention_id is not None
    interventions.deliver_notification(action.intervention_id)
    opened = interventions.get_intervention(
        project_id=PROJECT, session_id=session.session_id, intervention_id=action.intervention_id
    )
    paused = sessions.get_session(project_id=PROJECT, session_id=session.session_id)

    assert opened.reason.value == "agent_request"
    assert opened.action_id == action.action_id
    assert opened.checkpoint is None
    assert paused.status.value == "waiting_for_human"
    assert paused.action_count == 1
    assert len(slack.calls) == 1
    # Without actions left there is nothing to resume into.
    assert opened.can_resume is False


def test_request_human_without_checkpoint_reactivates_the_session_on_resume(
    sessions: AgentSessionService, interventions: AgentInterventionService
) -> None:
    session = _session(sessions)
    action = sessions.submit_action(
        project_id=PROJECT,
        session_id=session.session_id,
        body=SubmitAgentActionRequest(
            idempotency_key="human-1",
            expected_state_version=0,
            action_type=AgentActionType.REQUEST_HUMAN,
            diagnosis="Which qubit frequency should I trust?",
        ),
    )
    assert action.intervention_id is not None
    opened = interventions.get_intervention(
        project_id=PROJECT, session_id=session.session_id, intervention_id=action.intervention_id
    )

    resumed = _respond(interventions, session.session_id, opened, guidance="Use the Chevron one.")
    active = sessions.get_session(project_id=PROJECT, session_id=session.session_id)

    assert resumed.status.value == "resumed"
    assert resumed.response is not None
    assert resumed.response.guidance == "Use the Chevron one."
    assert active.status.value == "active"
    assert active.active_intervention_id is None


def test_a_half_applied_response_is_rolled_back_on_read(
    sessions: AgentSessionService, interventions: AgentInterventionService
) -> None:
    session = _session(sessions)
    opened = _create(interventions, session.session_id, _request())
    AgentInterventionDocument.get_motor_collection().update_one(
        {"intervention_id": opened.intervention_id},
        {
            "$set": {
                "status": "responding",
                "response": {
                    "response_id": "lost",
                    "idempotency_key": "r-lost",
                    "decision": "resume",
                    "guidance": "",
                    "resume_node_id": "rabi",
                    "responded_by": "expert",
                    "responded_at": now(),
                    "expected_state_version": opened.session_state_version,
                },
                "responding_since": now() - timedelta(minutes=5),
            }
        },
    )

    settled = interventions.get_intervention(
        project_id=PROJECT, session_id=session.session_id, intervention_id=opened.intervention_id
    )

    assert settled.status.value == "open"
    assert settled.response is None
    assert _respond(interventions, session.session_id, settled).status.value == (
        "resume_authorized"
    )


def test_a_second_escalation_while_paused_is_refused(
    sessions: AgentSessionService, interventions: AgentInterventionService
) -> None:
    session = _session(sessions)
    opened = _create(interventions, session.session_id, _request())

    with pytest.raises(HTTPException) as refused:
        interventions.create_intervention(
            project_id=PROJECT,
            session_id=session.session_id,
            username="tester",
            body=_request(key="int-2"),
        )
    assert refused.value.status_code == 409
    assert opened.intervention_id in str(refused.value.detail)


def test_slack_escapes_dynamic_text_and_preserves_application_links(
    sessions: AgentSessionService, interventions: AgentInterventionService, slack: FakeSlack
) -> None:
    session = _session(sessions)
    opened = _create(interventions, session.session_id, _request())
    doc = AgentInterventionDocument.find_one({"intervention_id": opened.intervention_id}).run()
    assert doc is not None
    payload = "<!channel> <https://example.com|trusted link> & <@U123>"
    doc.question = payload
    doc.chip_id = payload
    doc.task_name = payload
    doc.qids = [payload]
    slack.calls.clear()
    notifier = _notifier(slack)
    notifier.post_root(doc, project_name=payload)
    root = slack.calls[0]
    rendered = str(root)
    assert "<!channel>" not in rendered
    assert "<@U123>" not in rendered
    assert "<https://example.com|trusted link>" not in rendered
    blocks = root["attachments"][0]["blocks"]
    escaped = "&lt;!channel&gt; &lt;https://example.com|trusted link&gt; &amp; &lt;@U123&gt;"
    assert escaped in blocks[2]["text"]["text"]
    assert all(
        escaped in field["text"]
        for field in blocks[1]["fields"]
        if field["text"].startswith(("*Project:", "*Chip:", "*Targets:", "*Task:"))
    )
    assert f"/interventions/{doc.intervention_id}?project=project-1|" in blocks[0]["text"]["text"]
    notifier.post_reply(doc, payload)
    reply = slack.calls[1]["text"]
    assert reply.startswith(escaped)
    assert "|Open in QDash>" in reply


# ---------------------------------------------------------------- checkpoint reconciliation


def _claim(interventions, session_id, intervention, key="claim-1"):
    return interventions.claim_resume(
        project_id=PROJECT,
        session_id=session_id,
        intervention_id=intervention.intervention_id,
        username="tester",
        body=ClaimAgentResumeRequest(claim_key=key),
    )


def _refused(interventions, session_id, body) -> str:
    with pytest.raises(HTTPException) as refused:
        interventions.create_intervention(
            project_id=PROJECT, session_id=session_id, username="tester", body=body
        )
    assert refused.value.status_code == 422
    return str(refused.value.detail)


def test_a_checkpoint_with_fewer_visits_than_qdash_recorded_is_rejected(
    sessions: AgentSessionService, interventions: AgentInterventionService
) -> None:
    """Lowering a node's visit count cannot restore its spent budget."""
    session = _session(sessions)
    _run_task(sessions, session.session_id, key=RABI_KEY)
    _run_task(sessions, session.session_id, key="plan-1-node-0-visit-1-action")

    detail = _refused(interventions, session.session_id, _request())
    assert "fewer node visits than QDash recorded" in detail
    assert "rabi (checkpoint 1, QDash 2)" in detail
    # A path that disagrees with its own counts is rejected as well.
    detail = _refused(
        interventions,
        session.session_id,
        _request(checkpoint=_checkpoint(visit_counts={"rabi": 2}, node_path=["rabi"])),
    )
    assert "do not match its node path" in detail
    assert AgentInterventionDocument.count() == 0
    active = sessions.get_session(project_id=PROJECT, session_id=session.session_id)
    assert active.status.value == "active"

    # The truthful checkpoint is accepted, and its node budget is spent.
    opened = _create(
        interventions,
        session.session_id,
        _request(checkpoint=_checkpoint(visit_counts={"rabi": 2}, node_path=["rabi", "rabi"])),
    )
    options = {option.node_id: option for option in opened.resume_options}
    assert options["rabi"].visits == 2
    assert options["rabi"].available is False


def _refused_detail(interventions, session_id, body) -> object:
    with pytest.raises(HTTPException) as refused:
        interventions.create_intervention(
            project_id=PROJECT, session_id=session_id, username="tester", body=body
        )
    assert refused.value.status_code == 422
    return refused.value.detail


def test_only_a_reconciliation_failure_is_coded_as_checkpoint_rejected(
    sessions: AgentSessionService, interventions: AgentInterventionService
) -> None:
    """A runner may record a stop without the checkpoint only for this code."""
    session = _session(sessions)
    _run_task(sessions, session.session_id, key="manual-action")

    # A well-formed checkpoint that the session's mixed history cannot support.
    detail = _refused_detail(interventions, session.session_id, _request())
    assert isinstance(detail, dict)
    assert detail["code"] == "checkpoint_rejected"
    assert "not part of this plan" in detail["message"]
    # A checkpoint that contradicts itself stays a plain 422, even on the same history.
    detail = _refused_detail(
        interventions,
        session.session_id,
        _request(checkpoint=_checkpoint(visit_counts={"rabi": 2}, node_path=["rabi"])),
    )
    assert isinstance(detail, str)
    assert "do not match its node path" in detail
    assert AgentInterventionDocument.count() == 0
    active = sessions.get_session(project_id=PROJECT, session_id=session.session_id)
    assert active.status.value == "active"


def test_a_fresh_prefix_cannot_hide_earlier_plan_runs(
    sessions: AgentSessionService, interventions: AgentInterventionService
) -> None:
    session = _session(sessions)
    _run_task(sessions, session.session_id, key=RABI_KEY)
    _run_task(sessions, session.session_id, key="plan-1-node-0-visit-1-action")

    detail = _refused(
        interventions,
        session.session_id,
        _request(
            checkpoint=_checkpoint(idempotency_prefix="plan-2", visit_counts={}, node_path=[])
        ),
    )
    assert "not part of this plan" in detail
    assert AgentInterventionDocument.count() == 0


def test_a_resumed_plan_must_continue_the_bound_plan(
    sessions: AgentSessionService, interventions: AgentInterventionService
) -> None:
    """After the first checkpoint, the session accepts only the same plan, extended."""
    session = _session(sessions)
    _run_task(sessions, session.session_id, key=RABI_KEY)
    first = _create(interventions, session.session_id, _request())
    _respond(interventions, session.session_id, first)
    claimed = _claim(interventions, session.session_id, first)
    assert claimed.status.value == "resumed"
    # The resumed runner keeps the visit numbering, so its key is a new physical operation.
    _run_task(sessions, session.session_id, key="plan-1-node-0-visit-1-action")

    def follow_up(**checkpoint: Any):
        return _request(
            key="int-2",
            previous_intervention_id=first.intervention_id,
            checkpoint=_checkpoint(**checkpoint),
        )

    # A fresh prefix with reset counts, even with no new run under it.
    detail = _refused(
        interventions,
        session.session_id,
        follow_up(idempotency_prefix="plan-2", visit_counts={}, node_path=[]),
    )
    assert "changed: idempotency_prefix" in detail
    # A raised node budget.
    detail = _refused(
        interventions,
        session.session_id,
        follow_up(visit_counts={"rabi": 2}, node_path=["rabi", "rabi"], max_node_visits=5),
    )
    assert "changed: max_node_visits" in detail
    # A changed plan.
    detail = _refused(
        interventions,
        session.session_id,
        follow_up(
            nodes=[
                {
                    "id": "rabi",
                    "task_name": "CheckRabi",
                    "candidate_parameter": "control_amplitude",
                },
                {"id": "chevron", "task_name": "CheckChevron", "candidate_parameter": "x"},
            ],
            visit_counts={"rabi": 2},
            node_path=["rabi", "rabi"],
        ),
    )
    assert "plan_hash" in detail
    # Counts reset to the first checkpoint's.
    detail = _refused(interventions, session.session_id, follow_up())
    assert "fewer node visits" in detail
    # A path that drops the recorded history, with counts kept.
    detail = _refused(
        interventions,
        session.session_id,
        follow_up(
            visit_counts={"rabi": 2, "chevron": 1},
            node_path=["chevron", "rabi", "rabi"],
        ),
    )
    assert "does not extend the path" in detail

    # The truthful continuation is accepted and the node budget holds.
    second = _create(
        interventions,
        session.session_id,
        follow_up(visit_counts={"rabi": 2}, node_path=["rabi", "rabi"]),
    )
    assert second.status.value == "open"
    options = {option.node_id: option for option in second.resume_options}
    assert options["rabi"].available is False
    with pytest.raises(HTTPException) as over_budget:
        _respond(interventions, session.session_id, second, key="r-2")
    assert "already ran 2 times" in str(over_budget.value.detail)
    assert (
        _respond(
            interventions, session.session_id, second, key="r-3", resume_node_id="chevron"
        ).status.value
        == "resume_authorized"
    )


def test_checkpoint_candidates_must_match_their_plan_run(
    sessions: AgentSessionService, interventions: AgentInterventionService
) -> None:
    session = _session(sessions)
    rabi = _completed_run(sessions, session.session_id, key=RABI_KEY, ref="a-1")

    def with_candidates(*candidates: dict[str, str]):
        return _request(checkpoint=_checkpoint(accepted_candidates=list(candidates)))

    # The parameter of another node.
    detail = _refused(
        interventions,
        session.session_id,
        with_candidates(
            {"action_id": rabi, "parameter_name": "qubit_frequency", "task_id": "task-a-1"}
        ),
    )
    assert "does not match the authorized run" in detail
    # A task result of another run.
    original = TaskResultHistoryDocument.find_one({"task_id": "task-a-1"}).run()
    assert original is not None
    TaskResultHistoryDocument(
        **{
            **original.model_dump(exclude={"id"}),
            "task_id": "task-other",
            "execution_id": "exec-other",
        }
    ).insert()
    detail = _refused(
        interventions,
        session.session_id,
        with_candidates(
            {"action_id": rabi, "parameter_name": "control_amplitude", "task_id": "task-other"}
        ),
    )
    assert "does not match the authorized run" in detail
    # Two values for one parameter.
    candidate = {"action_id": rabi, "parameter_name": "control_amplitude", "task_id": "task-a-1"}
    detail = _refused(interventions, session.session_id, with_candidates(candidate, candidate))
    assert "more than one candidate" in detail

    opened = _create(interventions, session.session_id, with_candidates(candidate))
    assert opened.checkpoint is not None
    assert opened.checkpoint.accepted_candidates[0].task_id == "task-a-1"


SECRET = "fake-credential-must-not-be-stored"  # noqa: S105 - test marker, not a credential


class LeakySlack(FakeSlack):
    """Fails with exceptions whose text quotes the bot token, as a transport error may."""

    def __init__(self, exc: Exception) -> None:
        super().__init__()
        self.exc = exc

    def chat_postMessage(self, *, channel: str, **kwargs: Any) -> dict[str, str]:
        self.calls.append({"channel": channel, **kwargs})
        raise self.exc


class FakeSlackApiError(Exception):
    """Shaped like ``slack_sdk.errors.SlackApiError``: a message and a response with a code."""

    def __init__(self, message: str, response: dict[str, Any]) -> None:
        super().__init__(message)
        self.response = response


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (
            ConnectionError(
                f"POST https://slack.com/api/chat.postMessage Authorization: Bearer {SECRET}"
            ),
            "ConnectionError",
        ),
        (
            FakeSlackApiError(
                f"The request failed for token {SECRET}",
                {"ok": False, "error": "invalid_auth"},
            ),
            "FakeSlackApiError: invalid_auth",
        ),
        (
            FakeSlackApiError("failed", {"ok": False, "error": f"bad {SECRET}"}),
            "FakeSlackApiError",
        ),
    ],
)
def test_slack_errors_are_stored_without_their_text(
    init_db, caplog: pytest.LogCaptureFixture, exc: Exception, expected: str
) -> None:
    ChipDocument(
        project_id=PROJECT,
        chip_id="chip-001",
        username="tester",
        size=4,
        system_info=SystemInfoModel(),
    ).insert()
    leaky = LeakySlack(exc)
    interventions = AgentInterventionService(notifier=_notifier(leaky))
    sessions = AgentSessionService(intervention_service=interventions)
    session = _session(sessions)

    with caplog.at_level("DEBUG"):
        opened = _create(interventions, session.session_id, _request())
        interventions.post_update(opened.intervention_id, "update")
        retried = interventions.retry_notification(
            project_id=PROJECT,
            session_id=session.session_id,
            intervention_id=opened.intervention_id,
            username="expert",
        )

    assert retried.notification.last_error == expected
    stored = AgentInterventionDocument.find_one({"intervention_id": opened.intervention_id}).run()
    assert stored is not None
    assert SECRET not in stored.model_dump_json()
    assert SECRET not in retried.model_dump_json()
    assert SECRET not in caplog.text
    assert "Slack delivery attempt" in caplog.text


# ------------------------------------------------------------------ attempt evidence


def _evaluation(task_id: str, *, evaluation_id: str, run_id: str, **overrides: Any) -> None:
    from qdash.dbmodel.evaluation import EvaluationDocument
    from qdash.dbmodel.evaluation_run import EvaluationRunDocument

    run = {
        "run_id": run_id,
        "project_id": PROJECT,
        "chip_id": "chip-001",
        "task_name": "CheckRabi",
        "entity_type": "qubit",
        "requested_by": "tester",
    }
    run.update(overrides.pop("run", {}))
    if EvaluationRunDocument.find_one({"run_id": run_id}).run() is None:
        EvaluationRunDocument(**run).insert()
    evaluation = {
        "evaluation_id": evaluation_id,
        "run_id": run_id,
        "project_id": PROJECT,
        "chip_id": "chip-001",
        "task_id": task_id,
        "task_name": "CheckRabi",
        "qid": "Q00",
    }
    evaluation.update(overrides)
    EvaluationDocument(**evaluation).insert()


def _attempt_request(key: str = "int-ev", **attempt: Any) -> CreateAgentInterventionRequest:
    return CreateAgentInterventionRequest.model_validate(
        {
            "idempotency_key": key,
            "reason": "evaluation_failed",
            "summary": "The evaluation did not complete",
            "question": "Is the measurement usable?",
            "qids": ["Q00"],
            "attempts": [{"node_id": "rabi", "reason": "reported by the runner", **attempt}],
        }
    )


def _second_session_on_chip(sessions: AgentSessionService, chip_id: str):
    if ChipDocument.find_one({"chip_id": chip_id}).run() is None:
        ChipDocument(
            project_id=PROJECT,
            chip_id=chip_id,
            username="tester",
            size=4,
            system_info=SystemInfoModel(),
        ).insert()
    return sessions.create_session(
        project_id=PROJECT,
        username="tester",
        body=CreateAgentSessionRequest(
            chip_id=chip_id,
            policy=AgentSessionPolicy(qids=["Q00"], allowed_tasks=["CheckRabi"], max_actions=4),
            expires_in_seconds=3600,
        ),
    )


def _move_to_chip(ref: str, chip_id: str) -> None:
    for model in (ExecutionHistoryDocument, TaskResultHistoryDocument):
        model.get_motor_collection().update_many(
            {"execution_id": f"exec-{ref}"}, {"$set": {"chip_id": chip_id}}
        )


def test_a_full_evidence_chain_is_recorded(
    sessions: AgentSessionService, interventions: AgentInterventionService
) -> None:
    session = _session(sessions)
    action_id = _completed_run(sessions, session.session_id)
    _evaluation("task-a-1", evaluation_id="ev-1", run_id="evr-1")

    opened = _create(
        interventions,
        session.session_id,
        _attempt_request(
            task_name="CheckRabi",
            qid="Q00",
            status="failed",
            action_id=action_id,
            execution_id="exec-a-1",
            task_id="task-a-1",
            evaluation_id="ev-1",
            evaluation_run_id="evr-1",
        ),
    )

    attempt = opened.attempts[0]
    assert attempt.evaluation_id == "ev-1"
    assert attempt.execution_id == "exec-a-1"
    # Client-reported fields are stored as given.
    assert attempt.reason == "reported by the runner"
    assert attempt.status == "failed"


@pytest.mark.parametrize(
    "attempt",
    [
        {},
        {"task_name": "CheckRabi", "qid": "Q00", "transition": "retry"},
        {"evaluation_id": "ev-1"},
        {"task_id": "task-a-1"},
        {"execution_id": "exec-a-1"},
        {"evaluation_run_id": "evr-1", "task_id": "task-a-1"},
    ],
)
def test_partial_evidence_of_this_session_is_recorded(
    sessions: AgentSessionService, interventions: AgentInterventionService, attempt: dict[str, Any]
) -> None:
    """An attempt that failed early cites only what it has; each id is still checked."""
    session = _session(sessions)
    _completed_run(sessions, session.session_id)
    _evaluation("task-a-1", evaluation_id="ev-1", run_id="evr-1")

    opened = _create(interventions, session.session_id, _attempt_request(**attempt))
    assert opened.status.value == "open"


def test_a_pre_dispatch_failure_and_exhausted_budget_are_recorded(
    sessions: AgentSessionService, interventions: AgentInterventionService
) -> None:
    session = _session(sessions, max_actions=1)
    # An authorized action that never produced an execution.
    action = _run_task(sessions, session.session_id)

    opened = _create(
        interventions,
        session.session_id,
        CreateAgentInterventionRequest.model_validate(
            {
                "idempotency_key": "budget-1",
                "reason": "policy_limit",
                "summary": "The session has no actions left",
                "question": "Stop?",
                "qids": ["Q00"],
                "attempts": [
                    {
                        "task_name": "CheckRabi",
                        "qid": "Q00",
                        "action_id": action.action_id,
                        "reason": "QDash API request failed (QDashTransportError)",
                    }
                ],
            }
        ),
    )
    assert opened.status.value == "open"
    assert opened.can_resume is False


def _refused_plain(interventions, session_id, body) -> str:
    detail = _refused_detail(interventions, session_id, body)
    # A reference failure is never the checkpoint_rejected code a runner may fall back on.
    assert isinstance(detail, str), detail
    assert AgentInterventionDocument.count() == 0
    return detail


@pytest.mark.parametrize(
    "evidence",
    [
        {"task_id": "task-a-1"},
        {"evaluation_id": "ev-1"},
        {"task_id": "task-a-1", "evaluation_run_id": "evr-1"},
    ],
)
def test_an_unlinked_action_cannot_borrow_another_actions_result(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    evidence: dict[str, str],
) -> None:
    session = _session(sessions)
    _completed_run(sessions, session.session_id)
    _evaluation("task-a-1", evaluation_id="ev-1", run_id="evr-1")
    unlinked = _run_task(sessions, session.session_id, key="unlinked-action")

    detail = _refused_plain(
        interventions,
        session.session_id,
        _attempt_request(action_id=unlinked.action_id, **evidence),
    )
    assert "without its resolved execution" in detail
    opened = _create(
        interventions, session.session_id, _attempt_request(action_id=unlinked.action_id)
    )
    assert opened.status.value == "open"


def test_an_execution_of_another_session_is_refused(
    sessions: AgentSessionService, interventions: AgentInterventionService
) -> None:
    session = _session(sessions)
    own = _completed_run(sessions, session.session_id, ref="a-1")
    other = _session(sessions)
    _completed_run(sessions, other.session_id, ref="b-1")

    detail = _refused_plain(
        interventions,
        session.session_id,
        _attempt_request(action_id=own, execution_id="exec-b-1"),
    )
    assert "is not the execution QDash links to action" in detail
    detail = _refused_plain(
        interventions, session.session_id, _attempt_request(execution_id="exec-b-1")
    )
    assert "was not dispatched by this session" in detail
    detail = _refused_plain(interventions, session.session_id, _attempt_request(task_id="task-b-1"))
    assert "did not come from an execution of this session" in detail
    detail = _refused_plain(
        interventions,
        session.session_id,
        _attempt_request(action_id=own, task_id="task-b-1"),
    )
    assert "did not come from execution exec-a-1" in detail


def test_an_execution_on_another_chip_is_refused(
    sessions: AgentSessionService, interventions: AgentInterventionService
) -> None:
    session = _session(sessions)
    action_id = _completed_run(sessions, session.session_id)
    _move_to_chip("a-1", "chip-002")

    detail = _refused_plain(
        interventions,
        session.session_id,
        _attempt_request(action_id=action_id, execution_id="exec-a-1"),
    )
    assert "is not the execution QDash links" in detail
    detail = _refused_plain(interventions, session.session_id, _attempt_request(task_id="task-a-1"))
    assert "outside the session's chip" in detail

    # A session on the other chip cannot cite it either, from this session.
    elsewhere = _second_session_on_chip(sessions, "chip-002")
    detail = _refused_plain(
        interventions, elsewhere.session_id, _attempt_request(execution_id="exec-a-1")
    )
    assert "was not dispatched by this session" in detail


def test_swapped_task_results_and_evaluations_are_refused(
    sessions: AgentSessionService, interventions: AgentInterventionService
) -> None:
    session = _session(sessions, max_actions=4)
    first = _completed_run(sessions, session.session_id, ref="a-1")
    _completed_run(sessions, session.session_id, key="plan-1-node-0-visit-1-action", ref="a-2")
    _evaluation("task-a-1", evaluation_id="ev-1", run_id="evr-1")
    _evaluation("task-a-2", evaluation_id="ev-2", run_id="evr-2")
    _evaluation(
        "task-a-1",
        evaluation_id="ev-chevron",
        run_id="evr-chevron",
        task_name="CheckChevron",
        run={"task_name": "CheckChevron"},
    )

    cases = [
        (
            {"action_id": first, "execution_id": "exec-a-1", "task_id": "task-a-2"},
            "did not come from execution exec-a-1",
        ),
        ({"action_id": first, "execution_id": "exec-a-2"}, "is not the execution QDash links"),
        ({"task_id": "task-a-1", "evaluation_id": "ev-2"}, "evaluated task result task-a-2"),
        ({"evaluation_id": "ev-1", "evaluation_run_id": "evr-2"}, "is not part of evaluation run"),
        ({"task_id": "task-a-1", "evaluation_run_id": "evr-chevron"}, "did not evaluate CheckRabi"),
        ({"evaluation_run_id": "evr-1"}, "without the task result it evaluated"),
        ({"action_id": first, "task_name": "CheckChevron"}, "ran CheckRabi, not CheckChevron"),
        ({"task_id": "task-a-1", "task_name": "CheckChevron"}, "is a CheckRabi result"),
        ({"task_id": "task-a-1", "qid": "Q09"}, "target Q09 is outside the session scope"),
        ({"evaluation_id": "nope"}, "Evaluations not found in this project"),
        ({"evaluation_run_id": "nope", "task_id": "task-a-1"}, "Evaluation runs not found"),
    ]
    for index, (attempt, message) in enumerate(cases):
        detail = _refused_plain(
            interventions, session.session_id, _attempt_request(key=f"swap-{index}", **attempt)
        )
        assert message in detail, (attempt, detail)


def test_a_fabricated_task_display_on_a_result_is_refused(
    sessions: AgentSessionService, interventions: AgentInterventionService
) -> None:
    """The result's own qid decides; an attempt cannot relabel it."""
    session = sessions.create_session(
        project_id=PROJECT,
        username="tester",
        body=CreateAgentSessionRequest(
            chip_id="chip-001",
            policy=AgentSessionPolicy(
                qids=["Q00", "Q01"], allowed_tasks=["CheckRabi"], max_actions=4
            ),
            expires_in_seconds=3600,
        ),
    )
    action_id = _completed_run(sessions, session.session_id)

    detail = _refused_plain(
        interventions, session.session_id, _attempt_request(task_id="task-a-1", qid="Q01")
    )
    assert "is for Q00, not Q01" in detail
    detail = _refused_plain(
        interventions, session.session_id, _attempt_request(action_id=action_id, qid="Q01")
    )
    assert "did not run on Q01" in detail


def test_references_of_another_project_are_refused(
    sessions: AgentSessionService, interventions: AgentInterventionService
) -> None:
    session = _session(sessions)
    _completed_run(sessions, session.session_id)
    for model in (ExecutionHistoryDocument, TaskResultHistoryDocument):
        model.get_motor_collection().update_many(
            {"execution_id": "exec-a-1"}, {"$set": {"project_id": "project-2"}}
        )

    detail = _refused_plain(interventions, session.session_id, _attempt_request(task_id="task-a-1"))
    assert "Task results not found in this project" in detail
    detail = _refused_plain(
        interventions, session.session_id, _attempt_request(execution_id="exec-a-1")
    )
    assert "was not dispatched by this session" in detail


def test_an_unknown_checkpoint_source_execution_is_refused(
    sessions: AgentSessionService, interventions: AgentInterventionService
) -> None:
    session = _session(sessions)
    _run_task(sessions, session.session_id)

    detail = _refused_plain(
        interventions,
        session.session_id,
        _request(checkpoint=_checkpoint(source_execution_id="exec-missing")),
    )
    assert "source execution exec-missing" in detail
