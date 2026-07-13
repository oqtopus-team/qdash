"""Tests for the user-side agent calibration Skill runner."""

from __future__ import annotations

from unittest.mock import MagicMock

from qdash.client.services.agent_runner import (
    AgentCalibrationRunner,
    AgentSkillTransition,
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
        push_to_github=True,
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
    runner = AgentCalibrationRunner(client)

    outcome = runner.run_step(
        session_id="session-1",
        task_name="CheckT1",
        qid="Q00",
        source_execution_id="source-1",
        candidate_parameter="t1",
    )

    assert outcome.transition == AgentSkillTransition.HUMAN_ESCALATION
    client.execute_agent_action.assert_not_called()
