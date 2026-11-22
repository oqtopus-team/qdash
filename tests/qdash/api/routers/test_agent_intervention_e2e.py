"""End to end: a plan stops for a person, an expert answers in QDash, the runner resumes.

The Python client talks to the real API (in-memory MongoDB). Measurements are simulated by a
step runner that submits real actions and writes their executions and task results; Slack is a
fake client. Nothing reaches hardware or Slack.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from qdash.api.dependencies import get_agent_intervention_service, get_agent_session_service
from qdash.api.services.agent_intervention_service import AgentInterventionService
from qdash.api.services.agent_intervention_slack import AgentInterventionSlackNotifier
from qdash.api.services.agent_session_service import AgentSessionService
from qdash.client import QDashClient, QDashConfig
from qdash.client.services.agent_runner import (
    PLAN_COMPLETE,
    PLAN_ESCALATE,
    AgentPlannerDecision,
    AgentPlanNode,
    AgentPlanRunner,
    AgentSkillTransition,
    AgentStepOutcome,
    resume_state_from_intervention,
)
from qdash.common.utils.datetime import now
from qdash.config import get_settings
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.agent_session import AgentActionDocument, AgentSessionDocument
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.dbmodel.user import UserDocument

OUTPUTS = {"CheckRabi": ("control_amplitude", 0.05), "CheckChevron": ("qubit_frequency", 7.5)}


class FakeSlack:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def chat_postMessage(self, *, channel: str, **kwargs: Any) -> dict[str, str]:
        kwargs["channel"] = channel
        self.calls.append(kwargs)
        return {"channel": kwargs["channel"], "ts": f"{len(self.calls)}.000"}


class SimulatedStepRunner:
    """Submits real actions; simulates the measurement only for an action not run before."""

    def __init__(self, client: QDashClient) -> None:
        self._client = client
        self.measurements: list[str] = []

    def run_step(self, **kwargs: Any) -> AgentStepOutcome:
        session_id = kwargs["session_id"]
        task_name = kwargs["task_name"]
        session = self._client.get_agent_session(session_id)
        action = self._client.submit_agent_action(
            session_id,
            idempotency_key=kwargs["action_idempotency_key"],
            expected_state_version=session.state_version,
            action_type="run_task",
            task_name=task_name,
            qids=[kwargs["qid"]],
            parameter_overrides=kwargs["parameter_overrides"],
        )
        if action.decision != "authorized":
            return AgentStepOutcome(
                transition=AgentSkillTransition.HUMAN_ESCALATION,
                reason=action.reason,
                session_id=session_id,
                action_id=action.action_id,
                action=action,
            )
        doc = AgentActionDocument.find_one({"action_id": action.action_id}).run()
        assert doc is not None
        if doc.execution_status == "not_started":
            self._measure(doc, task_name)
        candidates = self._client.list_agent_action_candidates(session_id, action.action_id)
        candidate = next(c for c in candidates if c.parameter_name == kwargs["candidate_parameter"])
        return AgentStepOutcome(
            transition=AgentSkillTransition.PASS,
            reason="Candidate passed and remains staged",
            session_id=session_id,
            action_id=action.action_id,
            operation_id=doc.operation_id,
            execution_id=doc.execution_id,
            candidate=candidate,
        )

    def _measure(self, doc: AgentActionDocument, task_name: str) -> None:
        index = len(self.measurements) + 1
        self.measurements.append(task_name)
        execution_id = f"exec-{index}"
        doc.operation_id = execution_id
        doc.execution_id = execution_id
        doc.execution_status = "completed"
        doc.save()
        ExecutionHistoryDocument(
            project_id="lab-a",
            username="owner",
            name=f"agent:{task_name}",
            execution_id=execution_id,
            calib_data_path="",
            note={},
            status="completed",
            tags=[],
            chip_id="chip-001",
            message="",
            system_info=SystemInfoModel(),
        ).insert()
        parameter, value = OUTPUTS[task_name]
        TaskResultHistoryDocument(
            project_id="lab-a",
            username="owner",
            task_id=f"task-{index}",
            name=task_name,
            upstream_id="",
            status="completed",
            message="completed",
            input_parameters={},
            output_parameters={parameter: {"value": value}},
            output_parameter_names=[parameter],
            run_parameters={},
            note={},
            figure_path=[],
            json_figure_path=[],
            raw_data_path=[],
            start_at=now(),
            end_at=now(),
            elapsed_time=1.0,
            task_type="qubit",
            system_info=SystemInfoModel(),
            qid="Q00",
            execution_id=execution_id,
            tags=[],
            chip_id="chip-001",
        ).insert()


class ScriptedPlanner:
    """Escalates the first Rabi result as unknown; completes after Chevron."""

    def choose_next(self, observation: Any) -> AgentPlannerDecision:
        if observation.last_node_id == "rabi":
            return AgentPlannerDecision(
                PLAN_ESCALATE,
                "CheckRabi evaluation reported LOW_CONTRAST, which has no next action",
                escalation_reason="unknown_outcome",
                evidence={"status": "LOW_CONTRAST"},
            )
        return AgentPlannerDecision(PLAN_COMPLETE, "SUCCESS")


@pytest.fixture
def lab(test_client):
    from qdash.api.main import app

    slack = FakeSlack()
    settings = get_settings().model_copy(
        update={
            "slack_bot_token": "xoxb-test",
            "slack_agent_notification": True,
            "slack_agent_channel_id": "C-agent",
        }
    )
    interventions = AgentInterventionService(
        notifier=AgentInterventionSlackNotifier(settings=settings, client=slack)
    )
    app.dependency_overrides[get_agent_intervention_service] = lambda: interventions
    app.dependency_overrides[get_agent_session_service] = lambda: AgentSessionService(
        intervention_service=interventions
    )
    user = UserDocument(
        username="owner",
        hashed_password="hashed",
        access_token="owner-token",
        default_project_id="lab-a",
        system_info=SystemInfoModel(),
    )
    user.insert()
    ProjectDocument(
        project_id="lab-a", name="Lab A", owner_user_id=user.user_id, owner_username="owner"
    ).insert()
    ProjectMembershipDocument(
        project_id="lab-a",
        user_id=user.user_id,
        username="owner",
        role=ProjectRole.OWNER,
        status="active",
        invited_by_user_id=user.user_id,
        invited_by="owner",
    ).insert()
    ChipDocument(
        project_id="lab-a",
        chip_id="chip-001",
        username="owner",
        size=4,
        system_info=SystemInfoModel(),
    ).insert()
    client = QDashClient(
        QDashConfig(
            base_url=str(test_client.base_url), api_token="owner-token", project_id="lab-a"
        ),
        http_client=test_client,
    )
    yield client, slack, test_client
    app.dependency_overrides.pop(get_agent_intervention_service, None)
    app.dependency_overrides.pop(get_agent_session_service, None)


NODES = [
    AgentPlanNode(node_id="rabi", task_name="CheckRabi", candidate_parameter="control_amplitude"),
    AgentPlanNode(
        node_id="chevron", task_name="CheckChevron", candidate_parameter="qubit_frequency"
    ),
]


def test_unknown_result_waits_for_an_expert_and_resumes_without_replay(lab) -> None:
    client, slack, http = lab
    session = client.create_agent_session(
        chip_id="chip-001",
        policy={
            "qids": ["Q00"],
            "allowed_tasks": ["CheckRabi", "CheckChevron"],
            "allowed_overrides": {
                "control_amplitude": {"minimum": 0.0, "maximum": 1.0},
                "qubit_frequency": {"minimum": 7.0, "maximum": 8.0},
            },
            "max_actions": 4,
            "autonomy": "auto",
        },
    )
    steps = SimulatedStepRunner(client)
    runner = AgentPlanRunner(client, step_runner=steps)  # type: ignore[arg-type]

    stopped = runner.run_plan(
        session_id=session.session_id,
        qid="Q00",
        nodes=NODES,
        planner=ScriptedPlanner(),
        max_node_executions=4,
        max_node_visits=2,
        idempotency_prefix="plan-e2e",
        record_interventions=True,
        planner_name="none",
    )

    # The stop is durable in QDash, the session is paused, and Slack got one root message.
    assert stopped.transition == AgentSkillTransition.HUMAN_ESCALATION
    assert stopped.intervention is not None, stopped.intervention_error
    intervention_id = stopped.intervention.intervention_id
    assert client.get_agent_session(session.session_id).status == "waiting_for_human"
    recorded = client.get_agent_intervention(session.session_id, intervention_id)
    assert recorded.reason == "unknown_outcome"
    assert recorded.attempts[0]["status"] == "LOW_CONTRAST"
    assert recorded.notification["status"] == "sent"
    assert len(slack.calls) == 1
    assert steps.measurements == ["CheckRabi"]

    # Nothing else can run while the session waits.
    blocked = runner.run_plan(
        session_id=session.session_id,
        qid="Q00",
        nodes=NODES,
        idempotency_prefix="plan-other",
        record_interventions=True,
    )
    assert "waiting_for_human" in blocked.reason
    assert blocked.intervention is None
    assert blocked.intervention_error is not None
    assert steps.measurements == ["CheckRabi"]

    # The runner cannot resume before an expert answers.
    with pytest.raises(Exception, match="409"):
        client.claim_agent_resume(session.session_id, intervention_id, claim_key="claim-1")

    # The expert answers in QDash: continue from the Chevron node.
    answered = http.post(
        f"/agent-sessions/{session.session_id}/interventions/{intervention_id}/respond",
        headers={"Authorization": "Bearer owner-token", "X-Project-Id": "lab-a"},
        json={
            "idempotency_key": "answer-1",
            "expected_state_version": recorded.session_state_version,
            "decision": "resume",
            "guidance": "Low contrast is from a weak drive; check the frequency first.",
            "resume_node_id": "chevron",
        },
    )
    assert answered.status_code == 200, answered.text
    assert answered.json()["status"] == "resume_authorized"
    assert client.get_agent_session(session.session_id).status == "waiting_for_human"

    # The runner claims the resume and continues from the checkpoint.
    claimed = client.claim_agent_resume(session.session_id, intervention_id, claim_key="claim-1")
    nodes, state, settings = resume_state_from_intervention(claimed)
    resumed = runner.run_plan(
        session_id=session.session_id,
        qid=settings["qid"],
        nodes=nodes,
        planner=ScriptedPlanner(),
        max_node_executions=settings["max_node_executions"],
        max_node_visits=settings["max_node_visits"],
        idempotency_prefix=settings["idempotency_prefix"],
        record_interventions=True,
        resume=state,
    )
    client.record_agent_resume_outcome(
        session.session_id,
        intervention_id,
        claim_key="claim-1",
        transition=resumed.transition.value,
        reason=resumed.reason,
    )

    assert resumed.transition == AgentSkillTransition.PASS, resumed.reason
    assert resumed.node_path == ("rabi", "chevron")
    # Rabi was measured once in total; only the new node ran after the resume.
    assert steps.measurements == ["CheckRabi", "CheckChevron"]
    assert resumed.carried_overrides == {"control_amplitude": 0.05, "qubit_frequency": 7.5}
    assert state.guidance.startswith("Low contrast")
    final = client.get_agent_intervention(session.session_id, intervention_id)
    assert final.status == "resumed"
    assert final.resume_outcome is not None
    assert final.resume_outcome["transition"] == "pass"
    active = client.get_agent_session(session.session_id)
    assert active.status == "active"
    assert active.action_count == 2
    # The thread got replies for the answer, the claim, and the outcome.
    assert [call.get("thread_ts") for call in slack.calls[1:]] == ["1.000"] * 3


def test_mixed_manual_and_plan_history_pauses_without_a_resumable_checkpoint(lab) -> None:
    client, slack, http = lab
    session = client.create_agent_session(
        chip_id="chip-001",
        policy={
            "qids": ["Q00"],
            "allowed_tasks": ["CheckRabi", "CheckChevron"],
            "allowed_overrides": {
                "control_amplitude": {"minimum": 0.0, "maximum": 1.0},
                "qubit_frequency": {"minimum": 7.0, "maximum": 8.0},
            },
            "max_actions": 6,
            "autonomy": "auto",
        },
    )
    steps = SimulatedStepRunner(client)
    # A manual run_step before the plan: its action is not a node visit of any plan.
    manual = steps.run_step(
        session_id=session.session_id,
        task_name="CheckRabi",
        qid="Q00",
        action_idempotency_key="manual-rabi",
        parameter_overrides={},
        candidate_parameter="control_amplitude",
    )
    assert manual.transition == AgentSkillTransition.PASS
    runner = AgentPlanRunner(client, step_runner=steps)  # type: ignore[arg-type]

    def stop() -> Any:
        return runner.run_plan(
            session_id=session.session_id,
            qid="Q00",
            nodes=NODES,
            planner=ScriptedPlanner(),
            max_node_executions=4,
            max_node_visits=2,
            idempotency_prefix="plan-mixed",
            record_interventions=True,
        )

    stopped = stop()

    # QDash rejected the checkpoint, so the stop was recorded once without one.
    assert stopped.transition == AgentSkillTransition.HUMAN_ESCALATION
    assert stopped.checkpoint is not None
    assert stopped.checkpoint_rejection is not None
    assert "not part of this plan" in stopped.checkpoint_rejection
    assert stopped.intervention is not None, stopped.intervention_error
    intervention_id = stopped.intervention.intervention_id
    recorded = client.get_agent_intervention(session.session_id, intervention_id)
    assert recorded.checkpoint is None
    assert recorded.reason == "unknown_outcome", stopped.reason
    raw = http.get(
        f"/agent-sessions/{session.session_id}/interventions/{intervention_id}",
        headers={"Authorization": "Bearer owner-token", "X-Project-Id": "lab-a"},
    ).json()
    assert raw["resume_options"] == []
    assert recorded.resume_command is None
    assert recorded.summary.endswith("this intervention cannot resume the plan.")
    assert recorded.notification["status"] == "sent"
    assert len(slack.calls) == 1
    paused = client.get_agent_session(session.session_id)
    assert paused.status == "waiting_for_human"
    assert paused.active_intervention_id == intervention_id
    stored = AgentSessionDocument.find_one({"session_id": session.session_id}).run()
    assert stored is not None
    assert stored.plan_binding is None
    assert len(client.list_agent_interventions(session.session_id)) == 1

    # Recording the same stop again (a retry after a lost response) returns the same record.
    retried = runner._record_intervention(
        replace(stopped, intervention=None, checkpoint_rejection=None),
        previous_intervention_id=None,
    )
    assert retried.intervention is not None, retried.intervention_error
    assert retried.intervention.intervention_id == intervention_id
    # A new run is refused by the paused session, and its stop is not recorded.
    again = stop()
    assert again.intervention is None
    assert again.intervention_error is not None
    assert "already waits" in again.intervention_error
    assert len(client.list_agent_interventions(session.session_id)) == 1
    assert len(slack.calls) == 1
    assert steps.measurements == ["CheckRabi", "CheckRabi"]

    # No runner can resume a plan from it, before or after an expert answers.
    with pytest.raises(Exception, match="409"):
        client.claim_agent_resume(session.session_id, intervention_id, claim_key="claim-1")
    answered = http.post(
        f"/agent-sessions/{session.session_id}/interventions/{intervention_id}/respond",
        headers={"Authorization": "Bearer owner-token", "X-Project-Id": "lab-a"},
        json={
            "idempotency_key": "answer-1",
            "expected_state_version": recorded.session_state_version,
            "decision": "resume",
            "guidance": "Continue by hand.",
        },
    )
    assert answered.status_code == 200, answered.text
    assert answered.json()["status"] == "resumed"
    assert answered.json()["resume_command"] is None
    with pytest.raises(ValueError, match="no plan checkpoint"):
        resume_state_from_intervention(
            client.get_agent_intervention(session.session_id, intervention_id)
        )
    with pytest.raises(Exception, match="409"):
        client.claim_agent_resume(session.session_id, intervention_id, claim_key="claim-1")


def test_out_of_scope_checkpoint_is_refused_without_a_fallback(lab) -> None:
    client, slack, http = lab
    session = client.create_agent_session(
        chip_id="chip-001",
        policy={
            "qids": ["Q00"],
            "allowed_tasks": ["CheckRabi"],
            "allowed_overrides": {},
            "max_actions": 4,
            "autonomy": "auto",
        },
    )
    checkpoint = {
        "idempotency_prefix": "plan-scope",
        "qid": "Q00",
        "nodes": [
            {"id": "chevron", "task_name": "CheckChevron", "candidate_parameter": "f"},
        ],
        "node_path": [],
        "visit_counts": {},
        "stopped_node_id": "chevron",
        "max_node_executions": 1,
    }

    refused = http.post(
        f"/agent-sessions/{session.session_id}/interventions",
        headers={"Authorization": "Bearer owner-token", "X-Project-Id": "lab-a"},
        json={
            "idempotency_key": "scope-1",
            "reason": "unknown_outcome",
            "summary": "stopped",
            "question": "resume?",
            "qids": ["Q00"],
            "checkpoint": checkpoint,
        },
    )
    unauthenticated = http.post(
        f"/agent-sessions/{session.session_id}/interventions",
        json={
            "idempotency_key": "scope-2",
            "reason": "unknown_outcome",
            "summary": "stopped",
            "question": "resume?",
            "qids": ["Q00"],
        },
    )

    # A scope violation is a plain 422 without the checkpoint_rejected code.
    assert refused.status_code == 422, refused.text
    assert isinstance(refused.json()["detail"], str)
    assert "outside the session scope" in refused.json()["detail"]
    assert unauthenticated.status_code in {401, 403}
    assert client.get_agent_session(session.session_id).status == "active"
    assert client.list_agent_interventions(session.session_id) == []
    assert slack.calls == []


def test_evaluation_error_text_reaches_no_record_audit_or_slack(lab) -> None:
    """A raw evaluation error carries a fake secret; only its class and the ids are kept."""
    from unittest.mock import MagicMock

    from qdash.client.services.client_models import TaskNextAction
    from qdash.client.services.evaluation_planner import EvaluationPlanner
    from qdash.dbmodel.agent_session import AgentInterventionDocument

    marker = "SYNTHETIC_SECRET_MARKER xoxb-FAKE-TOKEN-0000"
    client, slack, http = lab
    session = client.create_agent_session(
        chip_id="chip-001",
        policy={
            "qids": ["Q00"],
            "allowed_tasks": ["CheckRabi", "CheckChevron"],
            "allowed_overrides": {
                "control_amplitude": {"minimum": 0.0, "maximum": 1.0},
                "qubit_frequency": {"minimum": 7.0, "maximum": 8.0},
            },
            "max_actions": 4,
            "autonomy": "auto",
        },
    )
    evaluator = MagicMock()
    evaluator.create_evaluation_run.side_effect = RuntimeError(marker)
    planner = EvaluationPlanner(
        evaluator,
        chip_id="chip-001",
        allowed_overrides={"control_amplitude": {"minimum": 0.0, "maximum": 1.0}},
        next_actions=lambda task_name: {"SUCCESS": TaskNextAction(action="continue")},
        poll_interval_seconds=0,
    )
    runner = AgentPlanRunner(client, step_runner=SimulatedStepRunner(client))  # type: ignore[arg-type]

    stopped = runner.run_plan(
        session_id=session.session_id,
        qid="Q00",
        nodes=NODES,
        planner=planner,
        max_node_executions=4,
        max_node_visits=2,
        idempotency_prefix="plan-redact",
        record_interventions=True,
        planner_name="evaluation",
    )

    assert stopped.intervention is not None, stopped.intervention_error
    intervention_id = stopped.intervention.intervention_id
    headers = {"Authorization": "Bearer owner-token", "X-Project-Id": "lab-a"}
    stored = AgentInterventionDocument.find_one({"intervention_id": intervention_id}).run()
    assert stored is not None
    api = http.get(
        f"/agent-sessions/{session.session_id}/interventions/{intervention_id}", headers=headers
    )
    audit = http.get(f"/agent-sessions/{session.session_id}/audit/export", headers=headers)
    assert api.status_code == 200, api.text
    assert audit.status_code == 200, audit.text
    for text in (
        stored.model_dump_json(),
        api.text,
        audit.text,
        repr(slack.calls),
        stopped.reason,
    ):
        assert "SYNTHETIC_SECRET_MARKER" not in text
        assert "xoxb-FAKE-TOKEN-0000" not in text
    # The safe diagnostic and the references stay useful to the expert.
    assert "Evaluating task result task-1 failed (RuntimeError)" in stored.summary
    assert stored.attempts[0].task_id == "task-1"
    assert stored.attempts[0].execution_id == "exec-1"
    assert len(slack.calls) == 1
    assert slack.calls[0]["text"] == "Agent needs an expert: Evaluation failed (chip-001 Q00)"
