"""Prefect task wrapper over :meth:`ConfigRepository.publish_owned`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from prefect import get_run_logger, task

from qdash.common.infrastructure.config_repository import get_config_repository

if TYPE_CHECKING:
    from pathlib import Path


@task(task_run_name="Push GitHub")
def push_github(
    paths: list[str | Path],
    commit_message: str = "Update calibration files",
    chip_id: str | None = None,
) -> str:
    """Publish System-owned files (params and calib_note) from the configuration root.

    Returns the short commit SHA, or ``"No changes to commit"`` when the files already
    match the repository.
    """
    logger = get_run_logger()
    repository = get_config_repository()
    result = repository.publish_owned(paths, commit_message, chip_id=chip_id)
    if not result.changed:
        logger.info("No changes to commit")
        return "No changes to commit"
    logger.info("Published %d file(s): %s", len(result.paths), result.commit)
    return result.commit or ""
