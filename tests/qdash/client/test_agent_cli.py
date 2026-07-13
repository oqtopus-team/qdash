"""Tests for the qdash-agent user entry point."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from qdash.client.services import agent_cli
from qdash.client.services.agent_runner import (
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
            '{"shots":1024}',
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
    assert step_kwargs["parameter_overrides"] == {"shots": 1024.0}
    assert step_kwargs["reconfigure_before_task"] is False
    assert step_kwargs["commit_candidate"] is True
    assert step_kwargs["apply_backend"] is True
    assert step_kwargs["push_to_github"] is False
    client.close.assert_called_once()
