"""Publish locally applied manual calibration values to the configuration repository."""

from __future__ import annotations

import logging
import re
from contextlib import ExitStack
from typing import TYPE_CHECKING, Any

from filelock import FileLock

from qdash.api.schemas.calibration import CalibrationGitHubSync
from qdash.common.config.backend import get_default_backend
from qdash.common.config.loader import ConfigLoader
from qdash.common.config.params_updater import resolve_param_yaml_file_names
from qdash.common.config.paths import QUBEX_CONFIG_BASE
from qdash.common.config.qubex_layout import QubexLayout
from qdash.common.config.system_catalog import default_system_id
from qdash.common.infrastructure.config_repository import RepoMode, get_config_repository

if TYPE_CHECKING:
    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

logger = logging.getLogger(__name__)


class CalibrationGitHubService:
    """Publish only mapped files; a remote failure never undoes local calibration."""

    def sync(self, result: TaskResultHistoryDocument) -> CalibrationGitHubSync:
        sync = CalibrationGitHubSync()
        try:
            settings: dict[str, Any] = ConfigLoader.load_workflow().get("github", {})
            if settings.get("enabled", True) is not True or get_default_backend() != "qubex":
                return sync
            names = sorted(resolve_param_yaml_file_names(result.output_parameters))
            if not names:
                return sync
            if not re.fullmatch(r"[a-zA-Z0-9_-]+", result.chip_id):
                raise ValueError("Invalid chip ID")
            layout = QubexLayout.detect(QUBEX_CONFIG_BASE)
            repository = get_config_repository(layout, actor=result.username)
            if repository.mode is RepoMode.PLAIN:
                return sync
            directory = layout.params_dir(default_system_id(layout, result.chip_id))
            # Serialize publication and hold the same file locks as YAML writers.
            # Retries deliberately publish current accepted files, never old values.
            with FileLock(directory / ".github-sync.lock", timeout=10), ExitStack() as stack:
                for name in names:
                    stack.enter_context(FileLock(directory / (name + ".lock"), timeout=10))
                published = repository.publish_owned(
                    [directory / name for name in names],
                    f"Sync calibration params after {result.task_id}",
                    chip_id=result.chip_id,
                )
            sync = CalibrationGitHubSync(status="synced", commit=published.commit)
        except Exception:
            sync = CalibrationGitHubSync(
                status="failed",
                message="Calibration values are applied. GitHub synchronization failed; retry synchronization.",
            )
            logger.warning("GitHub synchronization failed for manual edit %s", result.task_id)
        try:
            result.get_motor_collection().update_one(
                {"_id": result.id}, {"$set": {"note.github_sync": sync.model_dump()}}
            )
        except Exception:
            logger.warning("Could not record GitHub sync status for manual edit %s", result.task_id)
        return sync
