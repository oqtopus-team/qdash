"""Prefect task wrapper over :meth:`ConfigRepository.pull`."""

from __future__ import annotations

from pathlib import Path

from prefect import get_run_logger, task

from qdash.common.config.paths import QUBEX_CONFIG_BASE
from qdash.common.config.qubex_layout import QubexLayout
from qdash.common.infrastructure.config_repository import get_config_repository


@task(task_run_name="Pull GitHub")
def pull_github(target_dir: str | Path = QUBEX_CONFIG_BASE) -> str:
    """Bring the configuration root up to date with its repository.

    Returns the short commit SHA of the new head, or an empty string when the root is
    not synchronized with a remote (``local-git`` and ``plain`` modes).
    """
    logger = get_run_logger()
    repository = get_config_repository(QubexLayout.detect(Path(target_dir)))
    commit = repository.pull()
    logger.info(
        "Configuration root %s (%s mode) at commit %s", target_dir, repository.mode.value, commit
    )
    return commit or ""
