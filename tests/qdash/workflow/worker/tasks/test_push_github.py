"""Tests for push_github module, focusing on _sync_local_repo."""

import logging
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError


class TestSyncLocalRepo:
    """Tests for _sync_local_repo function."""

    def _import_sync(self):
        from qdash.workflow.worker.tasks.push_github import _sync_local_repo

        return _sync_local_repo

    def test_skips_when_no_git_dir(self, tmp_path: Path):
        """Should return immediately if .git directory does not exist."""
        _sync_local_repo = self._import_sync()
        logger = MagicMock(spec=logging.Logger)

        with patch("qdash.workflow.worker.tasks.push_github.QUBEX_CONFIG_BASE", tmp_path):
            _sync_local_repo("main", logger)

        logger.info.assert_not_called()
        logger.warning.assert_not_called()
        logger.error.assert_not_called()

    def test_calls_fetch_and_reset(self, tmp_path: Path):
        """Should fetch and reset --hard when .git exists."""
        _sync_local_repo = self._import_sync()
        logger = MagicMock(spec=logging.Logger)

        # Create a bare .git directory to pass the exists() check
        (tmp_path / ".git").mkdir()

        mock_repo = MagicMock(spec=Repo)
        with (
            patch("qdash.workflow.worker.tasks.push_github.QUBEX_CONFIG_BASE", tmp_path),
            patch("qdash.workflow.worker.tasks.push_github.Repo", return_value=mock_repo),
        ):
            _sync_local_repo("main", logger)

        mock_repo.remotes.origin.fetch.assert_called_once()
        mock_repo.git.reset.assert_called_once_with("--hard", "origin/main")
        logger.info.assert_called_once()

    def test_uses_correct_branch(self, tmp_path: Path):
        """Should reset to the specified branch, not always 'main'."""
        _sync_local_repo = self._import_sync()
        logger = MagicMock(spec=logging.Logger)
        (tmp_path / ".git").mkdir()

        mock_repo = MagicMock(spec=Repo)
        with (
            patch("qdash.workflow.worker.tasks.push_github.QUBEX_CONFIG_BASE", tmp_path),
            patch("qdash.workflow.worker.tasks.push_github.Repo", return_value=mock_repo),
        ):
            _sync_local_repo("develop", logger)

        mock_repo.git.reset.assert_called_once_with("--hard", "origin/develop")

    def test_handles_git_command_error(self, tmp_path: Path):
        """Should log warning on GitCommandError without raising."""
        _sync_local_repo = self._import_sync()
        logger = MagicMock(spec=logging.Logger)
        (tmp_path / ".git").mkdir()

        mock_repo = MagicMock(spec=Repo)
        mock_repo.remotes.origin.fetch.side_effect = GitCommandError("fetch", "network error")

        with (
            patch("qdash.workflow.worker.tasks.push_github.QUBEX_CONFIG_BASE", tmp_path),
            patch("qdash.workflow.worker.tasks.push_github.Repo", return_value=mock_repo),
        ):
            _sync_local_repo("main", logger)

        logger.warning.assert_called_once()
        assert "Failed to sync" in logger.warning.call_args[0][0]

    def test_handles_invalid_git_repository_error(self, tmp_path: Path):
        """Should log warning on InvalidGitRepositoryError without raising."""
        _sync_local_repo = self._import_sync()
        logger = MagicMock(spec=logging.Logger)
        (tmp_path / ".git").mkdir()

        with (
            patch("qdash.workflow.worker.tasks.push_github.QUBEX_CONFIG_BASE", tmp_path),
            patch(
                "qdash.workflow.worker.tasks.push_github.Repo",
                side_effect=InvalidGitRepositoryError("bad repo"),
            ),
        ):
            _sync_local_repo("main", logger)

        logger.warning.assert_called_once()

    def test_handles_unexpected_error(self, tmp_path: Path):
        """Should log error on unexpected exceptions without raising."""
        _sync_local_repo = self._import_sync()
        logger = MagicMock(spec=logging.Logger)
        (tmp_path / ".git").mkdir()

        with (
            patch("qdash.workflow.worker.tasks.push_github.QUBEX_CONFIG_BASE", tmp_path),
            patch(
                "qdash.workflow.worker.tasks.push_github.Repo",
                side_effect=OSError("disk error"),
            ),
        ):
            _sync_local_repo("main", logger)

        logger.error.assert_called_once()
        assert "Unexpected error" in logger.error.call_args[0][0]


class TestGitHubPushConfigDefaults:
    """Tests for GitHubPushConfig default file_types."""

    def test_default_includes_all_params(self):
        """Default file_types should include both CALIB_NOTE and ALL_PARAMS."""
        from qdash.workflow.service.github import ConfigFileType, GitHubPushConfig

        config = GitHubPushConfig()
        assert ConfigFileType.CALIB_NOTE in config.file_types
        assert ConfigFileType.ALL_PARAMS in config.file_types

    def test_explicit_file_types_override_default(self):
        """Explicit file_types should override the default."""
        from qdash.workflow.service.github import ConfigFileType, GitHubPushConfig

        config = GitHubPushConfig(file_types=[ConfigFileType.PROPS])
        assert config.file_types == [ConfigFileType.PROPS]
