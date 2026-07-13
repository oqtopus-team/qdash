"""Tests for the user-side agent calibration Skill runner."""

from __future__ import annotations

from unittest.mock import MagicMock

from qdash.client.services.agent_runner import (
    AgentCalibrationRunner,
    AgentCampaignNode,
    AgentCampaignRunner,
    AgentSkillTransition,
    AgentStepOutcome,
)
from qdash.client.services.errors import (
    QDashTransportError,
    QDashValidationError,
)
from qdash.client.services.models import (
    AgentActionResponse,
    AgentCandidateCommitResponse,
    AgentCandidateResponse,
    AgentSessionResponse,
    ExecutionResponseDetail,
)


def _session(state_version: int) -> AgentSessionResponse:
    return AgentSessionResponse.model_validate(
        {
            "session_id": "session-1",
            "project_id": "project-1",
            "chip_id": "chip-1",
            "created_by": "tester",
            "policy": {
                "qids": ["Q00"],
                "allowed_tasks": ["CheckT1"],
                "allowed_actions": ["run_task"],
                "allowed_overrides": {
                    "t1": {"minimum": 1.0, "maximum": 500.0},
                },
                "max_actions": 10,
            },
            "skill_name": "qubit-characterize",
            "skill_version": "1",
            "skill_hash": "sha256:test",
            "model_name": "local-model",
            "status": "active",
            "state_version": state_version,
            "action_count": state_version,
            "created_at": "2026-07-13T00:00:00Z",
            "updated_at": "2026-07-13T00:00:00Z",
            "expires_at": "2026-07-13T01:00:00Z",
        }
    )


def _action(*, decision: str = "authorized") -> AgentActionResponse:
    return AgentActionResponse.model_validate(
        {
            "action_id": "action-1",
            "session_id": "session-1",
            "idempotency_key": "action-key",
            "action_type": "run_task",
            "task_name": "CheckT1",
            "qids": ["Q00"],
            "parameter_overrides": {},
            "diagnosis": "",
            "decision": decision,
            "reason": "allowed" if decision == "authorized" else "policy rejected",
            "execution_status": "queued" if decision == "authorized" else "not_started",
            "operation_id": "operation-1" if decision == "authorized" else None,
            "execution_id": "execution-1" if decision == "authorized" else None,
            "state_version_before": 0,
            "state_version_after": 1,
            "created_at": "2026-07-13T00:00:01Z",
        }
    )


def _candidate(*, accepted: bool) -> AgentCandidateResponse:
    return AgentCandidateResponse(
        session_id="session-1",
        action_id="action-1",
        execution_id="execution-1",
        task_id="task-1",
        task_name="CheckT1",
        qid="Q00",
        source_parameter_name="t1",
        parameter_name="t1",
        value=95.0 if accepted else 900.0,
        error=2.0,
        unit="us",
        value_type="float",
        accepted=accepted,
        reason="passed" if accepted else "above maximum",
        minimum=1.0,
        maximum=500.0,
    )


def _execution() -> ExecutionResponseDetail:
    return ExecutionResponseDetail.model_validate(
        {
            "name": "agent-execution",
            "status": "completed",
            "flow_name": "re-execute:CheckT1",
            "username": "tester",
            "task": [],
            "note": {},
            "tags": ["agent-session:session-1"],
            "chip_id": "chip-1",
        }
    )


def _commit() -> AgentCandidateCommitResponse:
    return AgentCandidateCommitResponse.model_validate(
        {
            "commit_id": "commit-1",
            "session_id": "session-1",
            "action_id": "action-1",
            "idempotency_key": "commit-key",
            "execution_id": "execution-1",
            "task_id": "task-1",
            "task_name": "CheckT1",
            "qid": "Q00",
            "parameter_name": "t1",
            "value": 95.0,
            "status": "committed",
            "reason": "committed",
            "before_snapshot": None,
            "after_snapshot": {"value": 95.0},
            "committed_by": "tester",
            "state_version_before": 1,
            "state_version_after": 2,
            "created_at": "2026-07-13T00:00:02Z",
            "committed_at": "2026-07-13T00:00:02Z",
        }
    )


def test_run_step_passes_and_commits_authoritative_candidate() -> None:
    client = MagicMock()
    client.get_agent_session.side_effect = [_session(0), _session(1)]
    client.submit_agent_action.return_value = _action()
    client.execute_agent_action.return_value = _action()
    client.wait_for_agent_action.return_value = _action()
    client.wait_for_agent_action_execution.return_value = _action()
    client.wait_for_execution.return_value = _execution()
    client.list_agent_action_candidates.return_value = [_candidate(accepted=True)]
    client.commit_agent_action_candidate.return_value = _commit()
    runner = AgentCalibrationRunner(client, poll_interval_seconds=0)

    outcome = runner.run_step(
        session_id="session-1",
        task_name="CheckT1",
        qid="Q00",
        source_execution_id="source-1",
        candidate_parameter="t1",
        commit_candidate=True,
        action_idempotency_key="action-key",
        commit_idempotency_key="commit-key",
    )

    assert outcome.transition == AgentSkillTransition.PASS
    assert outcome.operation_id == "operation-1"
    assert outcome.execution_id == "execution-1"
    assert outcome.commit is not None
    client.wait_for_execution.assert_called_once_with(
        "execution-1",
        timeout_seconds=600.0,
        poll_interval_seconds=0,
    )
    client.execute_agent_action.assert_called_once_with(
        "session-1",
        "action-1",
        source_execution_id="source-1",
        update_params=False,
        reconfigure=False,
    )
    client.commit_agent_action_candidate.assert_called_once_with(
        "session-1",
        "action-1",
        "t1",
        idempotency_key="commit-key",
        expected_state_version=1,
        task_id="task-1",
    )


def test_run_step_applies_and_verifies_backend_after_commit() -> None:
    client = MagicMock()
    client.get_agent_session.side_effect = [_session(0), _session(1), _session(2)]
    client.submit_agent_action.return_value = _action()
    client.execute_agent_action.return_value = _action()
    client.wait_for_agent_action.return_value = _action()
    client.wait_for_agent_action_execution.return_value = _action()
    client.wait_for_execution.return_value = _execution()
    client.list_agent_action_candidates.return_value = [_candidate(accepted=True)]
    client.commit_agent_action_candidate.return_value = _commit()
    applied = _commit().model_copy(
        update={
            "backend_status": "applied",
            "backend_operation_id": "backend-operation-1",
            "backend_name": "fake",
            "backend_target_files": ["t1.yaml"],
            "backend_changed_files": ["t1.yaml"],
            "backend_verified": True,
            "backend_git_commit": "abc12345",
        }
    )
    client.apply_agent_candidate_commit.return_value = applied.model_copy(
        update={"backend_status": "queued", "backend_verified": False}
    )
    client.wait_for_agent_candidate_apply.return_value = applied
    runner = AgentCalibrationRunner(client, poll_interval_seconds=0)

    outcome = runner.run_step(
        session_id="session-1",
        task_name="CheckT1",
        qid="Q00",
        source_execution_id="source-1",
        candidate_parameter="t1",
        commit_candidate=True,
        apply_backend=True,
        action_idempotency_key="action-key",
        commit_idempotency_key="commit-key",
        backend_apply_idempotency_key="apply-key",
    )

    assert outcome.transition == AgentSkillTransition.PASS
    assert outcome.reason == "Candidate passed, was committed, and backend-verified"
    assert outcome.commit is not None
    assert outcome.commit.backend_git_commit == "abc12345"
    client.apply_agent_candidate_commit.assert_called_once_with(
        "session-1",
        "commit-1",
        idempotency_key="apply-key",
        expected_state_version=2,
        push_to_github=False,
    )
    client.wait_for_agent_candidate_apply.assert_called_once()


def test_run_step_rolls_back_after_gate_rejection() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _session(0)
    client.submit_agent_action.return_value = _action()
    client.execute_agent_action.return_value = _action()
    client.wait_for_agent_action.return_value = _action()
    client.wait_for_agent_action_execution.return_value = _action()
    client.wait_for_execution.return_value = _execution()
    client.list_agent_action_candidates.return_value = [_candidate(accepted=False)]
    runner = AgentCalibrationRunner(client, poll_interval_seconds=0)

    outcome = runner.run_step(
        session_id="session-1",
        task_name="CheckT1",
        qid="Q00",
        source_execution_id="source-1",
        candidate_parameter="t1",
        commit_candidate=True,
    )

    assert outcome.transition == AgentSkillTransition.ROLLBACK
    assert outcome.candidate is not None
    client.commit_agent_action_candidate.assert_not_called()


def test_run_step_escalates_policy_rejection() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _session(0)
    client.submit_agent_action.return_value = _action(decision="rejected")
    runner = AgentCalibrationRunner(client, poll_interval_seconds=0)

    outcome = runner.run_step(
        session_id="session-1",
        task_name="CheckT1",
        qid="Q00",
        source_execution_id="source-1",
        candidate_parameter="t1",
    )

    assert outcome.transition == AgentSkillTransition.HUMAN_ESCALATION
    client.execute_agent_action.assert_not_called()


def _client_ready_for_candidate() -> MagicMock:
    client = MagicMock()
    client.get_agent_session.return_value = _session(0)
    client.submit_agent_action.return_value = _action()
    client.execute_agent_action.return_value = _action()
    client.wait_for_agent_action.return_value = _action()
    client.wait_for_agent_action_execution.return_value = _action()
    client.wait_for_execution.return_value = _execution()
    client.list_agent_action_candidates.return_value = [_candidate(accepted=True)]
    return client


def test_run_step_retries_transient_api_error() -> None:
    client = MagicMock()
    client.get_agent_session.side_effect = QDashTransportError("network unavailable")
    runner = AgentCalibrationRunner(client, poll_interval_seconds=0)

    outcome = runner.run_step(
        session_id="session-1",
        task_name="CheckT1",
        qid="Q00",
        source_execution_id="source-1",
        candidate_parameter="t1",
    )

    assert outcome.transition == AgentSkillTransition.RETRY
    assert outcome.action_id is None
    assert "network unavailable" in outcome.reason


def test_run_step_escalates_commit_validation_error_with_provenance() -> None:
    client = _client_ready_for_candidate()
    client.get_agent_session.side_effect = [_session(0), _session(1)]
    client.commit_agent_action_candidate.side_effect = QDashValidationError(
        "state version conflict",
        status_code=409,
    )
    runner = AgentCalibrationRunner(client, poll_interval_seconds=0)

    outcome = runner.run_step(
        session_id="session-1",
        task_name="CheckT1",
        qid="Q00",
        source_execution_id="source-1",
        candidate_parameter="t1",
        commit_candidate=True,
    )

    assert outcome.transition == AgentSkillTransition.HUMAN_ESCALATION
    assert outcome.action_id == "action-1"
    assert outcome.operation_id == "operation-1"
    assert outcome.execution_id == "execution-1"
    assert outcome.candidate is not None


def test_run_step_backend_timeout_preserves_execution_id() -> None:
    client = _client_ready_for_candidate()
    client.get_agent_session.side_effect = [_session(0), _session(1), _session(2)]
    client.commit_agent_action_candidate.return_value = _commit()
    client.apply_agent_candidate_commit.return_value = _commit().model_copy(
        update={"backend_status": "queued"}
    )
    client.wait_for_agent_candidate_apply.side_effect = TimeoutError("apply timed out")
    runner = AgentCalibrationRunner(client, poll_interval_seconds=0)

    outcome = runner.run_step(
        session_id="session-1",
        task_name="CheckT1",
        qid="Q00",
        source_execution_id="source-1",
        candidate_parameter="t1",
        commit_candidate=True,
        apply_backend=True,
    )

    assert outcome.transition == AgentSkillTransition.RETRY
    assert outcome.execution_id == "execution-1"


def test_run_step_backend_verification_failure_preserves_execution_id() -> None:
    client = _client_ready_for_candidate()
    client.get_agent_session.side_effect = [_session(0), _session(1), _session(2)]
    client.commit_agent_action_candidate.return_value = _commit()
    queued = _commit().model_copy(update={"backend_status": "queued"})
    client.apply_agent_candidate_commit.return_value = queued
    client.wait_for_agent_candidate_apply.return_value = queued.model_copy(
        update={
            "backend_status": "failed",
            "backend_verified": False,
            "backend_error": "verification failed",
        }
    )
    runner = AgentCalibrationRunner(client, poll_interval_seconds=0)

    outcome = runner.run_step(
        session_id="session-1",
        task_name="CheckT1",
        qid="Q00",
        source_execution_id="source-1",
        candidate_parameter="t1",
        commit_candidate=True,
        apply_backend=True,
    )

    assert outcome.transition == AgentSkillTransition.HUMAN_ESCALATION
    assert outcome.execution_id == "execution-1"


def _campaign_session(*, max_actions: int = 4, action_count: int = 0) -> AgentSessionResponse:
    session = _session(action_count)
    return session.model_copy(
        update={
            "action_count": action_count,
            "policy": session.policy.model_copy(
                update={
                    "allowed_tasks": ["CheckT1", "CheckT2"],
                    "allowed_overrides": {
                        "t1": {"minimum": 1.0, "maximum": 500.0},
                        "t2": {"minimum": 1.0, "maximum": 700.0},
                    },
                    "max_actions": max_actions,
                }
            ),
        }
    )


def _campaign_step(
    parameter_name: str,
    value: float,
    *,
    transition: AgentSkillTransition = AgentSkillTransition.PASS,
    operation_id: str | None = "operation-1",
) -> AgentStepOutcome:
    candidate = _candidate(accepted=transition == AgentSkillTransition.PASS).model_copy(
        update={
            "parameter_name": parameter_name,
            "source_parameter_name": parameter_name,
            "value": value,
        }
    )
    return AgentStepOutcome(
        transition=transition,
        reason="step result",
        session_id="session-1",
        operation_id=operation_id,
        execution_id="execution-1" if operation_id else None,
        candidate=candidate if transition != AgentSkillTransition.RETRY else None,
    )


def test_campaign_propagates_accepted_candidates_with_fixed_source() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _campaign_session()
    step_runner = MagicMock()
    step_runner.run_step.side_effect = [
        _campaign_step("t1", 95.0),
        _campaign_step("t2", 130.0),
    ]
    runner = AgentCampaignRunner(client, step_runner=step_runner)

    outcome = runner.run_campaign(
        session_id="session-1",
        qid="Q00",
        source_execution_id="source-1",
        nodes=[
            AgentCampaignNode(task_name="CheckT1", candidate_parameter="t1"),
            AgentCampaignNode(task_name="CheckT2", candidate_parameter="t2"),
        ],
        idempotency_prefix="campaign-key",
    )

    assert outcome.transition == AgentSkillTransition.PASS
    assert outcome.completed_nodes == 2
    assert outcome.node_path == ("node-0", "node-1")
    assert outcome.carried_overrides == {"t1": 95.0, "t2": 130.0}
    first_call, second_call = step_runner.run_step.call_args_list
    assert first_call.kwargs["source_execution_id"] == "source-1"
    assert second_call.kwargs["source_execution_id"] == "source-1"
    assert first_call.kwargs["parameter_overrides"] == {}
    assert second_call.kwargs["parameter_overrides"] == {"t1": 95.0}
    assert second_call.kwargs["action_idempotency_key"] == "campaign-key-node-1-action"


def test_campaign_explicit_node_override_wins_over_carried_candidate() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _campaign_session()
    step_runner = MagicMock()
    step_runner.run_step.side_effect = [
        _campaign_step("t1", 95.0),
        _campaign_step("t2", 130.0),
    ]
    runner = AgentCampaignRunner(client, step_runner=step_runner)

    runner.run_campaign(
        session_id="session-1",
        qid="Q00",
        source_execution_id="source-1",
        nodes=[
            AgentCampaignNode(task_name="CheckT1", candidate_parameter="t1"),
            AgentCampaignNode(
                task_name="CheckT2",
                candidate_parameter="t2",
                parameter_overrides={"t1": 100.0},
            ),
        ],
    )

    second_call = step_runner.run_step.call_args_list[1]
    assert second_call.kwargs["parameter_overrides"] == {"t1": 100.0}


def test_campaign_stops_immediately_on_rollback() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _campaign_session()
    step_runner = MagicMock()
    step_runner.run_step.return_value = _campaign_step(
        "t1",
        900.0,
        transition=AgentSkillTransition.ROLLBACK,
    )
    runner = AgentCampaignRunner(client, step_runner=step_runner)

    outcome = runner.run_campaign(
        session_id="session-1",
        qid="Q00",
        source_execution_id="source-1",
        nodes=[
            AgentCampaignNode(task_name="CheckT1", candidate_parameter="t1"),
            AgentCampaignNode(task_name="CheckT2", candidate_parameter="t2"),
        ],
    )

    assert outcome.transition == AgentSkillTransition.ROLLBACK
    assert outcome.completed_nodes == 0
    step_runner.run_step.assert_called_once()


def test_campaign_retries_only_before_an_operation_exists() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _campaign_session()
    step_runner = MagicMock()
    step_runner.run_step.side_effect = [
        AgentStepOutcome(
            transition=AgentSkillTransition.RETRY,
            reason="temporary dispatch error",
            session_id="session-1",
        ),
        _campaign_step("t1", 95.0),
    ]
    runner = AgentCampaignRunner(client, step_runner=step_runner)

    outcome = runner.run_campaign(
        session_id="session-1",
        qid="Q00",
        source_execution_id="source-1",
        nodes=[AgentCampaignNode(task_name="CheckT1", candidate_parameter="t1")],
        max_pre_dispatch_retries=1,
        idempotency_prefix="stable",
    )

    assert outcome.transition == AgentSkillTransition.PASS
    assert outcome.attempts == 2
    calls = step_runner.run_step.call_args_list
    assert calls[0].kwargs["action_idempotency_key"] == "stable-node-0-action"
    assert calls[1].kwargs["action_idempotency_key"] == "stable-node-0-action"


def test_campaign_does_not_retry_after_hardware_operation_exists() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _campaign_session()
    step_runner = MagicMock()
    step_runner.run_step.return_value = AgentStepOutcome(
        transition=AgentSkillTransition.RETRY,
        reason="execution timed out",
        session_id="session-1",
        operation_id="operation-1",
    )
    runner = AgentCampaignRunner(client, step_runner=step_runner)

    outcome = runner.run_campaign(
        session_id="session-1",
        qid="Q00",
        source_execution_id="source-1",
        nodes=[AgentCampaignNode(task_name="CheckT1", candidate_parameter="t1")],
        max_pre_dispatch_retries=3,
    )

    assert outcome.transition == AgentSkillTransition.RETRY
    step_runner.run_step.assert_called_once()


def test_campaign_preflight_rejects_insufficient_action_budget() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _campaign_session(max_actions=1)
    step_runner = MagicMock()
    runner = AgentCampaignRunner(client, step_runner=step_runner)

    outcome = runner.run_campaign(
        session_id="session-1",
        qid="Q00",
        source_execution_id="source-1",
        nodes=[
            AgentCampaignNode(task_name="CheckT1", candidate_parameter="t1"),
            AgentCampaignNode(task_name="CheckT2", candidate_parameter="t2"),
        ],
    )

    assert outcome.transition == AgentSkillTransition.HUMAN_ESCALATION
    assert "1 remaining" in outcome.reason
    step_runner.run_step.assert_not_called()


def test_campaign_routes_rollback_through_recovery_and_revisits_node() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _campaign_session(max_actions=3)
    step_runner = MagicMock()
    step_runner.run_step.side_effect = [
        _campaign_step("t1", 900.0, transition=AgentSkillTransition.ROLLBACK),
        _campaign_step("t2", 130.0),
        _campaign_step("t1", 95.0),
    ]
    runner = AgentCampaignRunner(client, step_runner=step_runner)

    outcome = runner.run_campaign(
        session_id="session-1",
        qid="Q00",
        source_execution_id="source-1",
        nodes=[
            AgentCampaignNode(
                node_id="calibrate",
                task_name="CheckT1",
                candidate_parameter="t1",
                on_pass="$complete",
                on_rollback="diagnose",
            ),
            AgentCampaignNode(
                node_id="diagnose",
                task_name="CheckT2",
                candidate_parameter="t2",
                on_pass="calibrate",
            ),
        ],
        max_node_executions=3,
        idempotency_prefix="graph",
    )

    assert outcome.transition == AgentSkillTransition.PASS
    assert outcome.completed_nodes == 2
    assert outcome.node_path == ("calibrate", "diagnose", "calibrate")
    assert outcome.carried_overrides == {"t2": 130.0, "t1": 95.0}
    calls = step_runner.run_step.call_args_list
    assert calls[0].kwargs["action_idempotency_key"] == "graph-node-0-action"
    assert calls[2].kwargs["action_idempotency_key"] == "graph-node-0-visit-1-action"
    assert calls[2].kwargs["parameter_overrides"] == {"t2": 130.0}


def test_campaign_escalates_when_graph_reaches_execution_limit() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _campaign_session(max_actions=2)
    step_runner = MagicMock()
    step_runner.run_step.return_value = _campaign_step(
        "t1",
        900.0,
        transition=AgentSkillTransition.ROLLBACK,
    )
    runner = AgentCampaignRunner(client, step_runner=step_runner)

    outcome = runner.run_campaign(
        session_id="session-1",
        qid="Q00",
        source_execution_id="source-1",
        nodes=[
            AgentCampaignNode(
                node_id="calibrate",
                task_name="CheckT1",
                candidate_parameter="t1",
                on_rollback="calibrate",
            )
        ],
        max_node_executions=2,
    )

    assert outcome.transition == AgentSkillTransition.HUMAN_ESCALATION
    assert "2 node execution limit" in outcome.reason
    assert outcome.node_path == ("calibrate", "calibrate")
    assert step_runner.run_step.call_count == 2


def test_campaign_rejects_unknown_graph_target_before_session_lookup() -> None:
    client = MagicMock()
    step_runner = MagicMock()
    runner = AgentCampaignRunner(client, step_runner=step_runner)

    outcome = runner.run_campaign(
        session_id="session-1",
        qid="Q00",
        source_execution_id="source-1",
        nodes=[
            AgentCampaignNode(
                node_id="calibrate",
                task_name="CheckT1",
                candidate_parameter="t1",
                on_rollback="missing",
            )
        ],
    )

    assert outcome.transition == AgentSkillTransition.HUMAN_ESCALATION
    assert "target 'missing' does not exist" in outcome.reason
    client.get_agent_session.assert_not_called()
    step_runner.run_step.assert_not_called()


def test_campaign_rejects_reserved_complete_node_id() -> None:
    client = MagicMock()
    step_runner = MagicMock()
    runner = AgentCampaignRunner(client, step_runner=step_runner)

    outcome = runner.run_campaign(
        session_id="session-1",
        qid="Q00",
        source_execution_id="source-1",
        nodes=[
            AgentCampaignNode(
                node_id="$complete",
                task_name="CheckT1",
                candidate_parameter="t1",
            )
        ],
    )

    assert outcome.transition == AgentSkillTransition.HUMAN_ESCALATION
    assert "is reserved" in outcome.reason
    client.get_agent_session.assert_not_called()
    step_runner.run_step.assert_not_called()
