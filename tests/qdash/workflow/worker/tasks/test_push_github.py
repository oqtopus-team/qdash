"""Tests for push_github module, focusing on _sync_local_repo."""

import logging
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

    def test_params_file_names_defaults_to_none(self):
        """Default params_file_names keeps the historical all-yaml behavior."""
        from qdash.workflow.service.github import GitHubPushConfig

        with patch("qdash.workflow.service.github.ConfigLoader.load_workflow", return_value={}):
            config = GitHubPushConfig()
        assert config.params_file_names is None

    def test_params_file_names_loads_from_qdash_settings(self):
        """Default params_file_names can be managed in QDash settings."""
        from qdash.workflow.service.github import GitHubPushConfig

        with patch(
            "qdash.workflow.service.github.ConfigLoader.load_workflow",
            return_value={"github": {"params_file_names": ["params.yaml"]}},
        ):
            config = GitHubPushConfig()

        assert config.params_file_names == ["params.yaml"]

    def test_explicit_params_file_names_overrides_qdash_settings(self):
        """An explicit config value should override the QDash settings default."""
        from qdash.workflow.service.github import GitHubPushConfig

        with patch(
            "qdash.workflow.service.github.ConfigLoader.load_workflow",
            return_value={"github": {"params_file_names": ["params.yaml"]}},
        ):
            config = GitHubPushConfig(params_file_names=["drag.yaml"])

        assert config.params_file_names == ["drag.yaml"]

    def test_invalid_qdash_settings_params_file_names_raises(self):
        """Invalid QDash settings should fail during GitHubPushConfig creation."""
        from qdash.workflow.service.github import GitHubPushConfig

        with (
            patch(
                "qdash.workflow.service.github.ConfigLoader.load_workflow",
                return_value={"github": {"params_file_names": "params.yaml"}},
            ),
            pytest.raises(ValueError, match=r"workflow\.github\.params_file_names"),
        ):
            GitHubPushConfig()


class TestGitHubIntegrationPushFilesSync:
    """Tests for deferred local repo sync during grouped GitHub pushes."""

    def _make_integration(self):
        from qdash.workflow.service.github import GitHubIntegration

        integration = GitHubIntegration.__new__(GitHubIntegration)
        integration.logger = MagicMock()
        integration._push_calib_note = MagicMock(return_value="abc12345")
        integration._push_all_params = MagicMock(
            return_value={"commit": "def67890", "files": ["params.yaml"]}
        )
        integration._push_props = MagicMock()
        integration._push_params_file = MagicMock()
        return integration

    def _make_config(self):
        from qdash.workflow.service.github import ConfigFileType, GitHubPushConfig

        with patch("qdash.workflow.service.github.ConfigLoader.load_workflow", return_value={}):
            return GitHubPushConfig(
                file_types=[ConfigFileType.CALIB_NOTE, ConfigFileType.ALL_PARAMS],
                branch="develop",
            )

    def test_syncs_local_repo_once_after_all_pushes_succeed(self):
        """Grouped pushes should not reset local files between calib_note and params."""
        integration = self._make_integration()
        config = self._make_config()

        with patch("qdash.workflow.worker.tasks.push_github._sync_local_repo") as sync_local:
            result = integration.push_files(config)

        assert result == {
            "calib_note": "abc12345",
            "all_params": {"commit": "def67890", "files": ["params.yaml"]},
        }
        sync_local.assert_called_once_with("develop", integration.logger)

    def test_does_not_sync_local_repo_when_later_push_fails(self):
        """Do not discard local params changes when a grouped push reports an error."""
        integration = self._make_integration()
        integration._push_all_params.return_value = {"error": "push failed"}
        config = self._make_config()

        with patch("qdash.workflow.worker.tasks.push_github._sync_local_repo") as sync_local:
            result = integration.push_files(config)

        assert result["calib_note"] == "abc12345"
        assert result["all_params"] == {"error": "push failed"}
        sync_local.assert_not_called()

    def test_does_not_sync_local_repo_when_nothing_changed(self):
        """No-op grouped pushes do not need to reset the local repository."""
        integration = self._make_integration()
        integration._push_calib_note.return_value = "No changes to commit"
        integration._push_all_params.return_value = {
            "commit": "No changes to commit",
            "files": ["params.yaml"],
        }
        config = self._make_config()

        with patch("qdash.workflow.worker.tasks.push_github._sync_local_repo") as sync_local:
            integration.push_files(config)

        sync_local.assert_not_called()


class TestSelectParamYamlFiles:
    """Tests for selecting params YAML files for ALL_PARAMS batch pushes."""

    def _make_integration(self):
        from qdash.workflow.service.github import GitHubIntegration

        integration = GitHubIntegration.__new__(GitHubIntegration)
        integration.logger = MagicMock()
        return integration

    def test_selects_all_yaml_files_by_default(self, tmp_path: Path):
        """Should preserve ALL_PARAMS behavior when no allowlist is configured."""
        integration = self._make_integration()
        (tmp_path / "params.yaml").write_text("a: 1")
        (tmp_path / "drag.yaml").write_text("a: 2")
        (tmp_path / "README.md").write_text("ignored")

        files = integration._select_param_yaml_files(tmp_path, None)

        assert [path.name for path in files] == ["drag.yaml", "params.yaml"]

    def test_selects_configured_yaml_files(self, tmp_path: Path):
        """Should only include configured params file names."""
        integration = self._make_integration()
        (tmp_path / "params.yaml").write_text("a: 1")
        (tmp_path / "drag.yaml").write_text("a: 2")

        files = integration._select_param_yaml_files(tmp_path, ["params.yaml"])

        assert [path.name for path in files] == ["params.yaml"]

    def test_skips_missing_configured_files(self, tmp_path: Path):
        """Missing allowlisted files should not fail the whole batch."""
        integration = self._make_integration()
        (tmp_path / "params.yaml").write_text("a: 1")

        files = integration._select_param_yaml_files(tmp_path, ["params.yaml", "drag.yaml"])

        assert [path.name for path in files] == ["params.yaml"]
        integration.logger.warning.assert_called_once()

    def test_rejects_subpaths(self, tmp_path: Path):
        """Only simple file names are allowed in the params allowlist."""
        integration = self._make_integration()

        with pytest.raises(ValueError, match="Invalid params file name"):
            integration._select_param_yaml_files(tmp_path, ["nested/params.yaml"])

    def test_rejects_non_yaml_files(self, tmp_path: Path):
        """Only .yaml files are valid params batch targets."""
        integration = self._make_integration()

        with pytest.raises(ValueError, match="Invalid params file name"):
            integration._select_param_yaml_files(tmp_path, ["params.yml"])
