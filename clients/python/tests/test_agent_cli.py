"""Tests for the qdash-agent user entry point."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from qdash.client.services import agent_cli
from qdash.client.services.agent_runner import (
    AgentPlanOutcome,
    AgentSkillTransition,
    AgentStepOutcome,
)


def test_start_session_uses_profile_and_bounded_policy(
    monkeypatch,
    capsys,
) -> None:
    client = MagicMock()
    session = MagicMock()
    session.model_dump.return_value = {
        "session_id": "session-1",
        "state_version": 0,
    }
    client.create_agent_session.return_value = session
    monkeypatch.setattr(
        agent_cli.QDashClient,
        "from_profile",
        lambda profile: client,
    )

    exit_code = agent_cli.run(
        [
            "--profile",
            "lab",
            "start-session",
            "--chip-id",
            "chip-1",
            "--qid",
            "Q00",
            "--task",
            "CheckT1",
            "--allowed-overrides",
            '{"t1":{"minimum":1,"maximum":500}}',
            "--skill-name",
            "qubit-characterize",
            "--model-name",
            "local-model",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["session_id"] == "session-1"
    client.create_agent_session.assert_called_once_with(
        chip_id="chip-1",
        policy={
            "qids": ["Q00"],
            "allowed_tasks": ["CheckT1"],
            "allowed_overrides": {"t1": {"minimum": 1, "maximum": 500}},
            "quality_gates": {},
            "allow_reconfigure": False,
            "max_actions": 100,
            "autonomy": "confirm_each",
            "max_rounds_per_target": 3,
        },
        expires_in_seconds=21_600,
        skill_name="qubit-characterize",
        skill_version="",
        skill_hash="",
        model_name="local-model",
    )
    client.close.assert_called_once()


def test_start_session_can_load_connection_from_environment(
    monkeypatch,
    capsys,
) -> None:
    client = MagicMock()
    session = MagicMock()
    session.model_dump.return_value = {"session_id": "session-1"}
    client.create_agent_session.return_value = session
    monkeypatch.setattr(agent_cli.QDashClient, "from_env", lambda: client)

    exit_code = agent_cli.run(
        [
            "--from-env",
            "start-session",
            "--chip-id",
            "chip-1",
            "--qid",
            "Q00",
            "--task",
            "CheckT1",
            "--allowed-overrides",
            '{"t1":{"minimum":1,"maximum":500}}',
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["session_id"] == "session-1"
    client.create_agent_session.assert_called_once()
    client.close.assert_called_once()


def test_run_step_prints_typed_transition(
    monkeypatch,
    capsys,
) -> None:
    client = MagicMock()
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        agent_cli.QDashClient,
        "from_profile",
        lambda profile: client,
    )

    class FakeRunner:
        def __init__(self, runner_client, **kwargs):
            captured["client"] = runner_client
            captured["runner_kwargs"] = kwargs

        def run_step(self, **kwargs):
            captured["step_kwargs"] = kwargs
            return AgentStepOutcome(
                transition=AgentSkillTransition.PASS,
                reason="Candidate passed and was committed",
                session_id="session-1",
                action_id="action-1",
                operation_id="operation-1",
            )

    monkeypatch.setattr(agent_cli, "AgentCalibrationRunner", FakeRunner)

    exit_code = agent_cli.run(
        [
            "--profile",
            "lab",
            "run-step",
            "--session-id",
            "session-1",
            "--task",
            "CheckT1",
            "--qid",
            "Q00",
            "--source-execution-id",
            "source-1",
            "--candidate-parameter",
            "t1",
            "--parameter-overrides",
            '{"t1":95}',
            "--commit",
            "--apply-backend",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["transition"] == "pass"
    assert payload["operation_id"] == "operation-1"
    step_kwargs = captured["step_kwargs"]
    assert isinstance(step_kwargs, dict)
    assert step_kwargs["parameter_overrides"] == {"t1": 95.0}
    assert step_kwargs["reconfigure_before_task"] is False
    assert step_kwargs["commit_candidate"] is True
    assert step_kwargs["apply_backend"] is True
    assert step_kwargs["push_to_github"] is False
    client.close.assert_called_once()


def test_run_plan_parses_plan_and_prints_audit_outcome(
    monkeypatch,
    capsys,
) -> None:
    client = MagicMock()
    captured: dict[str, object] = {}
    monkeypatch.setattr(agent_cli.QDashClient, "from_profile", lambda profile: client)

    class FakePlanRunner:
        def __init__(self, runner_client, **kwargs):
            captured["client"] = runner_client
            captured["runner_kwargs"] = kwargs

        def run_plan(self, **kwargs):
            captured["plan_kwargs"] = kwargs
            return AgentPlanOutcome(
                transition=AgentSkillTransition.PASS,
                reason="Plan completed 2 nodes",
                session_id="session-1",
                qid="Q00",
                source_execution_id="source-1",
                completed_nodes=2,
                attempts=2,
                outcomes=(),
                carried_overrides={"t1": 95.0, "t2": 130.0},
                node_path=("calibrate", "verify"),
            )

    monkeypatch.setattr(agent_cli, "AgentPlanRunner", FakePlanRunner)

    exit_code = agent_cli.run(
        [
            "--profile",
            "lab",
            "run-plan",
            "--session-id",
            "session-1",
            "--qid",
            "Q00",
            "--source-execution-id",
            "source-1",
            "--plan",
            json.dumps(
                [
                    {
                        "id": "calibrate",
                        "task_name": "CheckT1",
                        "candidate_parameter": "t1",
                        "on_rollback": "verify",
                    },
                    {
                        "id": "verify",
                        "task_name": "CheckT2",
                        "candidate_parameter": "t2",
                        "on_pass": "$complete",
                    },
                ]
            ),
            "--idempotency-prefix",
            "plan-key",
            "--max-node-executions",
            "4",
            "--commit-on-success",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["transition"] == "pass"
    assert payload["completed_nodes"] == 2
    assert payload["node_path"] == ["calibrate", "verify"]
    assert payload["candidate_set_commit"] is None
    assert payload["planner_decisions"] == []
    plan_kwargs = captured["plan_kwargs"]
    assert isinstance(plan_kwargs, dict)
    assert plan_kwargs["idempotency_prefix"] == "plan-key"
    assert plan_kwargs["max_node_executions"] == 4
    assert plan_kwargs["commit_on_success"] is True
    nodes = plan_kwargs["nodes"]
    assert isinstance(nodes, list)
    assert [node.task_name for node in nodes] == ["CheckT1", "CheckT2"]
    assert nodes[0].node_id == "calibrate"
    assert nodes[0].on_rollback == "verify"
    assert nodes[1].on_pass == "$complete"  # noqa: S105 - transition target
    assert nodes[0].commit_candidate is False
    assert nodes[1].apply_backend is False
    client.close.assert_called_once()


def _auto_session(autonomy: str):
    from qdash.client.services.models import AgentSessionResponse

    return AgentSessionResponse.model_validate(
        {
            "session_id": "session-1",
            "project_id": "project-1",
            "chip_id": "chip-1",
            "created_by": "tester",
            "policy": {
                "qids": ["Q00"],
                "allowed_tasks": ["CheckRabi", "CheckChevron"],
                "allowed_actions": ["run_task"],
                "allowed_overrides": {"control_amplitude": {"minimum": 0.01, "maximum": 0.05}},
                "max_actions": 10,
                "autonomy": autonomy,
                "max_rounds_per_target": 2,
            },
            "skill_name": "qdash-calibration-agent",
            "skill_version": "1",
            "skill_hash": "sha256:test",
            "model_name": "local-model",
            "status": "active",
            "state_version": 0,
            "action_count": 0,
            "created_at": "2026-07-13T00:00:00Z",
            "updated_at": "2026-07-13T00:00:00Z",
            "expires_at": "2026-07-14T00:00:00Z",
        }
    )


_PLAN = json.dumps(
    [
        {"id": "rabi", "task_name": "CheckRabi", "candidate_parameter": "control_amplitude"},
        {"id": "chevron", "task_name": "CheckChevron", "candidate_parameter": "control_amplitude"},
    ]
)


def test_run_plan_evaluation_planner_needs_an_auto_session(monkeypatch, capsys) -> None:
    client = MagicMock()
    client.get_agent_session.return_value = _auto_session("confirm_each")
    monkeypatch.setattr(agent_cli.QDashClient, "from_profile", lambda profile: client)
    runner = MagicMock()
    monkeypatch.setattr(agent_cli, "AgentPlanRunner", runner)

    exit_code = agent_cli.run(
        [
            "--profile",
            "lab",
            "run-plan",
            "--session-id",
            "session-1",
            "--qid",
            "Q00",
            "--plan",
            _PLAN,
            "--planner",
            "evaluation",
        ]
    )

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["transition"] == "human_escalation"
    assert "autonomy='auto'" in payload["reason"]
    runner.return_value.run_plan.assert_not_called()


def test_run_plan_evaluation_planner_is_built_from_the_session(monkeypatch, capsys) -> None:
    from qdash.client.services.evaluation_planner import EvaluationPlanner

    client = MagicMock()
    client.get_agent_session.return_value = _auto_session("auto")
    monkeypatch.setattr(agent_cli.QDashClient, "from_profile", lambda profile: client)
    captured: dict[str, object] = {}

    class FakePlanRunner:
        def __init__(self, runner_client, **kwargs):
            pass

        def run_plan(self, **kwargs):
            captured.update(kwargs)
            return AgentPlanOutcome(
                transition=AgentSkillTransition.PASS,
                reason="Plan completed 1 nodes",
                session_id="session-1",
                qid="Q00",
                source_execution_id=None,
                completed_nodes=1,
                attempts=1,
                outcomes=(),
                node_path=("rabi",),
            )

    monkeypatch.setattr(agent_cli, "AgentPlanRunner", FakePlanRunner)

    exit_code = agent_cli.run(
        [
            "--profile",
            "lab",
            "run-plan",
            "--session-id",
            "session-1",
            "--qid",
            "Q00",
            "--plan",
            _PLAN,
            "--planner",
            "evaluation",
            "--evaluation-timeout-seconds",
            "42",
        ]
    )

    assert exit_code == 0
    planner = captured["planner"]
    assert isinstance(planner, EvaluationPlanner)
    assert planner.max_rounds_per_target == 2
    assert captured["max_node_executions"] == 4  # 2 nodes x 2 rounds
    assert captured["max_node_visits"] == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["evaluations"] == []


def test_run_plan_evaluation_planner_refuses_per_node_commits(monkeypatch, capsys) -> None:
    client = MagicMock()
    monkeypatch.setattr(agent_cli.QDashClient, "from_profile", lambda profile: client)
    runner = MagicMock()
    monkeypatch.setattr(agent_cli, "AgentPlanRunner", runner)
    plan = json.dumps(
        [
            {
                "id": "rabi",
                "task_name": "CheckRabi",
                "candidate_parameter": "control_amplitude",
                "commit_candidate": True,
            }
        ]
    )

    with pytest.raises(SystemExit) as exc_info:
        agent_cli.run(
            [
                "--profile",
                "lab",
                "run-plan",
                "--session-id",
                "session-1",
                "--qid",
                "Q00",
                "--plan",
                plan,
                "--planner",
                "evaluation",
            ]
        )

    assert exc_info.value.code == 2
    assert "--commit-on-success" in capsys.readouterr().err
    client.get_agent_session.assert_not_called()
    runner.return_value.run_plan.assert_not_called()
