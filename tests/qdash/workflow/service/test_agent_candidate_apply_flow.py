"""Tests for worker-side agent candidate backend application."""

from unittest.mock import MagicMock

import pytest

from qdash.dbmodel.agent_session import AgentCandidateCommitDocument
from qdash.workflow.engine.backend.fake import FakeBackend
from qdash.workflow.engine.params_updater import get_params_updater
from qdash.workflow.service import agent_candidate_apply_flow


@pytest.mark.parametrize("missing", [False, True])
def test_agent_candidate_apply_uses_audited_snapshot_and_verifies(
    init_db, monkeypatch, tmp_path, missing
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
        backend_dispatch_token="token-1",
    )
    commit.insert()

    params_dir = tmp_path / "params"
    params_dir.mkdir()
    params_file = params_dir / "drive_amplitude.yaml"
    if not missing:
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
        backend_dispatch_token="token-1",
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
        backend_dispatch_token="token-1",
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
    wrapped_updater.rollback.assert_called_once()
    wrapped_updater.restore.assert_not_called()


# ---------------------------------------------------------------- session-granted applies

SNAPSHOT = {"value": 0.12, "task_id": "task-1"}


def _granted_apply_setup(monkeypatch, tmp_path, *, stored: dict[str, object] | None = None):
    """A queued session-granted apply whose value the qubit stores, and its params file."""
    from qdash.datamodel.system_info import SystemInfoModel
    from qdash.dbmodel.qubit import QubitDocument

    QubitDocument(
        project_id="project-1",
        username="tester",
        qid="Q00",
        chip_id="chip-1",
        data={"drive_amplitude": dict(stored if stored is not None else SNAPSHOT)},
        system_info=SystemInfoModel(),
    ).insert()
    AgentCandidateCommitDocument(
        commit_id="commit-granted",
        session_id="session-1",
        action_id="action-1",
        project_id="project-1",
        idempotency_key="granted-key",
        request_hash="hash",
        execution_id="execution-1",
        task_id="task-1",
        task_name="CheckRabi",
        chip_id="chip-1",
        qid="Q00",
        parameter_name="drive_amplitude",
        value=0.12,
        status="committed",
        after_snapshot=dict(SNAPSHOT),
        committed_by="tester",
        state_version_before=1,
        state_version_after=2,
        backend_status="queued",
        backend_dispatch_token="token-granted",
        backend_authority="session_policy",
    ).insert()
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
    monkeypatch.setattr(
        "qdash.workflow.engine.params_updater.ConfigLoader.load_workflow",
        lambda: {
            "params_updater": {"parameter_file_map": {"drive_amplitude": "drive_amplitude.yaml"}}
        },
    )
    monkeypatch.setattr(agent_candidate_apply_flow, "get_default_backend", lambda: "fake")
    monkeypatch.setattr(agent_candidate_apply_flow, "create_backend", lambda **kwargs: backend)
    monkeypatch.setattr(agent_candidate_apply_flow, "get_run_logger", MagicMock)
    return backend, params_file


def _run_granted() -> dict[str, object]:
    return agent_candidate_apply_flow.agent_candidate_apply(
        project_id="project-1",
        session_id="session-1",
        commit_id="commit-granted",
        push_to_github=False,
    )


def _lock_count() -> int:
    from qdash.dbmodel.agent_session import AgentBackendApplyLockDocument

    return AgentBackendApplyLockDocument.find({}).count()


def _saved_granted() -> AgentCandidateCommitDocument:
    saved = AgentCandidateCommitDocument.find_one({"commit_id": "commit-granted"}).run()
    assert saved is not None
    return saved


def test_a_granted_apply_writes_the_stored_value_and_releases_the_lease(
    init_db, monkeypatch, tmp_path
) -> None:
    _, params_file = _granted_apply_setup(monkeypatch, tmp_path)
    assert _run_granted()["verified"] is True
    assert _saved_granted().backend_status == "applied"
    assert "Q00: 0.12" in params_file.read_text()
    assert _lock_count() == 0


def test_a_granted_apply_of_a_value_no_longer_stored_writes_nothing(
    init_db, monkeypatch, tmp_path
) -> None:
    _, params_file = _granted_apply_setup(
        monkeypatch, tmp_path, stored={"value": 0.2, "task_id": "manual"}
    )
    with pytest.raises(RuntimeError, match="before the write"):
        _run_granted()
    saved = _saved_granted()
    assert saved.backend_status == "failed"
    assert params_file.read_text() == "data:\n  Q00: 0.1\n"
    assert _lock_count() == 0


def _interleave_after_apply(monkeypatch, backend, write_between) -> None:
    """Run ``write_between`` right after the apply's YAML write lands."""
    updater = get_params_updater(backend, "chip-1")
    assert updater is not None
    original_apply = updater.apply

    def apply_then_someone_writes(qid, parameters, record):
        changed = original_apply(qid, parameters, record)
        write_between()
        return changed

    updater.apply = apply_then_someone_writes  # type: ignore[method-assign]
    monkeypatch.setattr(
        agent_candidate_apply_flow, "get_params_updater", lambda _backend, _chip: updater
    )


def _ordinary_yaml_write(backend, qid: str, value: float) -> None:
    """An ordinary workflow task's params write, through its own updater instance."""
    updater = get_params_updater(backend, "chip-1")
    assert updater is not None
    updater.update(qid, {"drive_amplitude": {"value": value}})


def _save_stored_value(value: float) -> None:
    from qdash.dbmodel.qubit import QubitDocument

    QubitDocument.update_calib_data(
        username="bob",
        qid="Q00",
        chip_id="chip-1",
        output_parameters={"drive_amplitude": {"value": value}},
        project_id="project-1",
    )


def test_a_qubit_write_during_a_granted_apply_restores_the_files(
    init_db, monkeypatch, tmp_path
) -> None:
    backend, params_file = _granted_apply_setup(monkeypatch, tmp_path)
    # Another writer saves the parameter while the files are being written.
    _interleave_after_apply(monkeypatch, backend, lambda: _save_stored_value(0.3))
    with pytest.raises(RuntimeError, match="after the write"):
        _run_granted()
    assert _saved_granted().backend_status == "failed"
    assert params_file.read_text() == "data:\n  Q00: 0.1\n"
    assert _lock_count() == 0


def test_rollback_keeps_an_unrelated_workflow_write_to_the_same_file(
    init_db, monkeypatch, tmp_path
) -> None:
    from ruamel.yaml import YAML

    backend, params_file = _granted_apply_setup(monkeypatch, tmp_path)

    def unrelated_writer_then_freshness_failure() -> None:
        _ordinary_yaml_write(backend, "Q01", 0.25)
        _save_stored_value(0.3)

    _interleave_after_apply(monkeypatch, backend, unrelated_writer_then_freshness_failure)
    with pytest.raises(RuntimeError, match="after the write"):
        _run_granted()
    saved = _saved_granted()
    assert saved.backend_status == "failed"
    assert "left later changes in place" not in saved.backend_error
    assert dict(YAML().load(params_file.read_text())["data"]) == {"Q00": 0.1, "Q01": 0.25}
    assert _lock_count() == 0


def test_rollback_leaves_a_later_write_of_the_same_field_and_reports_it(
    init_db, monkeypatch, tmp_path
) -> None:
    from ruamel.yaml import YAML

    backend, params_file = _granted_apply_setup(monkeypatch, tmp_path)

    def same_field_writer() -> None:
        _ordinary_yaml_write(backend, "Q00", 0.3)
        _save_stored_value(0.3)

    _interleave_after_apply(monkeypatch, backend, same_field_writer)
    with pytest.raises(ValueError, match="verification failed"):
        _run_granted()
    saved = _saved_granted()
    assert saved.backend_status == "failed"
    assert "backend rollback left later changes in place" in saved.backend_error
    assert "drive_amplitude.yaml:Q00 changed after the apply" in saved.backend_error
    assert dict(YAML().load(params_file.read_text())["data"]) == {"Q00": 0.3}
    assert _lock_count() == 0


def test_rollback_after_verification_failure_keeps_an_unrelated_write(
    init_db, monkeypatch, tmp_path
) -> None:
    from ruamel.yaml import YAML

    backend, params_file = _granted_apply_setup(monkeypatch, tmp_path)
    params_file.unlink()
    updater = get_params_updater(backend, "chip-1")
    assert updater is not None

    def verify_fails_after_unrelated_write(qid, parameters):
        _ordinary_yaml_write(backend, "Q01", 0.25)
        return set()

    updater.verify = verify_fails_after_unrelated_write  # type: ignore[method-assign]
    monkeypatch.setattr(
        agent_candidate_apply_flow, "get_params_updater", lambda _backend, _chip: updater
    )
    with pytest.raises(RuntimeError, match="did not cover all target files"):
        _run_granted()
    # The apply created the file; rollback removes only its key and keeps the other value.
    assert dict(YAML().load(params_file.read_text())["data"]) == {"Q01": 0.25}
    assert _saved_granted().backend_status == "failed"
    assert _lock_count() == 0


def test_rollback_of_a_created_file_with_no_other_writer_removes_it(
    init_db, monkeypatch, tmp_path
) -> None:
    backend, params_file = _granted_apply_setup(monkeypatch, tmp_path)
    params_file.unlink()
    _interleave_after_apply(monkeypatch, backend, lambda: _save_stored_value(0.3))
    with pytest.raises(RuntimeError, match="after the write"):
        _run_granted()
    assert not params_file.exists()
    assert _lock_count() == 0


def test_a_granted_apply_waits_for_another_apply_holding_the_chip(
    init_db, monkeypatch, tmp_path
) -> None:
    from qdash.dbmodel.agent_parameter_state import acquire_backend_apply_lock

    _, params_file = _granted_apply_setup(monkeypatch, tmp_path)
    _insert_commit("commit-other", "applying")
    assert (
        acquire_backend_apply_lock(
            project_id="project-1",
            chip_id="chip-1",
            session_id="session-1",
            commit_id="commit-other",
            token="token-1",
        )
        is None
    )
    with pytest.raises(RuntimeError, match="commit-other on chip chip-1 has not settled"):
        _run_granted()
    assert _saved_granted().backend_status == "failed"
    assert params_file.read_text() == "data:\n  Q00: 0.1\n"
    assert _lock_count() == 1
