"""Project-scoped storage for flow source files."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from fastapi import HTTPException

from qdash.common.config.path_resolver import resolve_user_flows_dir, to_container_user_flow_path

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger("uvicorn.app")

_UNSAFE_PROJECT_CHARS = re.compile(r"[^a-zA-Z0-9_-]")


class FlowSourceStore:
    """Read and write flow files under the user flow tree."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or resolve_user_flows_dir()

    @property
    def base_dir(self) -> Path:
        """Root directory holding one folder per project."""
        return self._base_dir

    def path_for(self, project_id: str, name: str) -> Path:
        """Return the source path for a flow, creating its project directory."""
        project_dir = self._base_dir / _UNSAFE_PROJECT_CHARS.sub("_", project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        return project_dir / f"{name}.py"

    def write(self, path: Path, code: str) -> None:
        """Write source code to a flow file."""
        try:
            path.write_text(code, encoding="utf-8")
        except Exception as exc:
            logger.error(f"Failed to write flow file: {exc}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save flow file: {exc}",
            ) from exc
        logger.info(f"Saved flow code to {path}")

    def read(self, path: Path) -> str:
        """Read a flow file."""
        try:
            return path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.error(f"Failed to read flow file: {exc}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to read flow file: {exc}",
            ) from exc

    def delete(self, path: Path) -> None:
        """Delete a flow file."""
        try:
            path.unlink()
        except Exception as exc:
            logger.error(f"Failed to delete flow file: {exc}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete flow file: {exc}",
            ) from exc
        logger.info(f"Deleted flow file: {path}")

    def exists(self, path: Path) -> bool:
        """Return whether the flow file is still on disk."""
        return path.exists()

    def to_deployment_path(self, path: Path) -> Path:
        """Map an API-local flow path to the deployment-service container path."""
        return to_container_user_flow_path(path, runtime_user_flows_dir=self._base_dir)
