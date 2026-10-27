"""GitHubIntegration publishes a session's owned files through ConfigRepository."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from qdash.common.config.qubex_layout import QubexLayout
from qdash.common.infrastructure.config_repository import PublishResult, RepoMode
from qdash.workflow.service.github import ConfigFileType, GitHubIntegration, GitHubPushConfig


class FakeRepository:
    def __init__(self, mode: RepoMode = RepoMode.GITHUB, changed: bool = True) -> None:
        self.mode = mode
        self.changed = changed
        self.calls: list[dict[str, Any]] = []

    def publish_owned(
        self, paths: Any, message: str, *, chip_id: str | None = None
    ) -> PublishResult:
        rels = [str(p) for p in paths]
        self.calls.append({"paths": rels, "message": message, "chip_id": chip_id})
        return PublishResult(
            mode=self.mode, paths=rels, message=message, commit="abc12345", changed=self.changed
        )

    def pull(self) -> str:
        return "abc12345"


def _integration(tmp_path: Path, repository: FakeRepository, system_ids: list[str] | None = None):
    integration = GitHubIntegration.__new__(GitHubIntegration)
    integration.username = "bob"
    integration.chip_id = "chip-1"
    integration.execution_id = "20260819-001"
    integration.project_id = "proj-1"
    integration.system_ids = system_ids
    integration.logger = MagicMock()
    layout = QubexLayout.detect(tmp_path)
    integration._layout = lambda: layout  # type: ignore[method-assign]
    integration._repository = lambda layout=None: repository  # type: ignore[method-assign,assignment,return-value]
    return integration, layout


def _shared_tree(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "chip.yaml").write_text("chip-1: {}\n")
    (tmp_path / "config" / "system.yaml").write_text(
        "chip-1:\n  chip_id: chip-1\n  backend: quel1\nchip-1-quel3:\n  chip_id: chip-1\n  backend: quel3\n"
    )
    for sid in ("chip-1", "chip-1-quel3"):
        (tmp_path / "params" / sid).mkdir(parents=True)
        (tmp_path / "params" / sid / "params.yaml").write_text("a: 1\n")
        (tmp_path / "params" / sid / "drag.yaml").write_text("a: 2\n")


def _config(**overrides: Any) -> GitHubPushConfig:
    with patch("qdash.workflow.service.github.ConfigLoader.load_workflow", return_value={}):
        return GitHubPushConfig(**overrides)


class TestGitHubPushConfigDefaults:
    def test_default_includes_note_and_params(self):
        config = _config()
        assert config.file_types == [ConfigFileType.CALIB_NOTE, ConfigFileType.ALL_PARAMS]
        assert config.params_file_names is None

    def test_params_file_names_loads_from_qdash_settings(self):
        with patch(
            "qdash.workflow.service.github.ConfigLoader.load_workflow",
            return_value={"github": {"params_file_names": ["params.yaml"]}},
        ):
            assert GitHubPushConfig().params_file_names == ["params.yaml"]
            assert GitHubPushConfig(params_file_names=["drag.yaml"]).params_file_names == [
                "drag.yaml"
            ]

    def test_invalid_qdash_settings_params_file_names_raises(self):
        with (
            patch(
                "qdash.workflow.service.github.ConfigLoader.load_workflow",
                return_value={"github": {"params_file_names": "params.yaml"}},
            ),
            pytest.raises(ValueError, match=r"workflow\.github\.params_file_names"),
        ):
            GitHubPushConfig()


class TestPushFiles:
    def test_publishes_note_and_params_of_every_used_system_in_one_commit(self, tmp_path: Path):
        _shared_tree(tmp_path)
        repository = FakeRepository()
        integration, _ = _integration(tmp_path, repository, ["chip-1", "chip-1-quel3"])
        note_repo = MagicMock()
        note_repo.find_latest_master.return_value = SimpleNamespace(note={"actor": "alice"})

        with patch("qdash.repository.MongoCalibrationNoteRepository", return_value=note_repo):
            result = integration.push_files(_config(params_file_names=["params.yaml"]))

        assert result["commit"] == "abc12345"
        assert result["system_ids"] == ["chip-1", "chip-1-quel3"]
        assert result["calib_note"]["files"] == [
            "calibration/chip-1/calib_note.json",
            "calibration/chip-1-quel3/calib_note.json",
        ]
        assert result["all_params"] == {
            "files": ["params.yaml", "params.yaml"],
            "commit": "abc12345",
        }
        assert len(repository.calls) == 1
        call = repository.calls[0]
        assert call["chip_id"] == "chip-1" and "20260819-001" in call["message"]
        assert [Path(p).relative_to(tmp_path).as_posix() for p in call["paths"]] == [
            "calibration/chip-1/calib_note.json",
            "calibration/chip-1-quel3/calib_note.json",
            "params/chip-1/params.yaml",
            "params/chip-1-quel3/params.yaml",
        ]
        assert (
            '"actor": "alice"'
            in (tmp_path / "calibration/chip-1-quel3/calib_note.json").read_text()
        )
        note_repo.find_latest_master.assert_called_with(
            chip_id="chip-1", project_id="proj-1", username=None
        )

    def test_defaults_to_the_chip_default_system(self, tmp_path: Path):
        _shared_tree(tmp_path)
        repository = FakeRepository()
        integration, _ = _integration(tmp_path, repository)

        result = integration.push_files(_config(file_types=[ConfigFileType.ALL_PARAMS]))

        assert result["system_ids"] == ["chip-1"]
        assert result["all_params"]["files"] == ["drag.yaml", "params.yaml"]

    def test_unchanged_files_report_no_commit(self, tmp_path: Path):
        _shared_tree(tmp_path)
        integration, _ = _integration(tmp_path, FakeRepository(changed=False))

        result = integration.push_files(_config(file_types=[ConfigFileType.ALL_PARAMS]))

        assert result["commit"] == "No changes to commit"
        assert result["all_params"]["commit"] == "No changes to commit"

    def test_missing_master_note_is_reported_not_raised(self, tmp_path: Path):
        _shared_tree(tmp_path)
        repository = FakeRepository()
        integration, _ = _integration(tmp_path, repository)
        note_repo = MagicMock()
        note_repo.find_latest_master.return_value = None

        with patch("qdash.repository.MongoCalibrationNoteRepository", return_value=note_repo):
            result = integration.push_files(_config())

        assert "No master calibration note" in result["error"]
        assert "error" in result["calib_note"]
        assert repository.calls == []

    def test_publish_failure_is_reported_per_file_type(self, tmp_path: Path):
        _shared_tree(tmp_path)
        repository = FakeRepository()
        repository.publish_owned = MagicMock(side_effect=RuntimeError("remote down"))  # type: ignore[method-assign]
        integration, _ = _integration(tmp_path, repository)

        result = integration.push_files(_config(file_types=[ConfigFileType.ALL_PARAMS]))

        assert result["error"] == "remote down"
        assert result["all_params"]["error"] == "remote down"


class TestPullConfig:
    def test_pull_failure_returns_none(self, tmp_path: Path):
        repository = FakeRepository()
        repository.pull = MagicMock(side_effect=RuntimeError("dirty"))  # type: ignore[method-assign]
        integration, _ = _integration(tmp_path, repository)

        assert integration.pull_config() is None
        integration.logger.warning.assert_called_once()

    def test_pull_returns_commit(self, tmp_path: Path):
        integration, _ = _integration(tmp_path, FakeRepository())
        assert integration.pull_config() == "abc12345"


class TestSelectParamYamlFiles:
    """Tests for selecting params YAML files for ALL_PARAMS batch pushes."""

    def _make_integration(self):
        integration = GitHubIntegration.__new__(GitHubIntegration)
        integration.logger = MagicMock()
        return integration

    def test_selects_all_yaml_files_by_default(self, tmp_path: Path):
        integration = self._make_integration()
        (tmp_path / "params.yaml").write_text("a: 1")
        (tmp_path / "drag.yaml").write_text("a: 2")
        (tmp_path / "README.md").write_text("ignored")

        files = integration._select_param_yaml_files(tmp_path, None)

        assert [path.name for path in files] == ["drag.yaml", "params.yaml"]

    def test_selects_configured_yaml_files(self, tmp_path: Path):
        integration = self._make_integration()
        (tmp_path / "params.yaml").write_text("a: 1")
        (tmp_path / "drag.yaml").write_text("a: 2")

        files = integration._select_param_yaml_files(tmp_path, ["params.yaml"])

        assert [path.name for path in files] == ["params.yaml"]

    def test_skips_missing_configured_files(self, tmp_path: Path):
        integration = self._make_integration()
        (tmp_path / "params.yaml").write_text("a: 1")

        files = integration._select_param_yaml_files(tmp_path, ["params.yaml", "drag.yaml"])

        assert [path.name for path in files] == ["params.yaml"]
        integration.logger.warning.assert_called_once()

    def test_rejects_subpaths(self, tmp_path: Path):
        integration = self._make_integration()

        with pytest.raises(ValueError, match="Invalid params file name"):
            integration._select_param_yaml_files(tmp_path, ["nested/params.yaml"])

    def test_rejects_non_yaml_files(self, tmp_path: Path):
        integration = self._make_integration()

        with pytest.raises(ValueError, match="Invalid params file name"):
            integration._select_param_yaml_files(tmp_path, ["params.yml"])
