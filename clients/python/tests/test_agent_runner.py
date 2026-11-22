"""Tests for the user-side agent calibration Skill runner."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from qdash.client.services.agent_runner import (
    PLAN_COMPLETE,
    PLAN_DEFAULT,
    PLAN_ESCALATE,
    AgentCalibrationRunner,
    AgentInterventionReason,
    AgentPlannerDecision,
    AgentPlanNode,
    AgentPlanOutcome,
    AgentPlanResumeState,
    AgentPlanRunner,
    AgentSkillTransition,
    AgentStepOutcome,
    resume_state_from_intervention,
)
from qdash.client.services.client_models import (
    AgentActionResponse,
    AgentCandidateCommitResponse,
    AgentCandidateResponse,
    AgentCandidateSetCommitResponse,
    AgentInterventionResponse,
    AgentSessionResponse,
)
from qdash.client.services.errors import (
    QDashApiError,
    QDashAuthError,
    QDashTransportError,
    QDashValidationError,
)
from qdash.client.services.models import (
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


def _candidate_set_commit() -> AgentCandidateSetCommitResponse:
    return AgentCandidateSetCommitResponse.model_validate(
        {
            "commit_id": "candidate-set-commit-1",
            "session_id": "session-1",
            "idempotency_key": "plan-key-candidate-set-commit",
            "chip_id": "chip-1",
            "qid": "Q00",
            "candidates": [
                _candidate(accepted=True).model_copy(
                    update={"parameter_name": "t1", "source_parameter_name": "t1"}
                )
            ],
            "status": "committed",
            "reason": "committed",
            "before_snapshot": {"t1": None},
            "after_snapshot": {"t1": {"value": 95.0}},
            "committed_by": "tester",
            "state_version_before": 2,
            "state_version_after": 3,
            "created_at": "2026-07-13T00:00:03Z",
            "committed_at": "2026-07-13T00:00:03Z",
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
    # The reason names the failure class, never the transport's own text.
    assert outcome.reason == "QDash API request failed (QDashTransportError)"
    assert "network unavailable" not in outcome.reason


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


def _plan_session(*, max_actions: int = 4, action_count: int = 0) -> AgentSessionResponse:
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


def _plan_step(
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


def test_plan_propagates_accepted_candidates_with_fixed_source() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _plan_session()
    step_runner = MagicMock()
    step_runner.run_step.side_effect = [
        _plan_step("t1", 95.0),
        _plan_step("t2", 130.0),
    ]
    runner = AgentPlanRunner(client, step_runner=step_runner)

    outcome = runner.run_plan(
        session_id="session-1",
        qid="Q00",
        source_execution_id="source-1",
        nodes=[
            AgentPlanNode(task_name="CheckT1", candidate_parameter="t1"),
            AgentPlanNode(task_name="CheckT2", candidate_parameter="t2"),
        ],
        idempotency_prefix="plan-key",
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
    assert second_call.kwargs["action_idempotency_key"] == "plan-key-node-1-action"


def test_plan_explicit_node_override_wins_over_carried_candidate() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _plan_session()
    step_runner = MagicMock()
    step_runner.run_step.side_effect = [
        _plan_step("t1", 95.0),
        _plan_step("t2", 130.0),
    ]
    runner = AgentPlanRunner(client, step_runner=step_runner)

    runner.run_plan(
        session_id="session-1",
        qid="Q00",
        source_execution_id="source-1",
        nodes=[
            AgentPlanNode(task_name="CheckT1", candidate_parameter="t1"),
            AgentPlanNode(
                task_name="CheckT2",
                candidate_parameter="t2",
                parameter_overrides={"t1": 100.0},
            ),
        ],
    )

    second_call = step_runner.run_step.call_args_list[1]
    assert second_call.kwargs["parameter_overrides"] == {"t1": 100.0}


def test_plan_stops_immediately_on_rollback() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _plan_session()
    step_runner = MagicMock()
    step_runner.run_step.return_value = _plan_step(
        "t1",
        900.0,
        transition=AgentSkillTransition.ROLLBACK,
    )
    runner = AgentPlanRunner(client, step_runner=step_runner)

    outcome = runner.run_plan(
        session_id="session-1",
        qid="Q00",
        source_execution_id="source-1",
        nodes=[
            AgentPlanNode(task_name="CheckT1", candidate_parameter="t1"),
            AgentPlanNode(task_name="CheckT2", candidate_parameter="t2"),
        ],
    )

    assert outcome.transition == AgentSkillTransition.ROLLBACK
    assert outcome.completed_nodes == 0
    step_runner.run_step.assert_called_once()


def test_plan_retries_only_before_an_operation_exists() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _plan_session()
    step_runner = MagicMock()
    step_runner.run_step.side_effect = [
        AgentStepOutcome(
            transition=AgentSkillTransition.RETRY,
            reason="temporary dispatch error",
            session_id="session-1",
        ),
        _plan_step("t1", 95.0),
    ]
    runner = AgentPlanRunner(client, step_runner=step_runner)

    outcome = runner.run_plan(
        session_id="session-1",
        qid="Q00",
        source_execution_id="source-1",
        nodes=[AgentPlanNode(task_name="CheckT1", candidate_parameter="t1")],
        max_pre_dispatch_retries=1,
        idempotency_prefix="stable",
    )

    assert outcome.transition == AgentSkillTransition.PASS
    assert outcome.attempts == 2
    calls = step_runner.run_step.call_args_list
    assert calls[0].kwargs["action_idempotency_key"] == "stable-node-0-action"
    assert calls[1].kwargs["action_idempotency_key"] == "stable-node-0-action"


def test_plan_does_not_retry_after_hardware_operation_exists() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _plan_session()
    step_runner = MagicMock()
    step_runner.run_step.return_value = AgentStepOutcome(
        transition=AgentSkillTransition.RETRY,
        reason="execution timed out",
        session_id="session-1",
        operation_id="operation-1",
    )
    runner = AgentPlanRunner(client, step_runner=step_runner)

    outcome = runner.run_plan(
        session_id="session-1",
        qid="Q00",
        source_execution_id="source-1",
        nodes=[AgentPlanNode(task_name="CheckT1", candidate_parameter="t1")],
        max_pre_dispatch_retries=3,
    )

    assert outcome.transition == AgentSkillTransition.RETRY
    step_runner.run_step.assert_called_once()


def test_plan_preflight_rejects_insufficient_action_budget() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _plan_session(max_actions=1)
    step_runner = MagicMock()
    runner = AgentPlanRunner(client, step_runner=step_runner)

    outcome = runner.run_plan(
        session_id="session-1",
        qid="Q00",
        source_execution_id="source-1",
        nodes=[
            AgentPlanNode(task_name="CheckT1", candidate_parameter="t1"),
            AgentPlanNode(task_name="CheckT2", candidate_parameter="t2"),
        ],
    )

    assert outcome.transition == AgentSkillTransition.HUMAN_ESCALATION
    assert "1 remaining" in outcome.reason
    step_runner.run_step.assert_not_called()


def test_plan_routes_rollback_through_recovery_and_revisits_node() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _plan_session(max_actions=3)
    step_runner = MagicMock()
    step_runner.run_step.side_effect = [
        _plan_step("t1", 900.0, transition=AgentSkillTransition.ROLLBACK),
        _plan_step("t2", 130.0),
        _plan_step("t1", 95.0),
    ]
    runner = AgentPlanRunner(client, step_runner=step_runner)

    outcome = runner.run_plan(
        session_id="session-1",
        qid="Q00",
        source_execution_id="source-1",
        nodes=[
            AgentPlanNode(
                node_id="calibrate",
                task_name="CheckT1",
                candidate_parameter="t1",
                on_pass="$complete",
                on_rollback="diagnose",
            ),
            AgentPlanNode(
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


def test_plan_escalates_when_graph_reaches_execution_limit() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _plan_session(max_actions=2)
    step_runner = MagicMock()
    step_runner.run_step.return_value = _plan_step(
        "t1",
        900.0,
        transition=AgentSkillTransition.ROLLBACK,
    )
    runner = AgentPlanRunner(client, step_runner=step_runner)

    outcome = runner.run_plan(
        session_id="session-1",
        qid="Q00",
        source_execution_id="source-1",
        nodes=[
            AgentPlanNode(
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


def test_plan_rejects_unknown_graph_target_before_session_lookup() -> None:
    client = MagicMock()
    step_runner = MagicMock()
    runner = AgentPlanRunner(client, step_runner=step_runner)

    outcome = runner.run_plan(
        session_id="session-1",
        qid="Q00",
        source_execution_id="source-1",
        nodes=[
            AgentPlanNode(
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


def test_plan_rejects_reserved_complete_node_id() -> None:
    client = MagicMock()
    step_runner = MagicMock()
    runner = AgentPlanRunner(client, step_runner=step_runner)

    outcome = runner.run_plan(
        session_id="session-1",
        qid="Q00",
        source_execution_id="source-1",
        nodes=[
            AgentPlanNode(
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


def test_plan_commits_latest_candidate_set_only_after_success() -> None:
    client = MagicMock()
    client.get_agent_session.side_effect = [
        _plan_session(max_actions=2),
        _plan_session(max_actions=2, action_count=2),
    ]
    client.commit_agent_candidate_set.return_value = _candidate_set_commit()
    step_runner = MagicMock()
    step_runner.run_step.side_effect = [
        _plan_step("t1", 90.0),
        _plan_step("t1", 95.0),
    ]
    runner = AgentPlanRunner(client, step_runner=step_runner)

    outcome = runner.run_plan(
        session_id="session-1",
        qid="Q00",
        source_execution_id="source-1",
        nodes=[
            AgentPlanNode(task_name="CheckT1", candidate_parameter="t1"),
            AgentPlanNode(task_name="CheckT1", candidate_parameter="t1"),
        ],
        commit_on_success=True,
        idempotency_prefix="plan-key",
    )

    assert outcome.transition == AgentSkillTransition.PASS
    assert outcome.candidate_set_commit is not None
    assert outcome.candidate_set_commit.commit_id == "candidate-set-commit-1"
    client.commit_agent_candidate_set.assert_called_once_with(
        "session-1",
        [
            {
                "action_id": "action-1",
                "parameter_name": "t1",
                "task_id": "task-1",
            }
        ],
        idempotency_key="plan-key-candidate-set-commit",
        expected_state_version=2,
    )


def test_plan_does_not_commit_after_rollback() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _plan_session()
    step_runner = MagicMock()
    step_runner.run_step.return_value = _plan_step(
        "t1",
        900.0,
        transition=AgentSkillTransition.ROLLBACK,
    )
    runner = AgentPlanRunner(client, step_runner=step_runner)

    outcome = runner.run_plan(
        session_id="session-1",
        qid="Q00",
        source_execution_id="source-1",
        nodes=[AgentPlanNode(task_name="CheckT1", candidate_parameter="t1")],
        commit_on_success=True,
    )

    assert outcome.transition == AgentSkillTransition.ROLLBACK
    client.commit_agent_candidate_set.assert_not_called()


def test_plan_planner_selects_only_pre_authorized_nodes() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _plan_session(max_actions=2)
    step_runner = MagicMock()
    step_runner.run_step.side_effect = [
        _plan_step("t1", 900.0, transition=AgentSkillTransition.ROLLBACK),
        _plan_step("t2", 130.0),
    ]
    planner = MagicMock()
    planner.choose_next.side_effect = [
        AgentPlannerDecision(target_node_id="diagnose", reason="inspect coherence"),
        AgentPlannerDecision(target_node_id="$complete", reason="recovery accepted"),
    ]
    runner = AgentPlanRunner(client, step_runner=step_runner)

    outcome = runner.run_plan(
        session_id="session-1",
        qid="Q00",
        source_execution_id="source-1",
        nodes=[
            AgentPlanNode(node_id="calibrate", task_name="CheckT1", candidate_parameter="t1"),
            AgentPlanNode(node_id="diagnose", task_name="CheckT2", candidate_parameter="t2"),
        ],
        max_node_executions=2,
        planner=planner,
    )

    assert outcome.transition == AgentSkillTransition.PASS
    assert outcome.node_path == ("calibrate", "diagnose")
    assert outcome.planner_decisions == (
        AgentPlannerDecision(target_node_id="diagnose", reason="inspect coherence"),
        AgentPlannerDecision(target_node_id="$complete", reason="recovery accepted"),
    )
    first_observation = planner.choose_next.call_args_list[0].args[0]
    assert first_observation.available_node_ids == ("calibrate", "diagnose")
    assert first_observation.remaining_node_executions == 1


def test_plan_planner_unknown_node_escalates_without_dispatch() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _plan_session()
    step_runner = MagicMock()
    step_runner.run_step.return_value = _plan_step("t1", 95.0)
    planner = MagicMock()
    planner.choose_next.return_value = AgentPlannerDecision(target_node_id="outside-policy")
    runner = AgentPlanRunner(client, step_runner=step_runner)

    outcome = runner.run_plan(
        session_id="session-1",
        qid="Q00",
        source_execution_id="source-1",
        nodes=[AgentPlanNode(task_name="CheckT1", candidate_parameter="t1")],
        planner=planner,
    )

    assert outcome.transition == AgentSkillTransition.HUMAN_ESCALATION
    assert "unknown node 'outside-policy'" in outcome.reason
    step_runner.run_step.assert_called_once()


def test_plan_planner_default_follows_the_plan_and_records_the_decision() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _plan_session(max_actions=3)
    step_runner = MagicMock()
    step_runner.run_step.side_effect = [_plan_step("t1", 95.0), _plan_step("t2", 130.0)]
    planner = MagicMock()
    planner.choose_next.side_effect = [
        AgentPlannerDecision(target_node_id=PLAN_DEFAULT, reason="evaluation: SUCCESS"),
        AgentPlannerDecision(target_node_id=PLAN_DEFAULT, reason="evaluation: SUCCESS"),
    ]
    runner = AgentPlanRunner(client, step_runner=step_runner)

    outcome = runner.run_plan(
        session_id="session-1",
        qid="Q00",
        nodes=[
            AgentPlanNode(node_id="calibrate", task_name="CheckT1", candidate_parameter="t1"),
            AgentPlanNode(node_id="verify", task_name="CheckT2", candidate_parameter="t2"),
        ],
        planner=planner,
    )

    assert outcome.transition == AgentSkillTransition.PASS
    assert outcome.node_path == ("calibrate", "verify")
    assert [d.target_node_id for d in outcome.planner_decisions] == [PLAN_DEFAULT] * 2
    observation = planner.choose_next.call_args_list[0].args[0]
    assert observation.node_tasks == {"calibrate": "CheckT1", "verify": "CheckT2"}
    assert observation.node_visits == {"calibrate": 1, "verify": 0}


def test_plan_planner_escalation_stops_with_its_reason() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _plan_session(max_actions=3)
    step_runner = MagicMock()
    step_runner.run_step.side_effect = [_plan_step("t1", 95.0)]
    planner = MagicMock()
    planner.choose_next.return_value = AgentPlannerDecision(
        target_node_id=PLAN_ESCALATE, reason="evaluation: ANOMALOUS; inspect the figure"
    )
    runner = AgentPlanRunner(client, step_runner=step_runner)

    outcome = runner.run_plan(
        session_id="session-1",
        qid="Q00",
        nodes=[
            AgentPlanNode(node_id="calibrate", task_name="CheckT1", candidate_parameter="t1"),
            AgentPlanNode(node_id="verify", task_name="CheckT2", candidate_parameter="t2"),
        ],
        planner=planner,
    )

    assert outcome.transition == AgentSkillTransition.HUMAN_ESCALATION
    assert "human review: evaluation: ANOMALOUS; inspect the figure" in outcome.reason
    assert step_runner.run_step.call_count == 1
    assert outcome.planner_decisions[0].target_node_id == PLAN_ESCALATE


def test_plan_planner_overrides_apply_to_the_chosen_node_once() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _plan_session(max_actions=4)
    step_runner = MagicMock()
    step_runner.run_step.side_effect = [
        _plan_step("t1", 900.0, transition=AgentSkillTransition.ROLLBACK),
        _plan_step("t1", 95.0),
        _plan_step("t2", 130.0),
    ]
    planner = MagicMock()
    planner.choose_next.side_effect = [
        AgentPlannerDecision(
            target_node_id="calibrate", reason="retry", parameter_overrides={"t1": 42.0}
        ),
        AgentPlannerDecision(target_node_id=PLAN_DEFAULT, reason="pass"),
        AgentPlannerDecision(target_node_id="$complete", reason="done"),
    ]
    runner = AgentPlanRunner(client, step_runner=step_runner)

    outcome = runner.run_plan(
        session_id="session-1",
        qid="Q00",
        nodes=[
            AgentPlanNode(node_id="calibrate", task_name="CheckT1", candidate_parameter="t1"),
            AgentPlanNode(node_id="verify", task_name="CheckT2", candidate_parameter="t2"),
        ],
        max_node_executions=4,
        planner=planner,
    )

    assert outcome.transition == AgentSkillTransition.PASS
    assert outcome.node_path == ("calibrate", "calibrate", "verify")
    overrides = [call.kwargs["parameter_overrides"] for call in step_runner.run_step.call_args_list]
    assert overrides[0] == {}
    assert overrides[1] == {"t1": 42.0}
    # The planner override is consumed; the accepted candidate is carried instead.
    assert overrides[2] == {"t1": 95.0}


def test_plan_planner_overrides_on_a_sentinel_are_rejected() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _plan_session(max_actions=3)
    step_runner = MagicMock()
    step_runner.run_step.side_effect = [_plan_step("t1", 95.0)]
    planner = MagicMock()
    planner.choose_next.return_value = AgentPlannerDecision(
        target_node_id=PLAN_DEFAULT, reason="x", parameter_overrides={"t1": 1.0}
    )
    runner = AgentPlanRunner(client, step_runner=step_runner)

    outcome = runner.run_plan(
        session_id="session-1",
        qid="Q00",
        nodes=[AgentPlanNode(node_id="calibrate", task_name="CheckT1", candidate_parameter="t1")],
        planner=planner,
    )

    assert outcome.transition == AgentSkillTransition.HUMAN_ESCALATION
    assert "attached overrides" in outcome.reason


def test_plan_rejects_reserved_planner_node_ids() -> None:
    client = MagicMock()
    runner = AgentPlanRunner(client, step_runner=MagicMock())
    outcome = runner.run_plan(
        session_id="session-1",
        qid="Q00",
        nodes=[AgentPlanNode(node_id="$escalate", task_name="CheckT1", candidate_parameter="t1")],
    )
    assert outcome.transition == AgentSkillTransition.HUMAN_ESCALATION
    assert "reserved" in outcome.reason


def test_plan_planner_rejects_per_node_commits() -> None:
    client = MagicMock()
    runner = AgentPlanRunner(client, step_runner=MagicMock())
    planner = MagicMock()

    with pytest.raises(ValueError, match="planner-controlled plan cannot use per-node commit"):
        runner.run_plan(
            session_id="session-1",
            qid="Q00",
            nodes=[
                AgentPlanNode(task_name="CheckT1", candidate_parameter="t1", commit_candidate=True)
            ],
            planner=planner,
        )

    client.get_agent_session.assert_not_called()
    planner.choose_next.assert_not_called()


def test_plan_max_node_visits_bounds_a_cycle_before_dispatch() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _plan_session(max_actions=10)
    step_runner = MagicMock()
    step_runner.run_step.return_value = _plan_step("t1", 95.0)
    planner = MagicMock()
    planner.choose_next.return_value = AgentPlannerDecision(
        target_node_id=PLAN_DEFAULT, reason="evaluation: SUCCESS"
    )
    runner = AgentPlanRunner(client, step_runner=step_runner)

    outcome = runner.run_plan(
        session_id="session-1",
        qid="Q00",
        nodes=[
            AgentPlanNode(
                node_id="calibrate",
                task_name="CheckT1",
                candidate_parameter="t1",
                on_pass="calibrate",
            )
        ],
        max_node_executions=10,
        max_node_visits=2,
        planner=planner,
    )

    assert outcome.transition == AgentSkillTransition.HUMAN_ESCALATION
    assert "calibrate (CheckT1) already ran 2 times (limit 2)" in outcome.reason
    assert outcome.node_path == ("calibrate", "calibrate")
    assert step_runner.run_step.call_count == 2
    assert outcome.completed_nodes == 2


def test_plan_max_node_visits_must_be_positive() -> None:
    runner = AgentPlanRunner(MagicMock(), step_runner=MagicMock())
    with pytest.raises(ValueError, match="max_node_visits must be positive"):
        runner.run_plan(
            session_id="session-1",
            qid="Q00",
            nodes=[AgentPlanNode(task_name="CheckT1", candidate_parameter="t1")],
            max_node_visits=0,
        )


def _intervention(**overrides: object) -> AgentInterventionResponse:
    data: dict[str, object] = {
        "intervention_id": "intervention-1",
        "project_id": "project-1",
        "session_id": "session-1",
        "chip_id": "chip-1",
        "reason": "unknown_outcome",
        "summary": "stopped",
        "question": "resume?",
        "status": "open",
        "session_status": "waiting_for_human",
        "page_path": "/agent-sessions/session-1/interventions/intervention-1",
        "notification": {"status": "pending"},
        "created_at": "2026-07-13T00:00:05Z",
        "updated_at": "2026-07-13T00:00:05Z",
    }
    data.update(overrides)
    return AgentInterventionResponse.model_validate(data)


_TWO_NODES = [
    AgentPlanNode(node_id="calibrate", task_name="CheckT1", candidate_parameter="t1"),
    AgentPlanNode(node_id="verify", task_name="CheckT2", candidate_parameter="t2"),
]


def test_plan_escalation_records_an_intervention_with_checkpoint_and_evidence() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _plan_session(max_actions=4)
    client.create_agent_intervention.return_value = _intervention()
    step_runner = MagicMock()
    step_runner.run_step.side_effect = [_plan_step("t1", 95.0)]
    planner = MagicMock()
    planner.choose_next.return_value = AgentPlannerDecision(
        target_node_id=PLAN_ESCALATE,
        reason="CheckT1 evaluation reported LOW_SNR, which has no next action",
        escalation_reason="unknown_outcome",
        evidence={"evaluation_id": "ev-1", "evaluation_run_id": "run-1", "status": "LOW_SNR"},
    )
    planner.export_history.return_value = {"calibrate": [{"status": "LOW_SNR"}]}
    runner = AgentPlanRunner(client, step_runner=step_runner)

    outcome = runner.run_plan(
        session_id="session-1",
        qid="Q00",
        nodes=_TWO_NODES,
        planner=planner,
        max_node_visits=2,
        idempotency_prefix="plan-key",
        record_interventions=True,
        planner_name="evaluation",
    )

    assert outcome.transition == AgentSkillTransition.HUMAN_ESCALATION
    assert outcome.escalation_reason == AgentInterventionReason.UNKNOWN_OUTCOME
    assert outcome.intervention is not None
    assert outcome.intervention.intervention_id == "intervention-1"
    kwargs = client.create_agent_intervention.call_args.kwargs
    assert kwargs["reason"] == "unknown_outcome"
    assert kwargs["idempotency_key"] == "plan-key-i-1-1"
    assert kwargs["node_id"] == "calibrate"
    assert kwargs["task_name"] == "CheckT1"
    attempt = kwargs["attempts"][0]
    assert attempt["evaluation_id"] == "ev-1"
    assert attempt["status"] == "LOW_SNR"
    assert attempt["task_id"] == "task-1"
    checkpoint = kwargs["checkpoint"]
    assert checkpoint["idempotency_prefix"] == "plan-key"
    assert checkpoint["node_path"] == ["calibrate"]
    assert checkpoint["visit_counts"] == {"calibrate": 1}
    assert checkpoint["stopped_node_id"] == "calibrate"
    assert checkpoint["accepted_candidates"] == [
        {"action_id": "action-1", "parameter_name": "t1", "task_id": "task-1"}
    ]
    assert checkpoint["planner"] == "evaluation"
    assert checkpoint["planner_history"] == {"calibrate": [{"status": "LOW_SNR"}]}


def test_plan_reports_a_failed_intervention_record_without_raising() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _plan_session(max_actions=4)
    client.create_agent_intervention.side_effect = QDashTransportError(
        "unreachable", status_code=503
    )
    step_runner = MagicMock()
    step_runner.run_step.side_effect = [
        _plan_step("t1", 900.0, transition=AgentSkillTransition.ROLLBACK)
    ]
    runner = AgentPlanRunner(client, step_runner=step_runner)

    outcome = runner.run_plan(
        session_id="session-1", qid="Q00", nodes=_TWO_NODES, record_interventions=True
    )

    assert outcome.transition == AgentSkillTransition.ROLLBACK
    assert outcome.escalation_reason == AgentInterventionReason.RECOVERY_EXHAUSTED
    assert outcome.intervention is None
    assert outcome.intervention_error is not None
    assert "unreachable" in outcome.intervention_error


def _rejected_checkpoint() -> QDashValidationError:
    return QDashValidationError(
        "422 rejected",
        status_code=422,
        payload={
            "detail": {
                "code": "checkpoint_rejected",
                "message": "The session ran actions that are not part of this plan",
            }
        },
    )


def _stopped_plan(client: MagicMock) -> AgentPlanOutcome:
    client.get_agent_session.return_value = _plan_session(max_actions=4)
    step_runner = MagicMock()
    step_runner.run_step.side_effect = [
        _plan_step("t1", 900.0, transition=AgentSkillTransition.ROLLBACK)
    ]
    runner = AgentPlanRunner(client, step_runner=step_runner)
    return runner.run_plan(
        session_id="session-1",
        qid="Q00",
        nodes=_TWO_NODES,
        idempotency_prefix="plan-key",
        record_interventions=True,
    )


def test_rejected_checkpoint_is_recorded_once_without_a_checkpoint() -> None:
    client = MagicMock()
    client.create_agent_intervention.side_effect = [
        _rejected_checkpoint(),
        _intervention(checkpoint=None),
    ]

    outcome = _stopped_plan(client)

    assert outcome.intervention is not None
    assert outcome.intervention_error is None
    assert outcome.checkpoint_rejection == "The session ran actions that are not part of this plan"
    first, fallback = (call.kwargs for call in client.create_agent_intervention.call_args_list)
    assert first["checkpoint"] is not None
    assert fallback["checkpoint"] is None
    assert fallback["idempotency_key"] == f"{first['idempotency_key']}-nocp"
    assert fallback["summary"].startswith(first["summary"])
    assert fallback["summary"].endswith("this intervention cannot resume the plan.")
    # The server's rejection detail stays local; the durable record gets a fixed note.
    assert "not part of this plan" not in fallback["summary"]
    for name in ("reason", "question", "node_id", "task_name", "qids", "attempts"):
        assert fallback[name] == first[name]


@pytest.mark.parametrize(
    "error",
    [
        QDashValidationError("422 scope", status_code=422, payload={"detail": "outside scope"}),
        QDashValidationError(
            "422 malformed",
            status_code=422,
            payload={"detail": [{"type": "missing", "loc": ["body", "checkpoint"]}]},
        ),
        QDashValidationError(
            "422 other code", status_code=422, payload={"detail": {"code": "something_else"}}
        ),
        QDashValidationError("422 no payload", status_code=422),
        QDashAuthError("401 unauthorized", status_code=401),
        QDashTransportError("403 forbidden", status_code=403),
        QDashTransportError(
            "409 conflict",
            status_code=409,
            payload={"detail": {"code": "checkpoint_rejected", "message": "x"}},
        ),
        QDashTransportError("timed out"),
    ],
)
def test_only_a_checkpoint_rejection_falls_back(error: QDashApiError) -> None:
    client = MagicMock()
    client.create_agent_intervention.side_effect = error

    outcome = _stopped_plan(client)

    assert client.create_agent_intervention.call_count == 1
    assert outcome.intervention is None
    assert outcome.checkpoint_rejection is None
    assert outcome.intervention_error is not None
    assert str(error) in outcome.intervention_error


def test_failed_fallback_reports_the_rejection_and_the_failure() -> None:
    client = MagicMock()
    client.create_agent_intervention.side_effect = [
        _rejected_checkpoint(),
        QDashTransportError("409 already waits", status_code=409),
    ]

    outcome = _stopped_plan(client)

    assert outcome.intervention is None
    assert outcome.checkpoint_rejection is not None
    assert outcome.intervention_error is not None
    assert "not part of this plan" in outcome.intervention_error
    assert "409 already waits" in outcome.intervention_error


def test_plan_known_recovery_stays_in_the_loop_without_an_intervention() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _plan_session(max_actions=4)
    step_runner = MagicMock()
    step_runner.run_step.side_effect = [_plan_step("t1", 95.0), _plan_step("t1", 96.0)]
    planner = MagicMock()
    planner.choose_next.side_effect = [
        AgentPlannerDecision(target_node_id="calibrate", reason="SUBOPTIMAL: retry"),
        AgentPlannerDecision(target_node_id=PLAN_COMPLETE, reason="SUCCESS"),
    ]
    runner = AgentPlanRunner(client, step_runner=step_runner)

    outcome = runner.run_plan(
        session_id="session-1",
        qid="Q00",
        nodes=_TWO_NODES,
        planner=planner,
        max_node_visits=3,
        max_node_executions=4,
        record_interventions=True,
    )

    assert outcome.transition == AgentSkillTransition.PASS
    client.create_agent_intervention.assert_not_called()
    assert outcome.checkpoint is None


def test_resumed_plan_restores_counters_and_never_reuses_an_earlier_key() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _plan_session(max_actions=4)
    client.list_agent_action_candidates.return_value = [_candidate(accepted=True)]
    step_runner = MagicMock()
    step_runner.run_step.side_effect = [_plan_step("t2", 130.0)]
    runner = AgentPlanRunner(client, step_runner=step_runner)
    state = AgentPlanResumeState(
        intervention_id="intervention-1",
        start_node_id="verify",
        node_path=("calibrate",),
        visit_counts={"calibrate": 1},
        accepted_candidates=(
            {"action_id": "action-1", "parameter_name": "t1", "task_id": "task-1"},
        ),
        planner_history={},
    )

    outcome = runner.run_plan(
        session_id="session-1",
        qid="Q00",
        nodes=_TWO_NODES,
        max_node_executions=3,
        idempotency_prefix="plan-key",
        resume=state,
        record_interventions=True,
    )

    assert outcome.transition == AgentSkillTransition.PASS
    assert outcome.node_path == ("calibrate", "verify")
    # The accepted T1 was re-read from QDash and carried into the resumed node.
    client.list_agent_action_candidates.assert_called_once_with("session-1", "action-1")
    call = step_runner.run_step.call_args.kwargs
    assert call["parameter_overrides"] == {"t1": 95.0}
    assert call["action_idempotency_key"] == "plan-key-node-1-action"
    assert outcome.carried_overrides == {"t1": 95.0, "t2": 130.0}
    assert outcome.completed_nodes == 2


def test_resumed_plan_keeps_the_visit_budget_and_the_execution_budget() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _plan_session(max_actions=4)
    client.list_agent_action_candidates.return_value = []
    step_runner = MagicMock()
    runner = AgentPlanRunner(client, step_runner=step_runner)
    state = AgentPlanResumeState(
        intervention_id="intervention-1",
        start_node_id="calibrate",
        node_path=("calibrate", "calibrate"),
        visit_counts={"calibrate": 2},
        accepted_candidates=(),
        planner_history={},
    )

    over_visits = runner.run_plan(
        session_id="session-1",
        qid="Q00",
        nodes=_TWO_NODES,
        max_node_visits=2,
        max_node_executions=4,
        idempotency_prefix="plan-key",
        resume=state,
    )
    over_executions = runner.run_plan(
        session_id="session-1",
        qid="Q00",
        nodes=_TWO_NODES,
        max_node_executions=2,
        idempotency_prefix="plan-key",
        resume=state,
    )

    assert over_visits.transition == AgentSkillTransition.HUMAN_ESCALATION
    assert "already ran 2 times" in over_visits.reason
    assert over_executions.escalation_reason == AgentInterventionReason.RECOVERY_EXHAUSTED
    step_runner.run_step.assert_not_called()


def test_resumed_plan_stops_when_a_carried_candidate_is_no_longer_accepted() -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _plan_session(max_actions=4)
    client.list_agent_action_candidates.return_value = [_candidate(accepted=False)]
    step_runner = MagicMock()
    runner = AgentPlanRunner(client, step_runner=step_runner)
    state = AgentPlanResumeState(
        intervention_id="intervention-1",
        start_node_id="verify",
        node_path=("calibrate",),
        visit_counts={"calibrate": 1},
        accepted_candidates=(
            {"action_id": "action-1", "parameter_name": "t1", "task_id": "task-1"},
        ),
        planner_history={},
    )

    outcome = runner.run_plan(
        session_id="session-1",
        qid="Q00",
        nodes=_TWO_NODES,
        max_node_executions=3,
        idempotency_prefix="plan-key",
        resume=state,
    )

    assert outcome.transition == AgentSkillTransition.HUMAN_ESCALATION
    assert "no longer accepted" in outcome.reason
    step_runner.run_step.assert_not_called()


def test_resume_state_comes_from_the_claimed_checkpoint() -> None:
    claimed = _intervention(
        status="resumed",
        response={"decision": "resume", "resume_node_id": "verify", "guidance": "T1 is fine"},
        checkpoint={
            "qid": "Q00",
            "nodes": [
                {"id": "calibrate", "task_name": "CheckT1", "candidate_parameter": "t1"},
                {"id": "verify", "task_name": "CheckT2", "candidate_parameter": "t2"},
            ],
            "idempotency_prefix": "plan-key",
            "node_path": ["calibrate"],
            "visit_counts": {"calibrate": 1},
            "stopped_node_id": "calibrate",
            "max_node_executions": 3,
            "max_node_visits": 2,
            "planner": "evaluation",
        },
    )

    nodes, state, settings = resume_state_from_intervention(claimed)

    assert [node.node_id for node in nodes] == ["calibrate", "verify"]
    assert state.start_node_id == "verify"
    assert state.guidance == "T1 is fine"
    assert settings["idempotency_prefix"] == "plan-key"
    assert settings["max_node_visits"] == 2
    assert settings["planner"] == "evaluation"
