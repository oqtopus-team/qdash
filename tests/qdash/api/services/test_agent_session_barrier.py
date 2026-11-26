"""Failure-injection tests for the agent-session execution barrier.

Each test stops a request at one persistence boundary (the request "crashes") or lets a
competing pause win between two steps of an operation, then checks that the session stays
paused, that no measurement, commit, or backend apply starts after the pause, and that a
retry recovers the same records without duplicates.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
from fastapi import HTTPException

import qdash.api.services.agent_session_gate as gate
import qdash.api.services.agent_session_service as session_service_module
from qdash.api.schemas.agent_session import (
    ApplyAgentCandidateRequest,
    CommitAgentCandidateRequest,
    CreateAgentInterventionRequest,
    CreateAgentSessionRequest,
    ExecuteAgentActionRequest,
    RespondAgentInterventionRequest,
    SubmitAgentActionRequest,
)
from qdash.api.schemas.task_file import ListTaskInfoResponse, TaskInfo
from qdash.api.services.agent_intervention_service import AgentInterventionService
from qdash.api.services.agent_intervention_slack import AgentInterventionSlackNotifier
from qdash.api.services.agent_session_service import AgentSessionService
from qdash.common.utils.datetime import now
from qdash.config import get_settings
from qdash.datamodel.agent_session import (
    AgentActionType,
    AgentInterventionDecision,
    AgentSessionPolicy,
    NumericBounds,
)
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.agent_session import (
    AgentActionDocument,
    AgentCandidateCommitDocument,
    AgentInterventionDocument,
    AgentSessionDocument,
)
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

if TYPE_CHECKING:
    from qdash.api.services.flow_service import FlowService
    from qdash.api.services.task_file_service import TaskFileService

PROJECT = "project-1"
TASK = "CheckQubitSpectroscopy"


class Crash(RuntimeError):
    """Stands for the API process dying at an injected point."""


class FakeSlack:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def chat_postMessage(self, *, channel: str, **kwargs: Any) -> dict[str, str]:
        self.calls.append({"channel": channel, **kwargs})
        return {"channel": channel, "ts": f"{len(self.calls)}.000"}


class FakeFlowService:
    """Counts every dispatch that reaches the workflow layer."""

    def __init__(self, during: Any = None) -> None:
        self.runs: list[dict[str, Any]] = []
        self.applies: list[dict[str, Any]] = []
        self._during = during

    async def execute_single_task_from_snapshot(self, **kwargs: Any) -> Any:
        self.runs.append(kwargs)
        if self._during is not None:
            self._during()
        return SimpleNamespace(execution_id="exec-run", flow_run_id=f"flow-{len(self.runs)}")

    async def execute_agent_candidate_apply(self, **kwargs: Any) -> Any:
        self.applies.append(kwargs)
        return SimpleNamespace(execution_id=f"apply-{len(self.applies)}")


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
    QubitDocument(
        project_id=PROJECT,
        username="tester",
        qid="Q00",
        chip_id="chip-001",
        data={},
        system_info=SystemInfoModel(),
    ).insert()
    ProjectDocument(
        project_id=PROJECT, name="Lab A", owner_user_id="u-1", owner_username="tester"
    ).insert()
    settings = get_settings().model_copy(
        update={
            "slack_bot_token": "xoxb-test",
            "slack_agent_notification": True,
            "slack_agent_channel_id": "C-agent",
        }
    )
    notifier = AgentInterventionSlackNotifier(settings=settings, client=slack)
    return AgentInterventionService(notifier=notifier)


@pytest.fixture
def sessions(interventions: AgentInterventionService) -> AgentSessionService:
    return AgentSessionService(intervention_service=interventions)


@pytest.fixture
def catalog(monkeypatch: pytest.MonkeyPatch) -> TaskFileService:
    monkeypatch.setattr("qdash.api.services.catalog_task_run.get_default_backend", lambda: "qubex")
    monkeypatch.setattr(
        "qdash.api.services.catalog_task_run.get_available_backends", lambda: ["qubex"]
    )
    monkeypatch.setattr(
        "qdash.api.services.catalog_task_run.is_task_available", lambda *_args: True
    )
    task = TaskInfo(
        name=TASK,
        class_name=TASK,
        task_type="qubit",
        file_path="qubex/check_qubit_spectroscopy.py",
        input_parameters={},
        run_parameters={},
    )
    return cast(
        "TaskFileService",
        SimpleNamespace(list_task_info=lambda *_a, **_k: ListTaskInfoResponse(tasks=[task])),
    )


# ---------------------------------------------------------------------- helpers


def _session(sessions: AgentSessionService, *, max_actions: int = 10) -> str:
    return sessions.create_session(
        project_id=PROJECT,
        username="tester",
        body=CreateAgentSessionRequest(
            chip_id="chip-001",
            policy=AgentSessionPolicy(
                qids=["Q00"],
                allowed_tasks=[TASK],
                allowed_overrides={"drive_amplitude": NumericBounds(minimum=0.0, maximum=1.0)},
                max_actions=max_actions,
            ),
            expires_in_seconds=3600,
        ),
    ).session_id


def _state(session_id: str) -> AgentSessionDocument:
    doc = AgentSessionDocument.find_one({"session_id": session_id}).run()
    assert doc is not None
    return doc


def _authorize_run(sessions: AgentSessionService, session_id: str, key: str = "run-1") -> str:
    return sessions.submit_action(
        project_id=PROJECT,
        session_id=session_id,
        body=SubmitAgentActionRequest(
            idempotency_key=key,
            expected_state_version=_state(session_id).state_version,
            action_type=AgentActionType.RUN_TASK,
            task_name=TASK,
            qids=["Q00"],
        ),
    ).action_id


def _request(key: str = "int-1", **overrides: Any) -> CreateAgentInterventionRequest:
    body: dict[str, Any] = {
        "idempotency_key": key,
        "reason": "unknown_outcome",
        "summary": "The spectroscopy peak is split",
        "question": "Which peak is f01?",
        "qids": ["Q00"],
    }
    body.update(overrides)
    return CreateAgentInterventionRequest.model_validate(body)


def _pause(interventions: AgentInterventionService, session_id: str, key: str = "int-1") -> str:
    return interventions.create_intervention(
        project_id=PROJECT, session_id=session_id, username="agent", body=_request(key)
    ).intervention_id


def _resume(interventions: AgentInterventionService, session_id: str, intervention_id: str) -> Any:
    return interventions.respond(
        project_id=PROJECT,
        session_id=session_id,
        intervention_id=intervention_id,
        username="expert",
        body=RespondAgentInterventionRequest(
            idempotency_key=f"resume-{intervention_id}",
            expected_state_version=_state(session_id).state_version,
            decision=AgentInterventionDecision.RESUME,
            guidance="Take the lower peak.",
        ),
    )


def _blockers(interventions: AgentInterventionService, session_id: str, iid: str) -> list[str]:
    return interventions.get_intervention(
        project_id=PROJECT, session_id=session_id, intervention_id=iid
    ).resume_blockers


def _crash_before_records_are_written(monkeypatch: pytest.MonkeyPatch) -> None:
    """The request dies right after the pausing session update is persisted."""

    def crash(doc: AgentSessionDocument) -> None:
        if doc.pending_intervention:
            raise Crash("after reservation")

    monkeypatch.setattr(gate, "materialize_pending_intervention", crash)


def _completed_with_candidate(session_id: str, action_id: str) -> None:
    AgentActionDocument.get_motor_collection().update_one(
        {"action_id": action_id},
        {
            "$set": {
                "execution_status": "completed",
                "execution_id": "execution-1",
                "operation_id": "operation-1",
            }
        },
    )
    TaskResultHistoryDocument(
        project_id=PROJECT,
        username="tester",
        task_id="task-result-1",
        name=TASK,
        upstream_id="",
        status="completed",
        message="completed",
        input_parameters={},
        output_parameters={"drive_amplitude": {"value": 0.12}},
        output_parameter_names=["drive_amplitude"],
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
        execution_id="execution-1",
        tags=[f"agent-session:{session_id}"],
        chip_id="chip-001",
    ).insert()


def _commit_body(session_id: str, key: str = "commit-1") -> CommitAgentCandidateRequest:
    return CommitAgentCandidateRequest(
        idempotency_key=key,
        expected_state_version=_state(session_id).state_version,
        task_id="task-result-1",
    )


def _qubit_data() -> dict[str, Any]:
    qubit = QubitDocument.find_one({"project_id": PROJECT, "qid": "Q00"}).run()
    assert qubit is not None
    return dict(qubit.data)


# ---------------------------------------------------------------------- pause boundaries


@pytest.mark.asyncio
async def test_crash_after_the_pause_keeps_every_gate_closed_and_a_retry_recovers_the_record(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    catalog: TaskFileService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = _session(sessions)
    queued_run = _authorize_run(sessions, session_id, "run-1")
    measured_run = _authorize_run(sessions, session_id, "run-0")
    _completed_with_candidate(session_id, measured_run)
    budget_before = _state(session_id).action_count

    with monkeypatch.context() as crashing:
        _crash_before_records_are_written(crashing)
        with pytest.raises(Crash):
            _pause(interventions, session_id)

        # The pause is durable even though the record was never written.
        paused = _state(session_id)
        assert paused.status.value == "waiting_for_human"
        assert paused.active_intervention_id is not None
        assert paused.pending_intervention is not None
        assert AgentInterventionDocument.count() == 0
        # The execution gate is already closed while the record is missing.
        assert gate.pass_execution_gate(PROJECT, session_id) is False

    # The retry returns the record the pause points to, written once.
    retried = interventions.create_intervention(
        project_id=PROJECT, session_id=session_id, username="agent", body=_request()
    )
    assert retried.intervention_id == paused.active_intervention_id
    assert retried.pauses_session is True
    assert AgentInterventionDocument.count() == 1
    again = interventions.create_intervention(
        project_id=PROJECT, session_id=session_id, username="agent", body=_request()
    )
    assert again.intervention_id == retried.intervention_id
    assert AgentInterventionDocument.count() == 1
    assert _state(session_id).pending_intervention is None

    # Every gate that needs an active session refuses, and nothing reaches the workflow.
    flow = FakeFlowService()
    with pytest.raises(HTTPException) as dispatch:
        await sessions.execute_action(
            project_id=PROJECT,
            session_id=session_id,
            action_id=queued_run,
            body=ExecuteAgentActionRequest(),
            flow_service=cast("FlowService", flow),
            task_file_service=catalog,
        )
    assert dispatch.value.status_code == 409
    with pytest.raises(HTTPException):
        _authorize_run(sessions, session_id, "run-2")
    with pytest.raises(HTTPException):
        sessions.commit_action_candidate(
            project_id=PROJECT,
            session_id=session_id,
            action_id=measured_run,
            parameter_name="drive_amplitude",
            username="agent",
            body=_commit_body(session_id),
        )
    assert flow.runs == []
    assert _qubit_data() == {}
    assert AgentCandidateCommitDocument.count() == 0
    assert _state(session_id).action_count == budget_before


def test_the_notification_sweep_writes_and_notifies_a_pause_whose_request_crashed(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    slack: FakeSlack,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = _session(sessions)
    with monkeypatch.context() as crashing:
        _crash_before_records_are_written(crashing)
        with pytest.raises(Crash):
            _pause(interventions, session_id)

    interventions.retry_due_notifications()

    paused = _state(session_id)
    assert paused.pending_intervention is None
    record = AgentInterventionDocument.find_one(
        {"intervention_id": paused.active_intervention_id}
    ).run()
    assert record is not None
    assert record.notification.status.value == "sent"
    assert len(slack.calls) == 1


def test_crash_after_the_record_is_written_keeps_the_pause_and_never_duplicates(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = _session(sessions)

    def crash(_doc: AgentSessionDocument, _intervention_id: str) -> None:
        raise Crash("after incident persistence")

    with monkeypatch.context() as crashing:
        crashing.setattr(gate, "_clear_pending", crash)
        with pytest.raises(Crash):
            _pause(interventions, session_id)
        assert AgentInterventionDocument.count() == 1
        assert _state(session_id).pending_intervention is not None

    # Long after the crash, reads still treat the record as the pause (not as unpaused).
    AgentInterventionDocument.get_motor_collection().update_many(
        {}, {"$set": {"created_at": now() - timedelta(hours=1)}}
    )
    record = AgentInterventionDocument.find_one({}).run()
    assert record is not None
    read = interventions.get_intervention(
        project_id=PROJECT, session_id=session_id, intervention_id=record.intervention_id
    )
    assert read.pauses_session is True
    assert read.status.value == "open"
    assert read.session_status.value == "waiting_for_human"

    retried = interventions.create_intervention(
        project_id=PROJECT, session_id=session_id, username="agent", body=_request()
    )
    assert retried.intervention_id == record.intervention_id
    assert AgentInterventionDocument.count() == 1
    assert _state(session_id).pending_intervention is None
    # And the expert can answer it: the pause is finished, not abandoned.
    assert _resume(interventions, session_id, record.intervention_id).status.value == "resumed"
    assert _state(session_id).status.value == "active"


def test_crash_after_a_request_human_pause_recovers_both_records_on_retry(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = _session(sessions)
    body = SubmitAgentActionRequest(
        idempotency_key="human-1",
        expected_state_version=0,
        action_type=AgentActionType.REQUEST_HUMAN,
        diagnosis="The resonator moved by 5 MHz.",
    )
    with monkeypatch.context() as crashing:
        _crash_before_records_are_written(crashing)
        with pytest.raises(Crash):
            sessions.submit_action(project_id=PROJECT, session_id=session_id, body=body)
    assert _state(session_id).status.value == "waiting_for_human"
    assert AgentActionDocument.count() == 0

    first = sessions.submit_action(project_id=PROJECT, session_id=session_id, body=body)
    second = sessions.submit_action(project_id=PROJECT, session_id=session_id, body=body)

    assert first.action_id == second.action_id
    assert first.intervention_id == _state(session_id).active_intervention_id
    assert AgentActionDocument.count() == 1
    assert AgentInterventionDocument.count() == 1
    # Asking for a person used no measurement budget.
    assert _state(session_id).action_count == 0


def test_a_pending_pause_on_a_session_that_then_expired_is_recorded_as_not_resumable(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = _session(sessions)
    with monkeypatch.context() as crashing:
        _crash_before_records_are_written(crashing)
        with pytest.raises(Crash):
            _pause(interventions, session_id)
    AgentSessionDocument.get_motor_collection().update_one(
        {"session_id": session_id}, {"$set": {"expires_at": now() - timedelta(seconds=1)}}
    )

    listed = interventions.list_interventions(project_id=PROJECT, session_id=session_id)

    assert listed.total == 1
    assert listed.items[0].session_status.value == "expired"
    assert listed.items[0].can_resume is False


def test_same_key_requests_that_race_for_the_pause_return_one_record(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A request that read the session as active loses the pause to a concurrent one."""
    session_id = _session(sessions)
    validate = interventions._validate_references
    raced: list[str] = []
    started: list[bool] = []

    def concurrent_request_wins(session: Any, body: Any) -> None:
        validate(session, body)
        if not started:
            started.append(True)
            raced.append(_pause(interventions, session_id, body.idempotency_key))

    monkeypatch.setattr(interventions, "_validate_references", concurrent_request_wins)
    loser = interventions.create_intervention(
        project_id=PROJECT, session_id=session_id, username="agent", body=_request()
    )

    assert loser.intervention_id == raced[0]
    assert AgentInterventionDocument.count() == 1

    monkeypatch.setattr(interventions, "_validate_references", validate)
    with pytest.raises(HTTPException) as other:
        interventions.create_intervention(
            project_id=PROJECT, session_id=session_id, username="agent", body=_request("int-2")
        )
    assert other.value.status_code == 409
    assert AgentInterventionDocument.count() == 1


# ---------------------------------------------------------------------- dispatch races


@pytest.mark.asyncio
async def test_a_pause_that_wins_before_the_dispatch_gate_stops_the_dispatch(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    catalog: TaskFileService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = _session(sessions)
    action_id = _authorize_run(sessions, session_id)
    before = _state(session_id)
    real_gate = gate.pass_execution_gate
    paused: list[str] = []

    def pause_first(project_id: str, sid: str) -> bool:
        # The action is reserved; a pause commits before this request reaches the gate.
        reserved = AgentActionDocument.find_one({"action_id": action_id}).run()
        assert reserved is not None
        assert reserved.execution_status == "dispatching"
        paused.append(_pause(interventions, session_id))
        assert any("being dispatched" in b for b in _blockers(interventions, sid, paused[0]))
        return real_gate(project_id, sid)

    monkeypatch.setattr(session_service_module, "pass_execution_gate", pause_first)
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
    assert "waiting_for_human" in str(refused.value.detail)
    assert flow.runs == []
    released = AgentActionDocument.find_one({"action_id": action_id}).run()
    assert released is not None
    assert released.execution_status == "not_started"
    assert _blockers(interventions, session_id, paused[0]) == []

    # The resume reactivates the same grant: same budget, policy, and expiry.
    monkeypatch.setattr(session_service_module, "pass_execution_gate", real_gate)
    _resume(interventions, session_id, paused[0])
    after = _state(session_id)
    assert after.status.value == "active"
    assert after.action_count == before.action_count
    assert after.policy == before.policy
    assert after.expires_at == before.expires_at
    dispatched = await sessions.execute_action(
        project_id=PROJECT,
        session_id=session_id,
        action_id=action_id,
        body=ExecuteAgentActionRequest(),
        flow_service=cast("FlowService", flow),
        task_file_service=catalog,
    )
    assert dispatched.execution_status == "queued"
    assert len(flow.runs) == 1


@pytest.mark.asyncio
async def test_a_dispatch_that_passed_the_gate_first_blocks_resume_until_it_settles(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    catalog: TaskFileService,
) -> None:
    session_id = _session(sessions)
    action_id = _authorize_run(sessions, session_id)
    paused: list[str] = []
    flow = FakeFlowService(during=lambda: paused.append(_pause(interventions, session_id)))

    dispatched = await sessions.execute_action(
        project_id=PROJECT,
        session_id=session_id,
        action_id=action_id,
        body=ExecuteAgentActionRequest(),
        flow_service=cast("FlowService", flow),
        task_file_service=catalog,
    )

    # The pause does not claim to stop a run that was already sent.
    assert dispatched.execution_status == "queued"
    assert len(flow.runs) == 1
    blockers = _blockers(interventions, session_id, paused[0])
    assert any("still running" in blocker for blocker in blockers)
    with pytest.raises(HTTPException) as refused:
        _resume(interventions, session_id, paused[0])
    assert "still running" in str(refused.value.detail)

    AgentActionDocument.get_motor_collection().update_one(
        {"action_id": action_id}, {"$set": {"execution_status": "completed"}}
    )
    assert _resume(interventions, session_id, paused[0]).status.value == "resumed"


@pytest.mark.asyncio
async def test_a_slow_dispatch_whose_reservation_was_released_never_runs(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    catalog: TaskFileService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A request stalls past the abandonment timeout between reservation and gate."""
    session_id = _session(sessions)
    action_id = _authorize_run(sessions, session_id)
    real_gate = gate.pass_execution_gate

    def stall(project_id: str, sid: str) -> bool:
        AgentActionDocument.get_motor_collection().update_one(
            {"action_id": action_id},
            {"$set": {"dispatch_reserved_at": now() - timedelta(minutes=5)}},
        )
        # Another worker treats the stalled reservation as abandoned.
        gate.release_abandoned_reservations(project_id, sid)
        return real_gate(project_id, sid)

    monkeypatch.setattr(session_service_module, "pass_execution_gate", stall)
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

    assert "released as abandoned" in str(refused.value.detail)
    assert flow.runs == []


def test_a_crashed_dispatch_is_released_only_before_it_passed_the_gate(
    sessions: AgentSessionService, interventions: AgentInterventionService
) -> None:
    session_id = _session(sessions)
    unconfirmed = _authorize_run(sessions, session_id, "run-1")
    confirmed = _authorize_run(sessions, session_id, "run-2")
    stale = now() - timedelta(minutes=5)
    for action_id, passed in ((unconfirmed, False), (confirmed, True)):
        AgentActionDocument.get_motor_collection().update_one(
            {"action_id": action_id},
            {
                "$set": {
                    "execution_status": "dispatching",
                    "dispatch_token": "t",
                    "dispatch_confirmed": passed,
                    "dispatch_reserved_at": stale,
                }
            },
        )
    iid = _pause(interventions, session_id)

    blockers = _blockers(interventions, session_id, iid)

    released = AgentActionDocument.find_one({"action_id": unconfirmed}).run()
    assert released is not None
    assert released.execution_status == "not_started"
    # A dispatch that may have started is never assumed to have stopped.
    assert len(blockers) == 1
    assert confirmed in blockers[0]
    stopped = interventions.respond(
        project_id=PROJECT,
        session_id=session_id,
        intervention_id=iid,
        username="expert",
        body=RespondAgentInterventionRequest(
            idempotency_key="stop",
            expected_state_version=_state(session_id).state_version,
            decision=AgentInterventionDecision.STOP,
        ),
    )
    assert stopped.status.value == "stopped"


# ---------------------------------------------------------------------- commit races


def test_a_pause_between_the_commit_check_and_its_reservation_persists_nothing(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = _session(sessions)
    action_id = _authorize_run(sessions, session_id)
    _completed_with_candidate(session_id, action_id)
    body = _commit_body(session_id)
    candidates = sessions.list_action_candidates

    def pause_after_check(**kwargs: Any) -> Any:
        result = candidates(**kwargs)
        _pause(interventions, session_id)
        return result

    monkeypatch.setattr(sessions, "list_action_candidates", pause_after_check)
    with pytest.raises(HTTPException) as refused:
        sessions.commit_action_candidate(
            project_id=PROJECT,
            session_id=session_id,
            action_id=action_id,
            parameter_name="drive_amplitude",
            username="agent",
            body=body,
        )

    assert refused.value.status_code == 409
    assert _qubit_data() == {}
    assert AgentCandidateCommitDocument.count() == 0
    assert _state(session_id).status.value == "waiting_for_human"


def test_a_commit_reserved_before_the_pause_finishes_and_blocks_resume_meanwhile(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = _session(sessions)
    action_id = _authorize_run(sessions, session_id)
    _completed_with_candidate(session_id, action_id)
    from qdash.dbmodel.agent_parameter_state import compare_and_set_parameter as write

    seen: list[list[str]] = []

    def pause_during_write(**kwargs: Any) -> Any:
        iid = _pause(interventions, session_id)
        seen.append(_blockers(interventions, session_id, iid))
        return write(**kwargs)

    monkeypatch.setattr(
        "qdash.api.services.agent_candidate_commit.compare_and_set_parameter", pause_during_write
    )
    committed = sessions.commit_action_candidate(
        project_id=PROJECT,
        session_id=session_id,
        action_id=action_id,
        parameter_name="drive_amplitude",
        username="agent",
        body=_commit_body(session_id),
    )

    assert committed.status == "committed"
    assert any("calibration commit" in blocker for blocker in seen[0])
    iid = _state(session_id).active_intervention_id
    assert iid is not None
    assert _blockers(interventions, session_id, iid) == []


def test_an_abandoned_commit_reservation_is_released_as_failed(
    sessions: AgentSessionService, interventions: AgentInterventionService
) -> None:
    session_id = _session(sessions)
    AgentCandidateCommitDocument(
        commit_id="c-stale",
        session_id=session_id,
        action_id="a",
        project_id=PROJECT,
        idempotency_key="commit-stale",
        request_hash="h",
        execution_id="e",
        task_id="t",
        task_name=TASK,
        qid="Q00",
        parameter_name="drive_amplitude",
        value=0.1,
        status="reserving",
        committed_by="agent",
        state_version_before=0,
        state_version_after=1,
        created_at=now() - timedelta(minutes=5),
    ).insert()
    iid = _pause(interventions, session_id)

    assert _blockers(interventions, session_id, iid) == []
    stale = AgentCandidateCommitDocument.find_one({"commit_id": "c-stale"}).run()
    assert stale is not None
    assert stale.status == "failed"
    assert _qubit_data() == {}


@pytest.mark.asyncio
async def test_a_pause_before_the_backend_apply_gate_restores_the_apply_state(
    sessions: AgentSessionService,
    interventions: AgentInterventionService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = _session(sessions)
    action_id = _authorize_run(sessions, session_id)
    _completed_with_candidate(session_id, action_id)
    commit = sessions.commit_action_candidate(
        project_id=PROJECT,
        session_id=session_id,
        action_id=action_id,
        parameter_name="drive_amplitude",
        username="agent",
        body=_commit_body(session_id),
    )
    real_gate = gate.pass_execution_gate
    paused: list[str] = []

    def pause_first(project_id: str, sid: str) -> bool:
        paused.append(_pause(interventions, sid))
        return real_gate(project_id, sid)

    monkeypatch.setattr(session_service_module, "pass_execution_gate", pause_first)
    flow = FakeFlowService()
    body = ApplyAgentCandidateRequest(
        idempotency_key="apply-1",
        expected_state_version=_state(session_id).state_version,
    )
    with pytest.raises(HTTPException) as refused:
        await sessions.apply_candidate_to_backend(
            project_id=PROJECT,
            session_id=session_id,
            commit_id=commit.commit_id,
            body=body,
            flow_service=cast("FlowService", flow),
        )

    assert refused.value.status_code == 409
    assert flow.applies == []
    restored = AgentCandidateCommitDocument.find_one({"commit_id": commit.commit_id}).run()
    assert restored is not None
    assert restored.backend_status == "not_started"
    assert restored.backend_apply_idempotency_key is None

    monkeypatch.setattr(session_service_module, "pass_execution_gate", real_gate)
    _resume(interventions, session_id, paused[0])
    queued = await sessions.apply_candidate_to_backend(
        project_id=PROJECT,
        session_id=session_id,
        commit_id=commit.commit_id,
        body=body.model_copy(update={"expected_state_version": _state(session_id).state_version}),
        flow_service=cast("FlowService", flow),
    )
    assert queued.backend_status == "queued"
    assert len(flow.applies) == 1
    # A queued apply blocks the resume of a later pause until the worker settles it.
    iid = _pause(interventions, session_id, "int-2")
    assert any("backend apply" in b for b in _blockers(interventions, session_id, iid))
