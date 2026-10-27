"""Status and synchronization of the Qubex configuration repository."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import HTTPException

from qdash.api.schemas.config_repository import (
    ConfigRepositoryStatus,
    ConfigRepositorySyncResult,
)
from qdash.common.config.path_resolver import resolve_config_base_path
from qdash.common.config.qubex_layout import QubexLayout
from qdash.common.infrastructure.config_repository import (
    ConfigRepository,
    ConfigRepositoryError,
    DirtySharedFiles,
    RepoMode,
    get_config_repository,
)

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class ConfigRepositoryService:
    """Expose the repository mode, layout and sync to the Config page."""

    def __init__(self, config_base_path: Path | None = None) -> None:
        self._base_path = config_base_path

    def _repository(self, actor: str) -> ConfigRepository:
        root = self._base_path or resolve_config_base_path()
        return get_config_repository(QubexLayout.detect(root), actor=actor)

    def status(self) -> ConfigRepositoryStatus:
        status = self._repository("config-ui").status()
        return ConfigRepositoryStatus(
            mode=status.mode.value,
            layout=status.layout.value if status.layout else None,
            layout_version=status.layout_version,
            manifest_present=status.manifest_present,
            schemas_status=status.schemas_status,
            root=status.root,
            is_git_repo=status.is_git_repo,
            branch=status.branch,
            head=status.head,
            head_message=status.head_message,
            changed_paths=status.changed_paths,
            untracked_paths=status.untracked_paths,
            unpushed_commits=status.unpushed_commits,
            has_remote_updates=status.has_remote_updates,
            review_required=status.review_required,
        )

    def sync(self, *, actor: str, force: bool = False) -> ConfigRepositorySyncResult:
        """Publish unpublished owned files, then pull. 409 when shared files are edited."""
        repository = self._repository(actor)
        if repository.mode is not RepoMode.GITHUB:
            return ConfigRepositorySyncResult(
                mode=repository.mode.value,
                commit=repository.status().head,
                message=f"Repository mode is {repository.mode.value}; nothing to synchronize",
            )
        try:
            result = repository.sync(force=force)
        except DirtySharedFiles as exc:
            raise HTTPException(
                status_code=409,
                detail=f"{exc!s}. Open a pull request with them or discard them with force.",
            ) from exc
        except ConfigRepositoryError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        published = len(result.published)
        message = (
            f"Published {published} file(s) and pulled {result.commit}"
            if published
            else f"Pulled {result.commit}"
        )
        return ConfigRepositorySyncResult(**result.to_dict(), message=message)
