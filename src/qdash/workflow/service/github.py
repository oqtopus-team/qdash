"""Configuration repository integration for calibration sessions.

A session pulls the configuration root before it starts and publishes the files it
owns when it finishes: the calibration note and the parameter YAML files of every
System the session used. Both go through
:class:`~qdash.common.infrastructure.config_repository.ConfigRepository`, so the
behaviour follows the repository mode (direct push, local commit, or change log only).
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any

from prefect import get_run_logger
from pydantic import BaseModel, Field

from qdash.common.config.loader import ConfigLoader
from qdash.common.config.qubex_layout import QubexLayout
from qdash.common.config.system_catalog import default_system_id
from qdash.common.infrastructure.config_repository import (
    ConfigRepository,
    GitHubSettings,
    get_config_repository,
)


class ConfigFileType(Enum):
    """Owned files a session can publish.

    Attributes:
        CALIB_NOTE: ``calibration/<system_id>/calib_note.json`` (the project's master note)
        ALL_PARAMS: ``params/<system_id>/*.yaml``, narrowed by ``params_file_names``
    """

    CALIB_NOTE = "calib_note"
    ALL_PARAMS = "all_params"


def _load_default_params_file_names() -> list[str] | None:
    """Load default params batch allowlist from QDash settings."""
    workflow_settings = ConfigLoader.load_workflow()
    if not isinstance(workflow_settings, dict):
        return None
    github_settings = workflow_settings.get("github", {})
    if not isinstance(github_settings, dict):
        return None
    value = github_settings.get("params_file_names")
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("workflow.github.params_file_names must be a list of strings")
    return value


class GitHubPushConfig(BaseModel):
    """What a session publishes when it finishes.

    Attributes:
        enabled: Whether to publish on finish_calibration()
        file_types: File types to publish (default: [CALIB_NOTE, ALL_PARAMS])
        params_file_names: Optional allowlist for ALL_PARAMS, such as
            ["params.yaml", "drag.yaml"]. Defaults to workflow.github.params_file_names
            from the QDash workflow config; when neither is set every *.yaml is published.
        commit_message: Custom commit message (default: auto-generated)
        branch: Target branch (default: "main")
    """

    enabled: bool = False
    file_types: list[ConfigFileType] = Field(
        default_factory=lambda: [ConfigFileType.CALIB_NOTE, ConfigFileType.ALL_PARAMS]
    )
    params_file_names: list[str] | None = Field(default_factory=_load_default_params_file_names)
    commit_message: str | None = None
    branch: str = "main"

    model_config = {"frozen": False}


class GitHubIntegration:
    """Pull before a session and publish the session's owned files after it.

    Attributes:
        username: Username for the calibration session
        chip_id: Target chip ID
        execution_id: Unique execution identifier
        project_id: Project owning the shared calibration state
        system_ids: Systems the session used; their params and calibration directories
            are the files it may publish. Defaults to the chip's default System.
    """

    def __init__(
        self,
        username: str,
        chip_id: str,
        execution_id: str,
        project_id: str | None = None,
        system_ids: list[str] | None = None,
    ) -> None:
        self.username = username
        self.chip_id = chip_id
        self.execution_id = execution_id
        self.project_id = project_id
        self.system_ids = system_ids
        self.logger = get_run_logger()

    @staticmethod
    def check_credentials() -> bool:
        """True when ``CONFIG_REPO_URL``, ``GITHUB_USER`` and ``GITHUB_TOKEN`` are set."""
        return GitHubSettings.from_env().credentials_available

    def _layout(self) -> QubexLayout:
        return QubexLayout.detect()

    def _repository(self, layout: QubexLayout | None = None) -> ConfigRepository:
        return get_config_repository(layout or self._layout(), actor=self.username)

    def _resolved_system_ids(self, layout: QubexLayout) -> list[str]:
        if self.system_ids:
            return list(dict.fromkeys(self.system_ids))
        return [default_system_id(layout, self.chip_id)]

    def _chip_system_ids(self, layout: QubexLayout, used: list[str]) -> list[str]:
        """Every System of the chip, the used ones first; the used ones alone on error."""
        try:
            from qdash.common.config.system_catalog import SystemCatalog

            all_ids = SystemCatalog(layout, self.chip_id).system_ids()
        except Exception as exc:  # unreadable tree: publish what the session used
            self.logger.debug(f"Could not list the chip's Systems: {exc}")
            return used
        return list(dict.fromkeys([*used, *all_ids]))

    def pull_config(self, target_dir: str | None = None) -> str | None:
        """Bring the configuration root up to date; returns the head commit or None.

        A refused pull (shared files edited locally, remote unreachable) is logged and
        the session continues with the local files.
        """
        try:
            layout = QubexLayout.detect(Path(target_dir)) if target_dir else self._layout()
            commit_id = self._repository(layout).pull()
            self.logger.info(f"Pulled config repository: {commit_id}")
            return str(commit_id) if commit_id else None
        except Exception as e:
            self.logger.warning(f"Failed to pull the config repository: {e}")
            return None

    def push_files(self, push_config: GitHubPushConfig) -> dict[str, Any]:
        """Publish the session's owned files in one commit.

        Returns a dictionary with the commit and the files per file type, or an
        ``error`` entry when publishing failed. Files are collected for every System
        in :attr:`system_ids`.
        """
        layout = self._layout()
        system_ids = self._resolved_system_ids(layout)
        files: list[Path] = []
        results: dict[str, Any] = {"system_ids": system_ids}
        try:
            for file_type in push_config.file_types:
                if file_type == ConfigFileType.CALIB_NOTE:
                    notes = [self._write_master_note(layout, sid) for sid in system_ids]
                    files.extend(notes)
                    results["calib_note"] = {"files": [str(layout.repo_relpath(p)) for p in notes]}
                elif file_type == ConfigFileType.ALL_PARAMS:
                    # Physics values are projected into every System of the chip, so
                    # the params of unused Systems changed too.
                    params = self._collect_params(
                        layout,
                        self._chip_system_ids(layout, system_ids),
                        push_config.params_file_names,
                    )
                    files.extend(params)
                    results["all_params"] = {"files": [p.name for p in params]}
        except Exception as e:
            self.logger.error(f"Failed to collect files to publish: {e}")
            results["error"] = str(e)
            for key in ("calib_note", "all_params"):
                results.setdefault(key, {})["error"] = str(e)
            return results
        if not files:
            results["status"] = "No files to push"
            return results
        message = (
            push_config.commit_message
            or f"Update calibration files from execution {self.execution_id}"
        )
        try:
            publish = self._repository(layout).publish_owned(files, message, chip_id=self.chip_id)
        except Exception as e:
            self.logger.error(f"Failed to publish calibration files: {e}")
            results["error"] = str(e)
            for key in ("calib_note", "all_params"):
                if key in results:
                    results[key]["error"] = str(e)
            return results
        results["mode"] = publish.mode.value
        results["commit"] = publish.commit if publish.changed else "No changes to commit"
        if publish.pr_url:
            results["pr_url"] = publish.pr_url
        for key in ("calib_note", "all_params"):
            if key in results:
                results[key]["commit"] = results["commit"]
        self.logger.info(f"Published {len(files)} file(s): {results['commit']}")
        return results

    def _write_master_note(self, layout: QubexLayout, system_id: str) -> Path:
        """Write the project's master calibration note into a System's calibration dir."""
        from qdash.repository import MongoCalibrationNoteRepository

        repo = MongoCalibrationNoteRepository()
        latest_note = repo.find_latest_master(
            chip_id=self.chip_id,
            project_id=self.project_id,
            username=None if self.project_id else self.username,
        )
        if latest_note is None:
            scope = f"project {self.project_id}" if self.project_id else f"user {self.username}"
            raise FileNotFoundError(f"No master calibration note found in MongoDB for {scope}")
        path = layout.calib_note_path(system_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(latest_note.note, f, indent=4, ensure_ascii=False, sort_keys=True)
        self.logger.info(f"Wrote master note to {path}")
        return path

    def _collect_params(
        self, layout: QubexLayout, system_ids: list[str], params_file_names: list[str] | None
    ) -> list[Path]:
        files: list[Path] = []
        for system_id in system_ids:
            params_dir = layout.params_dir(system_id)
            if not params_dir.exists():
                self.logger.warning(f"Params directory not found: {params_dir}")
                continue
            files.extend(self._select_param_yaml_files(params_dir, params_file_names))
        return files

    def _select_param_yaml_files(
        self,
        params_dir: Path,
        params_file_names: list[str] | None,
    ) -> list[Path]:
        """Select params YAML files to publish, optionally constrained by filename."""
        if params_file_names is None:
            return sorted(params_dir.glob("*.yaml"))

        files: list[Path] = []
        seen: set[str] = set()
        for file_name in params_file_names:
            normalized = file_name.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            path = Path(normalized)
            if path.name != normalized or path.suffix != ".yaml":
                raise ValueError(f"Invalid params file name: {file_name!r}")
            yaml_file = params_dir / normalized
            if yaml_file.exists():
                files.append(yaml_file)
            else:
                self.logger.warning(f"Configured params file not found, skipping: {yaml_file}")
        return files
