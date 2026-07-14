"""Tests for worker-side agent candidate backend application."""

from unittest.mock import MagicMock

import pytest

from qdash.dbmodel.agent_session import AgentCandidateCommitDocument
from qdash.workflow.engine.backend.fake import FakeBackend
from qdash.workflow.engine.params_updater import get_params_updater
from qdash.workflow.service import agent_candidate_apply_flow


def test_agent_candidate_apply_uses_audited_snapshot_and_verifies(
    init_db, monkeypatch, tmp_path
) -> None:
    """The worker reads the committed value, updates mapped files, and records verification."""
    commit = AgentCandidateCommitDocument(
        commit_id="commit-1",
        session_id="session-1",
        action_id="action-1",
        project_id="project-1",
        idempotency_key="commit-key",
        request_hash="hash",
        execution_id="execution-1",
        task_id="task-1",
        task_name="CheckRabi",
        chip_id="chip-1",
        qid="Q00",
        parameter_name="drive_amplitude",
        value=0.12,
        status="committed",
        after_snapshot={"value": 0.12},
        committed_by="tester",
        state_version_before=1,
        state_version_after=2,
        backend_status="queued",
    )
    commit.insert()

    params_dir = tmp_path / "params"
    params_dir.mkdir()
    params_file = params_dir / "drive_amplitude.yaml"
    params_file.write_text("data:\n  Q00: 0.1\n")
    backend = FakeBackend(
        {
            "task_type": "qubit",
            "qids": ["Q00"],
            "chip_id": "chip-1",
            "project_id": "project-1",
            "params_dir": str(params_dir),
        }
    )
    monkeypatch.setattr(agent_candidate_apply_flow, "get_default_backend", lambda: "fake")
    monkeypatch.setattr(agent_candidate_apply_flow, "create_backend", lambda **kwargs: backend)
    monkeypatch.setattr(
        "qdash.workflow.engine.params_updater.ConfigLoader.load_workflow",
        lambda: {
            "params_updater": {
                "parameter_file_map": {
                    "drive_amplitude": "drive_amplitude.yaml",
                }
            }
        },
    )
    monkeypatch.setattr(agent_candidate_apply_flow, "get_run_logger", MagicMock)

    result = agent_candidate_apply_flow.agent_candidate_apply(
        project_id="project-1",
        session_id="session-1",
        commit_id="commit-1",
        push_to_github=False,
    )

    saved = AgentCandidateCommitDocument.find_one({"commit_id": "commit-1"}).run()
    assert saved is not None
    assert result["verified"] is True
    assert saved.backend_status == "applied"
    assert saved.backend_verified is True
    assert saved.backend_target_files == ["drive_amplitude.yaml"]
    assert "Q00: 0.12" in params_file.read_text()


def test_versioned_apply_fails_before_file_write_without_github_credentials(
    init_db, monkeypatch, tmp_path
) -> None:
    """Versioned production apply performs credential preflight before mutation."""
    AgentCandidateCommitDocument(
        commit_id="commit-2",
        session_id="session-1",
        action_id="action-1",
        project_id="project-1",
        idempotency_key="commit-key-2",
        request_hash="hash",
        execution_id="execution-1",
        task_id="task-1",
        task_name="CheckRabi",
        chip_id="chip-1",
        qid="Q00",
        parameter_name="drive_amplitude",
        value=0.12,
        status="committed",
        after_snapshot={"value": 0.12},
        committed_by="tester",
        state_version_before=1,
        state_version_after=2,
        backend_status="queued",
    ).insert()
    params_dir = tmp_path / "params"
    params_dir.mkdir()
    params_file = params_dir / "drive_amplitude.yaml"
    original = "data:\n  Q00: 0.1\n"
    params_file.write_text(original)
    backend = FakeBackend(
        {
            "task_type": "qubit",
            "qids": ["Q00"],
            "chip_id": "chip-1",
            "project_id": "project-1",
            "params_dir": str(params_dir),
        }
    )
    monkeypatch.setattr(agent_candidate_apply_flow, "get_default_backend", lambda: "fake")
    monkeypatch.setattr(agent_candidate_apply_flow, "create_backend", lambda **kwargs: backend)
    monkeypatch.setattr(agent_candidate_apply_flow, "get_run_logger", MagicMock)
    monkeypatch.setattr(
        "qdash.workflow.service.github.GitHubIntegration.check_credentials",
        lambda: False,
    )

    with pytest.raises(RuntimeError, match="GitHub credentials are required"):
        agent_candidate_apply_flow.agent_candidate_apply(
            project_id="project-1",
            session_id="session-1",
            commit_id="commit-2",
            push_to_github=True,
        )

    saved = AgentCandidateCommitDocument.find_one({"commit_id": "commit-2"}).run()
    assert saved is not None
    assert saved.backend_status == "failed"
    assert saved.backend_verified is False
    assert params_file.read_text() == original


def _insert_commit(commit_id: str, backend_status: str) -> None:
    AgentCandidateCommitDocument(
        commit_id=commit_id,
        session_id="session-1",
        action_id="action-1",
        project_id="project-1",
        idempotency_key=f"{commit_id}-key",
        request_hash="hash",
        execution_id="execution-1",
        task_id="task-1",
        task_name="CheckRabi",
        chip_id="chip-1",
        qid="Q00",
        parameter_name="drive_amplitude",
        value=0.12,
        status="committed",
        after_snapshot={"value": 0.12},
        committed_by="tester",
        state_version_before=1,
        state_version_after=2,
        backend_status=backend_status,
    ).insert()


def test_agent_candidate_apply_aborts_when_transition_guard_is_lost(init_db, monkeypatch) -> None:
    _insert_commit("commit-stale", "applied")
    create_backend = MagicMock()
    monkeypatch.setattr(agent_candidate_apply_flow, "create_backend", create_backend)
    monkeypatch.setattr(agent_candidate_apply_flow, "get_run_logger", MagicMock)

    with pytest.raises(RuntimeError, match="no longer queued"):
        agent_candidate_apply_flow.agent_candidate_apply(
            project_id="project-1",
            session_id="session-1",
            commit_id="commit-stale",
            push_to_github=False,
        )

    create_backend.assert_not_called()
    saved = AgentCandidateCommitDocument.find_one({"commit_id": "commit-stale"}).run()
    assert saved is not None
    assert saved.backend_status == "applied"


def test_agent_candidate_apply_restores_yaml_when_verification_fails(
    init_db, monkeypatch, tmp_path
) -> None:
    _insert_commit("commit-rollback", "queued")
    params_dir = tmp_path / "params"
    params_dir.mkdir()
    params_file = params_dir / "drive_amplitude.yaml"
    original = "data:\n  Q00: 0.1\n"
    params_file.write_text(original)
    backend = FakeBackend(
        {
            "task_type": "qubit",
            "qids": ["Q00"],
            "chip_id": "chip-1",
            "project_id": "project-1",
            "params_dir": str(params_dir),
        }
    )
    monkeypatch.setattr(
        "qdash.workflow.engine.params_updater.ConfigLoader.load_workflow",
        lambda: {
            "params_updater": {"parameter_file_map": {"drive_amplitude": "drive_amplitude.yaml"}}
        },
    )
    updater = get_params_updater(backend, "chip-1")
    assert updater is not None
    wrapped_updater = MagicMock(wraps=updater)
    wrapped_updater.verify.return_value = set()
    monkeypatch.setattr(agent_candidate_apply_flow, "get_default_backend", lambda: "fake")
    monkeypatch.setattr(agent_candidate_apply_flow, "create_backend", lambda **kwargs: backend)
    monkeypatch.setattr(
        agent_candidate_apply_flow,
        "get_params_updater",
        lambda _backend, _chip_id: wrapped_updater,
    )
    monkeypatch.setattr(agent_candidate_apply_flow, "get_run_logger", MagicMock)

    with pytest.raises(RuntimeError, match="did not cover all target files"):
        agent_candidate_apply_flow.agent_candidate_apply(
            project_id="project-1",
            session_id="session-1",
            commit_id="commit-rollback",
            push_to_github=False,
        )

    saved = AgentCandidateCommitDocument.find_one({"commit_id": "commit-rollback"}).run()
    assert saved is not None
    assert saved.backend_status == "failed"
    assert saved.backend_verified is False
    assert params_file.read_text() == original
    wrapped_updater.restore.assert_called_once()
