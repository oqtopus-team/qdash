"""Synchronize locally applied manual calibration values to the config repository."""

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
from qdash.common.infrastructure.config_github import (
    config_github_credentials_available,
    push_config_files,
)

if TYPE_CHECKING:
    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

logger = logging.getLogger(__name__)


class CalibrationGitHubService:
    """Push only mapped files; a remote failure never undoes local calibration."""

    def sync(self, result: TaskResultHistoryDocument) -> CalibrationGitHubSync:
        sync = CalibrationGitHubSync()
        try:
            settings: dict[str, Any] = ConfigLoader.load_workflow().get("github", {})
            if settings.get("enabled", True) is not True or get_default_backend() != "qubex":
                return sync
            if not config_github_credentials_available():
                return sync
            names = sorted(resolve_param_yaml_file_names(result.output_parameters))
            if not names:
                return sync
            if not re.fullmatch(r"[a-zA-Z0-9_-]+", result.chip_id):
                raise ValueError("Invalid chip ID")
            directory = QUBEX_CONFIG_BASE / result.chip_id / "params"
            # Serialize publication and hold the same file locks as YAML writers.
            # Retries deliberately publish current accepted files, never old values.
            with FileLock(directory / ".github-sync.lock", timeout=10), ExitStack() as stack:
                for name in names:
                    stack.enter_context(FileLock(directory / (name + ".lock"), timeout=10))
                files = {
                    f"{result.chip_id}/params/{name}": (directory / name).read_bytes()
                    for name in names
                }
                commit = push_config_files(
                    files,
                    f"Sync calibration params after {result.task_id}",
                    branch=settings.get("branch", "main"),
                )
            sync = CalibrationGitHubSync(status="synced", commit=commit)
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
