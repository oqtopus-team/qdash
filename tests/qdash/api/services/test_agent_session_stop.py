"""Stopping an agent session on a person's request.

A stop is one compare-and-set that moves an active or paused session to ``cancelled``
and records who stopped it and why. After it, nothing passes the session gate: no
dispatch, commit, apply, or resume. What passed the gate before it is not cancelled, only
reported, and a repeat or a stop of an ended session changes nothing.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any, cast

import pytest
from fastapi import HTTPException

import qdash.api.services.agent_session_gate as gate
import qdash.api.services.agent_session_service as session_service_module
from qdash.api.schemas.agent_session import (
    ClaimAgentResumeRequest,
    ExecuteAgentActionRequest,
    RespondAgentInterventionRequest,
    StopAgentSessionRequest,
    SubmitAgentActionRequest,
)
from qdash.common.utils.datetime import now
from qdash.datamodel.agent_session import AgentActionType, AgentInterventionDecision
from qdash.dbmodel.agent_session import (
    AgentActionDocument,
    AgentInterventionDocument,
    AgentSessionDocument,
)
from tests.qdash.api.services import test_agent_session_barrier as barrier
from tests.qdash.api.services.test_agent_session_barrier import (
    PROJECT,
    FakeFlowService,
    _authorize_run,
    _commit_body,
    _completed_with_candidate,
    _pause,
    _session,
    _state,
)

# The barrier tests' fixtures: a project, a chip, Slack, and the catalog of one task.
slack = barrier.slack
interventions = barrier.interventions
sessions = barrier.sessions
catalog = barrier.catalog

if TYPE_CHECKING:
    from qdash.api.services.agent_intervention_service import AgentInterventionService
    from qdash.api.services.agent_session_service import AgentSessionService
    from qdash.api.services.flow_service import FlowService
    from qdash.api.services.task_file_service import TaskFileService


def _stop(
    sessions: AgentSessionService,
    session_id: str,
    *,
    key: str = "stop-1",
    reason: str = "The user asked to stop",
    username: str = "tester",
) -> Any:
    return sessions.stop_session(
        project_id=PROJECT,
        session_id=session_id,
        username=username,
        body=StopAgentSessionRequest(idempotency_key=key, reason=reason),
    )


def _submit(sessions: AgentSessionService, session_id: str, key: str, kind: AgentActionType) -> Any:
    return sessions.submit_action(
        project_id=PROJECT,
        session_id=session_id,
        body=SubmitAgentActionRequest(
            idempotency_key=key,
            expected_state_version=_state(session_id).state_version,
            action_type=kind,
            task_name="CheckQubitSpectroscopy" if kind == AgentActionType.RUN_TASK else None,
            qids=["Q00"] if kind == AgentActionType.RUN_TASK else [],
        ),
    )


def test_a_stop_ends_an_active_session_once_and_records_who_and_why(
    sessions: AgentSessionService,
) -> None:
    session_id = _session(sessions)
    before = _state(session_id)

    stopped = _stop(sessions, session_id)
    assert stopped.outcome == "stopped"
    assert stopped.session.status.value == "cancelled"
    assert stopped.session.state_version == before.state_version + 1
    assert stopped.in_flight == []
    stop = stopped.session.stop
    assert stop is not None
    assert (stop.stopped_by, stop.reason, stop.status_before.value) == (
        "tester",
        "The user asked to stop",
        "active",
    )
    assert stopped.session.end_notification is not None
    assert stopped.session.end_notification.event.value == "cancelled"
    assert stopped.session.end_notification.actor == "tester"

    # A repeat is a no-op; the same key with another reason is a different request.
    again = _stop(sessions, session_id)
    assert again.outcome == "already_stopped"
    assert again.session.state_version == stopped.session.state_version
    with pytest.raises(HTTPException) as reused:
        _stop(sessions, session_id, reason="another reason")
    assert reused.value.status_code == 409
    # Another stop of the ended session changes nothing.
    other = _stop(sessions, session_id, key="stop-2", username="someone")
    assert other.outcome == "already_ended"
    assert other.session.stop is not None and other.session.stop.stopped_by == "tester"

    # Nothing new is authorized in it, a completion included.
    for kind in (AgentActionType.RUN_TASK, AgentActionType.COMPLETE_SESSION):
        with pytest.raises(HTTPException) as refused:
            _submit(sessions, session_id, f"after-{kind.value}", kind)
        assert refused.value.status_code == 409
        assert "not active: cancelled" in str(refused.value.detail)


def test_a_stop_of_a_paused_session_closes_its_question_and_no_resume_follows(
    sessions: AgentSessionService, interventions: AgentInterventionService
) -> None:
    session_id = _session(sessions)
    intervention_id = _pause(interventions, session_id)
    version = _state(session_id).state_version

    stopped = _stop(sessions, session_id)
    assert stopped.outcome == "stopped"
    assert stopped.session.stop is not None
    assert stopped.session.stop.status_before.value == "waiting_for_human"
    assert stopped.session.active_intervention_id is None
    assert stopped.closed_intervention_ids == [intervention_id]
    record = AgentInterventionDocument.find_one({"intervention_id": intervention_id}).run()
    assert record is not None and record.status.value == "stopped"
    assert record.events[-1].kind == "session_stopped"
    assert record.events[-1].actor == "tester"

    # The expert can no longer resume it, and no runner can claim a resume.
    with pytest.raises(HTTPException) as answered:
        interventions.respond(
            project_id=PROJECT,
            session_id=session_id,
            intervention_id=intervention_id,
            username="expert",
            body=RespondAgentInterventionRequest(
                idempotency_key="resume",
                expected_state_version=version,
                decision=AgentInterventionDecision.RESUME,
            ),
        )
    assert answered.value.status_code == 409
    with pytest.raises(HTTPException) as claimed:
        interventions.claim_resume(
            project_id=PROJECT,
            session_id=session_id,
            intervention_id=intervention_id,
            username="tester",
            body=ClaimAgentResumeRequest(claim_key="runner"),
        )
    assert claimed.value.status_code == 409
    assert _state(session_id).status.value == "cancelled"


def test_a_question_reopened_by_a_response_the_stop_beat_is_closed_on_the_next_read(
    sessions: AgentSessionService, interventions: AgentInterventionService
) -> None:
    session_id = _session(sessions)
    intervention_id = _pause(interventions, session_id)
    _stop(sessions, session_id)
    # A response that was being recorded lost the session to the stop and rolled back.
    AgentInterventionDocument.get_motor_collection().update_one(
        {"intervention_id": intervention_id}, {"$set": {"status": "open"}}
    )
    [item] = interventions.list_interventions(project_id=PROJECT, session_id=session_id).items
    assert item.status.value == "stopped"


def test_a_session_out_of_actions_can_still_be_completed_or_stopped(
    sessions: AgentSessionService,
) -> None:
    session_id = _session(sessions, max_actions=1)
    _authorize_run(sessions, session_id)
    assert _state(session_id).action_count == 1
    # Another measurement is refused for the budget; finishing is not.
    refused = _submit(sessions, session_id, "run-2", AgentActionType.RUN_TASK)
    assert refused.decision.value == "rejected"
    completed = _submit(sessions, session_id, "done", AgentActionType.COMPLETE_SESSION)
    assert completed.decision.value == "authorized"
    assert _state(session_id).status.value == "completed"
    # A stop of the completed session leaves it completed.
    assert _stop(sessions, session_id).outcome == "already_ended"
    assert _state(session_id).status.value == "completed"

    exhausted = _session(sessions, max_actions=1)
    _authorize_run(sessions, exhausted)
    assert _stop(sessions, exhausted).outcome == "stopped"


def test_an_expired_session_is_reported_as_ended_not_stopped(
    sessions: AgentSessionService,
) -> None:
    session_id = _session(sessions)
    AgentSessionDocument.get_motor_collection().update_one(
        {"session_id": session_id}, {"$set": {"expires_at": now() - timedelta(minutes=1)}}
    )
    result = _stop(sessions, session_id)
    assert result.outcome == "already_ended"
    assert result.session.status.value == "expired"
    assert result.session.stop is None
    assert result.session.end_notification is not None
    assert result.session.end_notification.event.value == "expired"


def test_a_stop_that_races_other_writes_retries_on_what_they_stored(
    sessions: AgentSessionService, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_id = _session(sessions)
    real = sessions._get_session_document
    raced: list[str] = []

    def submit_first(project_id: str, sid: str) -> Any:
        doc = real(project_id, sid)
        if not raced:
            # A measurement is authorized between the stop's read and its update.
            raced.append("racing")
            _authorize_run(sessions, session_id, key="racing")
        return doc

    monkeypatch.setattr(sessions, "_get_session_document", submit_first)
    stopped = _stop(sessions, session_id)
    assert stopped.outcome == "stopped"
    # The stop recorded the version it actually ended, after the racing submission.
    assert stopped.session.stop is not None
    assert stopped.session.stop.state_version == stopped.session.state_version == 2


@pytest.mark.asyncio
async def test_a_stop_that_wins_before_the_dispatch_gate_dispatches_nothing(
    sessions: AgentSessionService,
    catalog: TaskFileService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = _session(sessions)
    action_id = _authorize_run(sessions, session_id)
    real_gate = gate.pass_execution_gate
    reports: list[Any] = []

    def stop_first(project_id: str, sid: str) -> bool:
        # The action is reserved; the stop commits before this request reaches the gate.
        reports.append(_stop(sessions, session_id))
        return real_gate(project_id, sid)

    monkeypatch.setattr(session_service_module, "pass_execution_gate", stop_first)
    flow = FakeFlowService()
    with pytest.raises(HTTPException) as refused:
        await sessions.execute_action(
            project_id=PROJECT,
            session_id=session_id,
            action_id=action_id,
            body=ExecuteAgentActionRequest(),
            flow_service=cast("FlowService", flow),
            task_file_service=catalog,
        )
    assert refused.value.status_code == 409
    assert "cancelled" in str(refused.value.detail)
    assert flow.runs == []
    released = AgentActionDocument.find_one({"action_id": action_id}).run()
    assert released is not None and released.execution_status == "not_started"
    # The reservation was listed truthfully: it might still have passed the gate.
    [report] = reports
    assert [(op.kind, op.id, op.status) for op in report.in_flight] == [
        ("measurement", action_id, "dispatching")
    ]
    # Once released, nothing is in flight any more.
    assert _stop(sessions, session_id).in_flight == []


@pytest.mark.asyncio
async def test_a_dispatch_that_passed_the_gate_first_is_reported_not_cancelled(
    sessions: AgentSessionService, catalog: TaskFileService
) -> None:
    session_id = _session(sessions)
    action_id = _authorize_run(sessions, session_id)
    reports: list[Any] = []
    flow = FakeFlowService(during=lambda: reports.append(_stop(sessions, session_id)))

    dispatched = await sessions.execute_action(
        project_id=PROJECT,
        session_id=session_id,
        action_id=action_id,
        body=ExecuteAgentActionRequest(),
        flow_service=cast("FlowService", flow),
        task_file_service=catalog,
    )
    # The run was sent before the stop; the stop does not claim to have cancelled it.
    assert dispatched.execution_status == "queued"
    assert len(flow.runs) == 1
    [report] = reports
    assert report.outcome == "stopped"
    assert [(op.kind, op.id) for op in report.in_flight] == [("measurement", action_id)]
    readback = _stop(sessions, session_id)
    assert [(op.kind, op.id, op.status) for op in readback.in_flight] == [
        ("measurement", action_id, "queued")
    ]

    # Its result arrives, but nothing commits it in the stopped session.
    _completed_with_candidate(session_id, action_id)
    with pytest.raises(HTTPException) as refused:
        sessions.commit_action_candidate(
            project_id=PROJECT,
            session_id=session_id,
            action_id=action_id,
            parameter_name="drive_amplitude",
            username="tester",
            body=_commit_body(session_id),
        )
    assert refused.value.status_code == 409
    assert "cancelled" in str(refused.value.detail)
    assert _stop(sessions, session_id).in_flight == []
