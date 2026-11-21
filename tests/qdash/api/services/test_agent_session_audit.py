"""Tests for the chronological experiment audit of an agent session.

The audit is read from QDash's authoritative records; the only new records are agent
decisions, which are append-only, idempotent, validated against the session, and freeze
QDash's reading of the evidence they cite.
"""

from __future__ import annotations

import base64
from datetime import timedelta
from typing import TYPE_CHECKING, Any, cast

import pytest
from fastapi import HTTPException

from qdash.api.schemas.agent_session import (
    ApplyAgentCandidateRequest,
    CommitAgentCandidateRequest,
    CreateAgentInterventionRequest,
    CreateAgentSessionRequest,
    RecordAgentDecisionRequest,
    RespondAgentInterventionRequest,
    SubmitAgentActionRequest,
)
from qdash.api.services.agent_intervention_service import AgentInterventionService
from qdash.api.services.agent_session_audit import AgentSessionAuditService
from qdash.api.services.agent_session_service import AgentSessionService
from qdash.common.utils.datetime import now
from qdash.datamodel.agent_session import (
    AgentActionDecision,
    AgentActionType,
    AgentAutonomy,
    AgentSessionPolicy,
    NumericBounds,
)
from qdash.datamodel.evaluation import EvaluationOutputModel
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.agent_session import (
    AgentActionDocument,
    AgentCandidateCommitDocument,
    AgentDecisionDocument,
    AgentSessionDocument,
)
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.evaluation import EvaluationDocument
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

if TYPE_CHECKING:
    from qdash.api.schemas.agent_session import AgentSessionAuditResponse
    from qdash.api.services.flow_service import FlowService

PROJECT = "project-1"
OWNER = "alice"


@pytest.fixture
def sessions(init_db) -> AgentSessionService:
    """A session service with a chip and qubit in the active test database."""
    for project_id in (PROJECT, "project-2"):
        ChipDocument(
            project_id=project_id,
            chip_id="chip-001",
            username=OWNER,
            size=4,
            system_info=SystemInfoModel(),
        ).insert()
    QubitDocument(
        project_id=PROJECT,
        username=OWNER,
        qid="Q00",
        chip_id="chip-001",
        data={"qubit_frequency": {"value": 5.0, "unit": "GHz"}},
        system_info=SystemInfoModel(),
    ).insert()
    return AgentSessionService(intervention_service=AgentInterventionService())


@pytest.fixture
def audit() -> AgentSessionAuditService:
    return AgentSessionAuditService()


def _session(
    sessions: AgentSessionService,
    *,
    project_id: str = PROJECT,
    skill_name: str = "",
    skill_version: str = "",
    model_name: str = "",
):
    return sessions.create_session(
        project_id=project_id,
        username=OWNER,
        body=CreateAgentSessionRequest(
            chip_id="chip-001",
            policy=AgentSessionPolicy(
                qids=["Q00"],
                allowed_tasks=["CheckQubitFrequency", "CheckRabi"],
                allowed_overrides={"qubit_frequency": NumericBounds(minimum=4.0, maximum=6.0)},
                quality_gates={"r2": NumericBounds(minimum=0.9)},
                autonomy=AgentAutonomy.AUTO,
                max_actions=20,
                max_rounds_per_target=10,
            ),
            skill_name=skill_name,
            skill_version=skill_version,
            model_name=model_name,
        ),
    )


def _submit(
    sessions: AgentSessionService,
    session_id: str,
    *,
    key: str,
    task: str = "CheckQubitFrequency",
    qids: list[str] | None = None,
    overrides: dict[str, float] | None = None,
    project_id: str = PROJECT,
):
    version = sessions.get_session(project_id=project_id, session_id=session_id).state_version
    return sessions.submit_action(
        project_id=project_id,
        session_id=session_id,
        username=OWNER,
        body=SubmitAgentActionRequest(
            idempotency_key=key,
            expected_state_version=version,
            action_type=AgentActionType.RUN_TASK,
            task_name=task,
            qids=qids or ["Q00"],
            parameter_overrides=overrides or {},
            diagnosis=f"Measure {task} to locate the next value.",
        ),
    )


def _finish(
    session_id: str,
    action_id: str,
    *,
    sequence: int,
    task: str = "CheckQubitFrequency",
    status: str = "completed",
    outputs: dict[str, Any] | None = None,
    metrics: dict[str, float] | None = None,
    project_id: str = PROJECT,
) -> str:
    """Give an action an execution and a task result, as the workflow would."""
    action = AgentActionDocument.find_one({"session_id": session_id, "action_id": action_id}).run()
    assert action is not None
    started = now()
    action.operation_id = f"flow-run-{sequence}"
    action.execution_status = "queued"
    action.dispatch_reserved_at = started
    action.save()
    ExecutionHistoryDocument(
        project_id=project_id,
        username=OWNER,
        name=f"agent:{task}",
        execution_id=f"execution-{sequence}",
        calib_data_path="",
        note={"flow_run_id": f"flow-run-{sequence}"},
        status=status,
        tags=[f"agent-session:{session_id}"],
        chip_id="chip-001",
        start_at=started,
        end_at=started + timedelta(seconds=5),
        message="",
        system_info=SystemInfoModel(),
    ).insert()
    task_id = f"task-{sequence}"
    TaskResultHistoryDocument(
        project_id=project_id,
        username=OWNER,
        task_id=task_id,
        name=task,
        upstream_id="",
        status=status,
        message="fit failed" if status == "failed" else "completed",
        input_parameters={"qubit_frequency": {"value": 5.0, "unit": "GHz"}},
        output_parameters=outputs or {},
        output_parameter_names=list(outputs or {}),
        run_parameters={},
        quality_metrics=metrics or {},
        note={},
        figure_path=["/data/fig.png"],
        json_figure_path=["/data/fig.json"],
        raw_data_path=["/data/raw.npy"],
        start_at=started,
        end_at=started + timedelta(seconds=5),
        elapsed_time=5.0,
        task_type="qubit",
        system_info=SystemInfoModel(),
        qid="Q00",
        execution_id=f"execution-{sequence}",
        tags=[],
        chip_id="chip-001",
    ).insert()
    return task_id


def _decision(
    audit: AgentSessionAuditService,
    session_id: str,
    *,
    key: str,
    username: str = OWNER,
    project_id: str = PROJECT,
    **fields: Any,
):
    body = {
        "idempotency_key": key,
        "assessment": "pass",
        "interpretation": "The peak is clear and R2 0.98 passes the task knowledge's criterion.",
        "next_action": "next_task",
        **fields,
    }
    return audit.record_decision(
        project_id=project_id,
        session_id=session_id,
        username=username,
        body=RecordAgentDecisionRequest.model_validate(body),
    )


def _kinds(audit_response: AgentSessionAuditResponse) -> list[str]:
    return [event.kind for event in audit_response.events]


def _event(audit_response: AgentSessionAuditResponse, event_id: str):
    return next(event for event in audit_response.events if event.event_id == event_id)


@pytest.mark.asyncio
async def test_measurement_decision_commit_and_dependent_step_form_one_timeline(
    sessions: AgentSessionService, audit: AgentSessionAuditService
) -> None:
    """Intent, parameters, results, gates, decision, commit, apply, and the next step."""
    session = _session(
        sessions, skill_name="qdash-agent-calibration", skill_version="0.9.0", model_name="m-1"
    )
    first = _submit(sessions, session.session_id, key="a-1", overrides={"qubit_frequency": 5.1})
    task_id = _finish(
        session.session_id,
        first.action_id,
        sequence=1,
        outputs={"qubit_frequency": {"value": 5.12, "error": 0.001, "unit": "GHz"}},
        metrics={"r2": 0.98},
    )
    EvaluationDocument(
        evaluation_id="ev-1",
        run_id="run-1",
        project_id=PROJECT,
        chip_id="chip-001",
        task_id=task_id,
        task_name="CheckQubitFrequency",
        qid="Q00",
        execution_id="execution-1",
        status="completed",
        output=EvaluationOutputModel(model="provider/judge", diagnosis={"status": "SUCCESS"}),
    ).insert()

    decided = _decision(
        audit,
        session.session_id,
        key="d-1",
        evidence_action_ids=[first.action_id],
        evaluation_ids=["ev-1"],
        next_action="propose_commit",
        next_detail="Commit qubit_frequency before CheckRabi",
    )
    snapshot = decided.evidence_snapshot["actions"][0]
    assert snapshot["task_id"] == task_id
    assert snapshot["outputs"]["qubit_frequency"] == {
        "value": 5.12,
        "unit": "GHz",
        "error": 0.001,
    }
    assert snapshot["requested_overrides"] == {"qubit_frequency": 5.1}
    assert snapshot["effective_inputs"]["qubit_frequency"]["value"] == 5.0
    assert snapshot["gate"][0]["accepted"] is True
    assert snapshot["artifacts"]["figures"] == 1
    assert "/data" not in str(snapshot)  # storage paths stay out of the audit
    assert decided.evidence_snapshot["evaluations"][0]["diagnosis"] == {"status": "SUCCESS"}

    commit = sessions.commit_action_candidate(
        project_id=PROJECT,
        session_id=session.session_id,
        action_id=first.action_id,
        parameter_name="qubit_frequency",
        username=OWNER,
        body=CommitAgentCandidateRequest(
            idempotency_key="c-1",
            expected_state_version=sessions.get_session(
                project_id=PROJECT, session_id=session.session_id
            ).state_version,
            task_id=task_id,
        ),
    )

    class FakeFlowService:
        async def execute_agent_candidate_apply(self, **_kwargs: object) -> object:
            return type("Operation", (), {"execution_id": "apply-op-1"})()

    await sessions.apply_candidate_to_backend(
        project_id=PROJECT,
        session_id=session.session_id,
        commit_id=commit.commit_id,
        body=ApplyAgentCandidateRequest(
            idempotency_key="apply-1",
            expected_state_version=sessions.get_session(
                project_id=PROJECT, session_id=session.session_id
            ).state_version,
        ),
        flow_service=cast("FlowService", FakeFlowService()),
    )
    dependent = _submit(sessions, session.session_id, key="a-2", task="CheckRabi")
    _decision(
        audit,
        session.session_id,
        key="d-2",
        evidence_action_ids=[first.action_id],
        next_action="next_task",
        next_detail="CheckRabi on Q00 with the committed frequency",
        next_action_id=dependent.action_id,
    )

    result = audit.export_audit(project_id=PROJECT, session_id=session.session_id)

    assert result.schema_version == "qdash.agent-session-audit.v1"
    assert result.complete is True
    assert result.session.missing == ["skill_hash"]
    assert result.session.model_name == "m-1"
    ids = [event.event_id for event in result.events]
    # Stored times have millisecond precision, so records written in the same millisecond
    # (the apply and the next proposal here) may share a timestamp; causal pairs still order.
    expected_order = [
        "session_created:" + session.session_id,
        f"action_proposed:{first.action_id}",
        f"measurement:{first.action_id}",
        "evaluation:ev-1",
        f"decision:{decided.decision_id}",
        f"candidate_commit:{commit.commit_id}",
        f"backend_apply:{commit.commit_id}",
    ]
    assert [ids.index(event_id) for event_id in expected_order] == sorted(
        ids.index(event_id) for event_id in expected_order
    )
    assert ids.index(f"action_proposed:{dependent.action_id}") > ids.index(
        f"candidate_commit:{commit.commit_id}"
    )
    assert sorted(_kinds(result)) == sorted(
        [
            "session_created",
            "action_proposed",
            "measurement",
            "evaluation",
            "decision",
            "candidate_commit",
            "backend_apply",
            "action_proposed",
            "decision",
        ]
    )
    assert [event.sequence for event in result.events] == list(range(9))
    proposed = _event(result, f"action_proposed:{first.action_id}")
    assert proposed.actor == OWNER
    assert proposed.data["intent"] == "Measure CheckQubitFrequency to locate the next value."
    assert proposed.data["agent_reported_fields"] == ["intent"]
    measurement = _event(result, f"measurement:{first.action_id}")
    assert measurement.provenance == "server_record"
    assert measurement.status == "completed"
    assert measurement.execution_id == "execution-1"
    assert measurement.missing == []
    assert measurement.data["quality_metrics"] == {"r2": 0.98}
    committed = _event(result, f"candidate_commit:{commit.commit_id}")
    assert committed.status == "committed"
    assert committed.data["before_value"] == 5.0
    assert committed.data["after_value"] == 5.12
    applied = _event(result, f"backend_apply:{commit.commit_id}")
    assert applied.status == "queued"
    assert applied.status_is_current is True
    decision_event = result.events[-1]
    assert decision_event.provenance == "agent_reported"
    assert decision_event.data["next_action_id"] == dependent.action_id
    # The dependent step has not run, so it has no measurement event.
    assert f"measurement:{dependent.action_id}" not in {e.event_id for e in result.events}


def test_rejected_and_failed_measurements_are_reported_as_they_happened(
    sessions: AgentSessionService, audit: AgentSessionAuditService
) -> None:
    """A scope rejection is not an execution, and a failed run without a decision says so."""
    session = _session(sessions)
    rejected = _submit(sessions, session.session_id, key="a-out", qids=["Q09"])
    assert rejected.decision == AgentActionDecision.REJECTED
    failed = _submit(sessions, session.session_id, key="a-fail")
    _finish(session.session_id, failed.action_id, sequence=1, status="failed")

    before = audit.export_audit(project_id=PROJECT, session_id=session.session_id)
    rejected_event = _event(before, f"action_proposed:{rejected.action_id}")
    assert "not executed" in rejected_event.summary
    assert rejected_event.status == "rejected"
    assert f"measurement:{rejected.action_id}" not in {e.event_id for e in before.events}
    failed_event = _event(before, f"measurement:{failed.action_id}")
    assert failed_event.status == "failed"
    assert failed_event.data["gate"] == []
    assert failed_event.missing == ["decision"]

    escalation = _decision(
        audit,
        session.session_id,
        key="d-fail",
        assessment="fail",
        interpretation="The fit failed; the task knowledge has no recovery for this message.",
        evidence_action_ids=[failed.action_id, rejected.action_id],
        next_action="request_human",
    )
    assert [item["decision"] for item in escalation.evidence_snapshot["actions"]] == [
        "authorized",
        "rejected",
    ]
    after = audit.export_audit(project_id=PROJECT, session_id=session.session_id)
    assert _event(after, f"measurement:{failed.action_id}").missing == []


def test_dispatch_error_text_is_not_copied_into_the_audit(
    sessions: AgentSessionService, audit: AgentSessionAuditService
) -> None:
    session = _session(sessions)
    action = _submit(sessions, session.session_id, key="a-1")
    AgentActionDocument.get_motor_collection().update_one(
        {"action_id": action.action_id},
        {
            "$set": {
                "execution_status": "failed",
                "operation_id": None,
                "dispatch_reserved_at": now(),
                "metadata.execution_error": "connect to http://user:secret@prefect failed",
            }
        },
    )
    # A dispatch that failed before an operation existed has no measurement to show.
    result = audit.export_audit(project_id=PROJECT, session_id=session.session_id)
    assert "secret" not in result.model_dump_json()


def test_request_human_response_and_continuation_survive_a_restart(
    sessions: AgentSessionService, audit: AgentSessionAuditService
) -> None:
    """The question, the expert's answer, and the step after it are read back from QDash."""
    session = _session(sessions)
    first = _submit(sessions, session.session_id, key="a-1")
    _finish(session.session_id, first.action_id, sequence=1, outputs={}, metrics={"r2": 0.4})
    opened = sessions.interventions.create_intervention(
        project_id=PROJECT,
        session_id=session.session_id,
        username=OWNER,
        body=CreateAgentInterventionRequest.model_validate(
            {
                "idempotency_key": "human-1",
                "reason": "evaluation_failed",
                "summary": "R2 0.4 is below the criterion; no documented recovery.",
                "question": "Widen the sweep or stop?",
                "qids": ["Q00"],
                "attempts": [{"action_id": first.action_id, "task_name": "CheckQubitFrequency"}],
                "autonomous": True,
            }
        ),
    )
    # The decision is recorded while the session is paused; that changes no session state.
    paused = sessions.get_session(project_id=PROJECT, session_id=session.session_id)
    _decision(
        audit,
        session.session_id,
        key="d-1",
        assessment="fail",
        evidence_action_ids=[first.action_id],
        next_action="request_human",
        intervention_id=opened.intervention_id,
    )
    assert (
        sessions.get_session(project_id=PROJECT, session_id=session.session_id).state_version
        == paused.state_version
    )
    sessions.interventions.respond(
        project_id=PROJECT,
        session_id=session.session_id,
        intervention_id=opened.intervention_id,
        username="expert",
        body=RespondAgentInterventionRequest.model_validate(
            {
                "idempotency_key": "r-1",
                "expected_state_version": paused.state_version,
                "decision": "resume",
                "guidance": "Widen the sweep by 50 MHz.",
            }
        ),
    )
    retry = _submit(sessions, session.session_id, key="a-2", overrides={"qubit_frequency": 5.05})

    # A restarted pi has nothing but a new service and the session id.
    restarted = AgentSessionAuditService().export_audit(
        project_id=PROJECT, session_id=session.session_id
    )
    ids = [event.event_id for event in restarted.events]
    response_id = next(e.event_id for e in restarted.events if e.kind == "intervention_response")
    assert ids.index(f"intervention_opened:{opened.intervention_id}") < ids.index(response_id)
    assert ids.index(response_id) < ids.index(f"action_proposed:{retry.action_id}")
    response = _event(restarted, response_id)
    assert response.actor == "expert"
    assert response.provenance == "human_reported"
    assert response.data["guidance"] == "Widen the sweep by 50 MHz."
    opened_event = _event(restarted, f"intervention_opened:{opened.intervention_id}")
    assert opened_event.data["question"] == "Widen the sweep or stop?"
    assert opened_event.status == "resumed"


def test_decision_retry_is_idempotent_and_corrections_append(
    sessions: AgentSessionService, audit: AgentSessionAuditService
) -> None:
    session = _session(sessions)
    action = _submit(sessions, session.session_id, key="a-1")
    first = _decision(audit, session.session_id, key="d-1", evidence_action_ids=[action.action_id])
    replay = _decision(audit, session.session_id, key="d-1", evidence_action_ids=[action.action_id])
    assert replay.decision_id == first.decision_id
    with pytest.raises(HTTPException) as reused:
        _decision(audit, session.session_id, key="d-1", next_action="stop")
    assert reused.value.status_code == 409

    correction = _decision(
        audit,
        session.session_id,
        key="d-2",
        assessment="inconclusive",
        interpretation="Correction: the R2 cited earlier was from a different run.",
        next_action="repeat",
        supersedes_decision_id=first.decision_id,
    )
    assert AgentDecisionDocument.find({"session_id": session.session_id}).count() == 2
    result = audit.export_audit(project_id=PROJECT, session_id=session.session_id)
    original = _event(result, f"decision:{first.decision_id}")
    assert original.status == "superseded"
    assert original.data["superseded_by_decision_id"] == correction.decision_id
    assert original.data["interpretation"].startswith("The peak is clear")


def test_decisions_reject_foreign_references_and_other_users(
    sessions: AgentSessionService, audit: AgentSessionAuditService
) -> None:
    session = _session(sessions)
    other = _session(sessions)
    foreign_project = _session(sessions, project_id="project-2")
    mine = _submit(sessions, session.session_id, key="a-1")
    theirs = _submit(sessions, other.session_id, key="a-1")
    _finish(other.session_id, theirs.action_id, sequence=7)
    EvaluationDocument(
        evaluation_id="ev-other",
        run_id="run-1",
        project_id=PROJECT,
        chip_id="chip-001",
        task_id="task-7",
        task_name="CheckQubitFrequency",
        qid="Q00",
    ).insert()

    cases: list[tuple[dict[str, Any], int]] = [
        ({"evidence_action_ids": [theirs.action_id]}, 409),
        ({"next_action_id": theirs.action_id}, 409),
        ({"evaluation_ids": ["ev-other"]}, 409),
        ({"intervention_id": "int-unknown"}, 409),
        ({"supersedes_decision_id": "dec-unknown"}, 409),
    ]
    for index, (fields, code) in enumerate(cases):
        with pytest.raises(HTTPException) as refused:
            _decision(audit, session.session_id, key=f"bad-{index}", **fields)
        assert refused.value.status_code == code, fields
    with pytest.raises(HTTPException) as not_creator:
        _decision(audit, session.session_id, key="d-x", username="mallory")
    assert not_creator.value.status_code == 403
    with pytest.raises(HTTPException) as cross_project:
        _decision(audit, foreign_project.session_id, key="d-x")
    assert cross_project.value.status_code == 404
    with pytest.raises(HTTPException) as cross_read:
        audit.export_audit(project_id=PROJECT, session_id=foreign_project.session_id)
    assert cross_read.value.status_code == 404
    assert AgentDecisionDocument.find({}).count() == 0
    assert mine.decision == AgentActionDecision.AUTHORIZED


def test_decision_snapshot_stays_frozen_while_current_status_moves(
    sessions: AgentSessionService, audit: AgentSessionAuditService
) -> None:
    session = _session(sessions)
    action = _submit(sessions, session.session_id, key="a-1")
    _finish(session.session_id, action.action_id, sequence=1, status="running")
    decided = _decision(
        audit,
        session.session_id,
        key="d-1",
        assessment=None,
        interpretation="Still running; waiting for the result.",
        evidence_action_ids=[action.action_id],
        next_action="repeat",
    )
    ExecutionHistoryDocument.get_motor_collection().update_one(
        {"execution_id": "execution-1"}, {"$set": {"status": "completed"}}
    )
    result = audit.export_audit(project_id=PROJECT, session_id=session.session_id)
    assert _event(result, f"measurement:{action.action_id}").status == "completed"
    frozen = _event(result, f"decision:{decided.decision_id}")
    assert frozen.data["evidence_snapshot"]["actions"][0]["execution_status"] == "running"
    assert frozen.missing == ["assessment"]


def test_legacy_session_shows_known_facts_and_marks_missing_metadata(
    sessions: AgentSessionService, audit: AgentSessionAuditService
) -> None:
    """A session recorded before audits existed is not given decisions or actors it lacks."""
    session = _session(sessions)
    AgentSessionDocument.get_motor_collection().update_one(
        {"session_id": session.session_id},
        {"$set": {"skill_name": "", "skill_version": "", "model_name": ""}},
    )
    legacy = AgentActionDocument(
        action_id="legacy-1",
        session_id=session.session_id,
        project_id=PROJECT,
        idempotency_key="legacy",
        request_hash="x",
        action_type=AgentActionType.RUN_TASK,
        task_name="CheckQubitFrequency",
        qids=["Q00"],
        decision=AgentActionDecision.AUTHORIZED,
        reason="authorized",
        execution_status="completed",
        operation_id="execution-legacy",
        execution_id="execution-legacy",
        state_version_before=0,
        state_version_after=1,
    )
    legacy.insert()

    result = audit.export_audit(project_id=PROJECT, session_id=session.session_id)

    assert set(result.session.missing) == {
        "skill_name",
        "skill_version",
        "skill_hash",
        "model_name",
    }
    proposed = _event(result, "action_proposed:legacy-1")
    assert proposed.actor is None
    assert proposed.missing == ["actor"]
    measurement = _event(result, "measurement:legacy-1")
    assert measurement.status == "completed"
    assert set(measurement.missing) == {"task_result", "decision"}
    assert "decision" not in _kinds(result)


def test_pages_cover_the_whole_timeline_and_export_is_not_truncated(
    sessions: AgentSessionService, audit: AgentSessionAuditService
) -> None:
    session = _session(sessions)
    action = _submit(sessions, session.session_id, key="a-1")
    for index in range(130):
        _decision(
            audit,
            session.session_id,
            key=f"d-{index}",
            evidence_action_ids=[action.action_id],
            next_action="repeat",
        )

    exported = audit.export_audit(project_id=PROJECT, session_id=session.session_id)
    assert exported.total_events == 132
    assert len(exported.events) == 132
    assert exported.complete is True

    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        page = audit.read_audit(
            project_id=PROJECT, session_id=session.session_id, cursor=cursor, limit=50
        )
        pages += 1
        seen.extend(event.event_id for event in page.events)
        assert page.total_events == 132
        if page.complete:
            assert page.next_cursor is None
            break
        cursor = page.next_cursor
    assert pages == 3
    assert seen == [event.event_id for event in exported.events]

    default = audit.read_audit(project_id=PROJECT, session_id=session.session_id)
    assert len(default.events) == 100
    assert default.complete is False
    with pytest.raises(HTTPException) as invalid:
        audit.read_audit(project_id=PROJECT, session_id=session.session_id, cursor="not-a-cursor")
    assert invalid.value.status_code == 400


def test_failed_commit_and_failed_apply_are_reported_without_raw_errors(
    sessions: AgentSessionService, audit: AgentSessionAuditService
) -> None:
    session = _session(sessions)
    action = _submit(sessions, session.session_id, key="a-1")
    base: dict[str, Any] = {
        "session_id": session.session_id,
        "action_id": action.action_id,
        "project_id": PROJECT,
        "request_hash": "h",
        "execution_id": "execution-1",
        "task_id": "task-1",
        "task_name": "CheckQubitFrequency",
        "chip_id": "chip-001",
        "qid": "Q00",
        "parameter_name": "qubit_frequency",
        "value": 5.12,
        "committed_by": OWNER,
        "state_version_before": 1,
        "state_version_after": 2,
    }
    AgentCandidateCommitDocument(
        commit_id="commit-failed",
        idempotency_key="c-1",
        status="failed",
        reason="Candidate persistence failed: mongodb://admin:pw@db timed out",
        **base,
    ).insert()
    AgentCandidateCommitDocument(
        commit_id="commit-pending",
        idempotency_key="c-2",
        status="committing",
        **base,
    ).insert()
    AgentCandidateCommitDocument(
        commit_id="commit-apply-failed",
        idempotency_key="c-3",
        status="committed",
        after_snapshot={"value": 5.12},
        backend_status="failed",
        backend_requested_at=now(),
        backend_error="worker said token=abc123",
        **base,
    ).insert()

    result = audit.export_audit(project_id=PROJECT, session_id=session.session_id)
    dumped = result.model_dump_json()

    assert "pw@db" not in dumped
    assert "abc123" not in dumped
    assert _event(result, "candidate_commit:commit-failed").data["reason"] == (
        "Candidate persistence failed"
    )
    pending = _event(result, "candidate_commit:commit-pending")
    assert pending.status == "committing"
    assert pending.status_is_current is True
    assert "was" not in pending.summary
    apply_failed = _event(result, "backend_apply:commit-apply-failed")
    assert apply_failed.status == "failed"
    assert apply_failed.data["error_recorded"] is True
    assert "backend_apply:commit-pending" not in {event.event_id for event in result.events}


# ---------------------------------------------------------------------- snapshot pagination


def _pages(audit: AgentSessionAuditService, session_id: str, limit: int) -> list[Any]:
    pages = []
    cursor = None
    while True:
        page = audit.read_audit(
            project_id=PROJECT, session_id=session_id, cursor=cursor, limit=limit
        )
        pages.append(page)
        if page.complete:
            return pages
        cursor = page.next_cursor


def _with_notes(audit: AgentSessionAuditService, session_id: str, count: int) -> str:
    action = _submit(audit_sessions(), session_id, key="a-notes")
    for index in range(count):
        _decision(audit, session_id, key=f"n-{index}", evidence_action_ids=[action.action_id])
    return str(action.action_id)


def audit_sessions() -> AgentSessionService:
    return AgentSessionService(intervention_service=AgentInterventionService())


def test_a_late_result_with_an_earlier_time_restarts_paging_instead_of_being_skipped(
    sessions: AgentSessionService, audit: AgentSessionAuditService
) -> None:
    """A measurement that lands between pages, sorting before the page already read, is not
    silently left out: the next page is refused and a new first page contains it."""
    session = _session(sessions)
    late = _submit(sessions, session.session_id, key="a-late")
    _with_notes(audit, session.session_id, 6)
    first = audit.read_audit(project_id=PROJECT, session_id=session.session_id, limit=4)
    assert first.complete is False
    assert f"measurement:{late.action_id}" not in {e.event_id for e in first.events}

    # The run finishes now, but its dispatch time is before every event of the first page.
    _finish(session.session_id, late.action_id, sequence=1)
    AgentActionDocument.get_motor_collection().update_one(
        {"action_id": late.action_id},
        {"$set": {"dispatch_reserved_at": session.created_at + timedelta(milliseconds=1)}},
    )
    with pytest.raises(HTTPException) as changed:
        audit.read_audit(
            project_id=PROJECT,
            session_id=session.session_id,
            cursor=first.next_cursor,
            limit=4,
        )
    assert changed.value.status_code == 409
    assert "first page" in str(changed.value.detail)

    again = _pages(audit, session.session_id, 4)
    seen = [event.event_id for page in again for event in page.events]
    assert f"measurement:{late.action_id}" in seen[:4]
    assert len({page.snapshot_id for page in again}) == 1
    assert again[0].snapshot_id != first.snapshot_id
    assert len(seen) == again[0].total_events == len(set(seen))


def test_a_decision_or_intervention_between_pages_invalidates_the_cursor(
    sessions: AgentSessionService, audit: AgentSessionAuditService
) -> None:
    session = _session(sessions)
    action_id = _with_notes(audit, session.session_id, 5)
    first = audit.read_audit(project_id=PROJECT, session_id=session.session_id, limit=3)
    _decision(audit, session.session_id, key="d-late", evidence_action_ids=[action_id])
    with pytest.raises(HTTPException) as after_decision:
        audit.read_audit(
            project_id=PROJECT, session_id=session.session_id, cursor=first.next_cursor
        )
    assert after_decision.value.status_code == 409

    first = audit.read_audit(project_id=PROJECT, session_id=session.session_id, limit=3)
    sessions.interventions.create_intervention(
        project_id=PROJECT,
        session_id=session.session_id,
        username=OWNER,
        body=CreateAgentInterventionRequest.model_validate(
            {
                "idempotency_key": "human-late",
                "reason": "agent_request",
                "summary": "Need a person.",
                "question": "Continue?",
                "autonomous": True,
            }
        ),
    )
    with pytest.raises(HTTPException) as after_intervention:
        audit.read_audit(
            project_id=PROJECT, session_id=session.session_id, cursor=first.next_cursor
        )
    assert after_intervention.value.status_code == 409


def test_pages_of_one_snapshot_match_its_export(
    sessions: AgentSessionService, audit: AgentSessionAuditService
) -> None:
    session = _session(sessions)
    _with_notes(audit, session.session_id, 120)
    pages = _pages(audit, session.session_id, 100)
    exported = audit.export_audit(project_id=PROJECT, session_id=session.session_id)
    assert len(pages) == 2
    assert {page.snapshot_id for page in pages} == {exported.snapshot_id}
    assert [e.event_id for page in pages for e in page.events] == [
        e.event_id for e in exported.events
    ]
    assert [e.sequence for page in pages for e in page.events] == list(range(122))
    assert pages[0].total_events == exported.total_events == 122


def test_foreign_tampered_and_old_cursors_are_refused(
    sessions: AgentSessionService, audit: AgentSessionAuditService
) -> None:
    from qdash.api.services import agent_session_audit as module

    session = _session(sessions)
    other = _session(sessions)
    foreign = _session(sessions, project_id="project-2")
    _with_notes(audit, session.session_id, 4)
    first = audit.read_audit(project_id=PROJECT, session_id=session.session_id, limit=2)
    assert first.next_cursor is not None
    position = module._decode_cursor(first.next_cursor)

    def read(session_id: str, cursor: str, project_id: str = PROJECT) -> int:
        with pytest.raises(HTTPException) as refused:
            audit.read_audit(project_id=project_id, session_id=session_id, cursor=cursor)
        return refused.value.status_code

    # A cursor of another session, or of the same session id in another project.
    assert read(other.session_id, first.next_cursor) == 400
    assert read(foreign.session_id, first.next_cursor, project_id="project-2") == 400
    # A cursor whose position or snapshot was edited.
    past_end = module._CursorPosition(PROJECT, session.session_id, position.snapshot_id, 10_000)
    assert read(session.session_id, module._encode_cursor(past_end)) == 400
    forged = module._CursorPosition(PROJECT, session.session_id, "0" * 32, position.offset)
    assert read(session.session_id, module._encode_cursor(forged)) == 409
    for raw in ('["v2","project-1","x","y",0]', '["v2","project-1","x","y",true]'):
        token = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
        assert read(session.session_id, token) == 400
    # A cursor of the earlier sort-key format, and noise.
    old = base64.urlsafe_b64encode(b'["v1","2026-11-21T00:00:00.000+00:00",1,1,"e"]').decode()
    assert read(session.session_id, old.rstrip("=")) == 400
    assert read(session.session_id, "not-a-cursor") == 400


def test_records_changing_during_an_export_give_a_fresh_snapshot_or_a_refusal(
    sessions: AgentSessionService,
    audit: AgentSessionAuditService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The export never reports complete for records that were read while they changed."""
    session = _session(sessions)
    action = _submit(sessions, session.session_id, key="a-1")
    _finish(session.session_id, action.action_id, sequence=1, status="running")
    original = AgentSessionAuditService._read_once
    reads: list[str] = []

    def finishing_after_first_read(self: AgentSessionAuditService, *args: Any) -> Any:
        snapshot = original(self, *args)
        reads.append(snapshot.snapshot_id)
        if len(reads) == 1:
            # The run completes while the export is being read.
            ExecutionHistoryDocument.get_motor_collection().update_one(
                {"execution_id": "execution-1"}, {"$set": {"status": "completed"}}
            )
        return snapshot

    monkeypatch.setattr(AgentSessionAuditService, "_read_once", finishing_after_first_read)
    exported = audit.export_audit(project_id=PROJECT, session_id=session.session_id)
    assert len(reads) == 3
    assert reads[0] != reads[1] == reads[2] == exported.snapshot_id
    assert _event(exported, f"measurement:{action.action_id}").status == "completed"
    assert exported.complete is True

    def always_changing(self: AgentSessionAuditService, *args: Any) -> Any:
        _decision(audit, session.session_id, key=f"d-{len(reads)}")
        reads.append("changed")
        return original(self, *args)

    monkeypatch.setattr(AgentSessionAuditService, "_read_once", always_changing)
    for read in (
        lambda: audit.export_audit(project_id=PROJECT, session_id=session.session_id),
        lambda: audit.read_audit(project_id=PROJECT, session_id=session.session_id),
    ):
        with pytest.raises(HTTPException) as unstable:
            read()
        assert unstable.value.status_code == 503


# ---------------------------------------------------------------------- decision quota


def _fill_decisions(session_id: str, count: int) -> None:
    AgentDecisionDocument.insert_many(
        [
            AgentDecisionDocument(
                decision_id=f"bulk-{slot}",
                project_id=PROJECT,
                session_id=session_id,
                chip_id="chip-001",
                idempotency_key=f"bulk-{slot}",
                request_hash="",
                recorded_by=OWNER,
                session_status_at_record="active",
                session_state_version_at_record=0,
                interpretation="bulk",
                next_action="next_task",
                quota_slot=slot,
            )
            for slot in range(count)
        ]
    )


def _interleave(monkeypatch: pytest.MonkeyPatch, on_call: int, concurrent: Any) -> None:
    """Run ``concurrent`` inside the ``on_call``-th quota read, after it read the slot."""
    original = AgentSessionAuditService._used_slots
    calls = {"count": 0}

    def used_slots(scope: dict[str, str]) -> int:
        calls["count"] += 1
        value = original(scope)
        if calls["count"] == on_call:
            concurrent()
        return value

    monkeypatch.setattr(AgentSessionAuditService, "_used_slots", staticmethod(used_slots))


def test_concurrent_distinct_decisions_at_the_last_slot_never_exceed_the_quota(
    sessions: AgentSessionService,
    audit: AgentSessionAuditService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from qdash.api.services.agent_session_audit import MAX_DECISIONS_PER_SESSION

    session = _session(sessions)
    _fill_decisions(session.session_id, MAX_DECISIONS_PER_SESSION - 1)
    winner: list[Any] = []
    # Both recordings see slot 1999 free (the first read of each passes the quota check, the
    # second chooses the slot); the other one inserts in between.
    for on_call in (1, 2):
        _interleave(
            monkeypatch,
            on_call,
            lambda key=f"b-{on_call}": winner.append(_decision(audit, session.session_id, key=key)),
        )
        with pytest.raises(HTTPException) as full:
            _decision(audit, session.session_id, key=f"a-{on_call}")
        assert full.value.status_code == 409
        assert "full" in str(full.value.detail)
        assert AgentDecisionDocument.find({"session_id": session.session_id}).count() == 2000
        monkeypatch.undo()
        raced = AgentDecisionDocument.find_one({"decision_id": winner[-1].decision_id}).run()
        assert raced is not None
        raced.delete()
    slots = [d.quota_slot for d in AgentDecisionDocument.find({"session_id": session.session_id})]
    assert sorted(slots) == list(range(MAX_DECISIONS_PER_SESSION - 1))


def test_same_key_races_at_the_cap_record_once_and_replay(
    sessions: AgentSessionService,
    audit: AgentSessionAuditService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from qdash.api.services.agent_session_audit import MAX_DECISIONS_PER_SESSION

    session = _session(sessions)
    _fill_decisions(session.session_id, MAX_DECISIONS_PER_SESSION - 1)
    first: list[Any] = []
    _interleave(
        monkeypatch, 2, lambda: first.append(_decision(audit, session.session_id, key="same"))
    )
    replayed = _decision(audit, session.session_id, key="same")
    monkeypatch.undo()
    assert replayed.decision_id == first[0].decision_id
    assert AgentDecisionDocument.find({"session_id": session.session_id}).count() == 2000
    # With the quota full, a retry of the key still replays; a new key is refused.
    assert _decision(audit, session.session_id, key="same").decision_id == replayed.decision_id
    with pytest.raises(HTTPException) as full:
        _decision(audit, session.session_id, key="another")
    assert full.value.status_code == 409


def test_a_crash_around_the_insert_neither_loses_a_record_nor_holds_a_slot(
    sessions: AgentSessionService,
    audit: AgentSessionAuditService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session(sessions)
    _fill_decisions(session.session_id, 3)
    original = AgentDecisionDocument.insert

    def crash_before(self: AgentDecisionDocument, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("process died before the write")

    monkeypatch.setattr(AgentDecisionDocument, "insert", crash_before)
    with pytest.raises(RuntimeError):
        _decision(audit, session.session_id, key="k-1")
    monkeypatch.undo()
    assert AgentDecisionDocument.find({"session_id": session.session_id}).count() == 3
    recorded = _decision(audit, session.session_id, key="k-1")
    stored = AgentDecisionDocument.find_one({"decision_id": recorded.decision_id}).run()
    assert stored is not None and stored.quota_slot == 3

    def crash_after(self: AgentDecisionDocument, *args: Any, **kwargs: Any) -> Any:
        original(self, *args, **kwargs)
        raise RuntimeError("response lost after the write")

    monkeypatch.setattr(AgentDecisionDocument, "insert", crash_after)
    with pytest.raises(RuntimeError):
        _decision(audit, session.session_id, key="k-2")
    monkeypatch.undo()
    retried = _decision(audit, session.session_id, key="k-2")
    assert AgentDecisionDocument.find({"session_id": session.session_id}).count() == 5
    stored = AgentDecisionDocument.find_one({"decision_id": retried.decision_id}).run()
    assert stored is not None and stored.quota_slot == 4
