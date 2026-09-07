"""Configuration publication checks remote rejection and preserves live files."""

from unittest.mock import MagicMock

import pytest

from qdash.common.infrastructure.config_github import push_config_files


@pytest.fixture
def repository(monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_USER", "tester")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("CONFIG_REPO_URL", "https://github.com/example/config.git")
    repo = MagicMock()
    repo.__enter__.return_value = repo
    repo.head.commit.hexsha = "abc123"
    repo.index.diff.return_value = [object()]
    repo.remotes.origin.push.return_value = MagicMock()
    monkeypatch.setattr(
        "qdash.common.infrastructure.config_github.Repo.clone_from", lambda *args, **kwargs: repo
    )
    return repo


def test_publishes_files_in_one_commit(repository):
    assert push_config_files({"chip/params/readout.yaml": b"data: {}\n"}, "manual edit") == "abc123"
    repository.index.add.assert_called_once_with(["chip/params/readout.yaml"])
    repository.index.commit.assert_called_once()
    repository.remotes.origin.push.return_value.raise_if_error.assert_called_once()


def test_rejected_push_is_not_success_and_does_not_leak_credentials(repository):
    repository.remotes.origin.push.return_value.raise_if_error.side_effect = RuntimeError(
        "test-token"
    )
    with pytest.raises(RuntimeError, match="synchronization failed") as error:
        push_config_files({"chip/params/readout.yaml": b"data: {}\n"}, "manual edit")
    assert "test-token" not in str(error.value)


def test_unchanged_content_needs_no_new_commit(repository):
    repository.index.diff.return_value = []
    assert push_config_files({"chip/params/readout.yaml": b"data: {}\n"}, "manual edit") == "abc123"
    repository.index.commit.assert_not_called()
    repository.remotes.origin.push.assert_not_called()
