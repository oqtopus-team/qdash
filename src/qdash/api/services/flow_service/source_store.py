"""Project-scoped storage for flow source files."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import HTTPException
from filelock import FileLock, Timeout

from qdash.api.lib.errors import OperationFailedError
from qdash.common.config.path_resolver import resolve_user_flows_dir, to_container_user_flow_path

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

logger = logging.getLogger("uvicorn.app")

_UNSAFE_PROJECT_CHARS = re.compile(r"[^a-zA-Z0-9_-]")
# How long a save waits for another save of the same flow before giving up.
_LOCK_TIMEOUT_SECONDS = 120.0
_LOCK_POLL_SECONDS = 0.05

# Codes of unexpected flow source failures; the handler logs the cause under an error ID.
FLOW_SOURCE_READ_FAILED = "flow_source_read_failed"
FLOW_SOURCE_WRITE_FAILED = "flow_source_write_failed"
FLOW_SOURCE_DELETE_FAILED = "flow_source_delete_failed"


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
            raise _save_failed() from exc
        logger.info(f"Saved flow code to {path}")

    def create(self, path: Path, code: str) -> None:
        """Write a new flow file, failing when the file already exists.

        The exclusive open is atomic on the filesystem, so a concurrent writer
        in another process cannot slip in between the check and the write.

        Raises:
            FileExistsError: A file with this path already exists; it is left untouched.

        """
        try:
            with path.open("x", encoding="utf-8") as handle:
                handle.write(code)
        except FileExistsError:
            raise
        except Exception as exc:
            raise _save_failed() from exc
        logger.info(f"Created flow code at {path}")

    @asynccontextmanager
    async def lock(self, path: Path) -> AsyncIterator[None]:
        """Hold the save lock of one flow file, across API processes on this host.

        The lock is a sibling ``.<name>.py.lock`` file. It is polled rather than
        awaited in a worker thread, so a cancelled request never leaves a thread
        holding it.
        """
        lock = FileLock(path.with_name(f".{path.name}.lock"), timeout=0)
        deadline = time.monotonic() + _LOCK_TIMEOUT_SECONDS
        while True:
            try:
                lock.acquire(timeout=0)
                break
            except Timeout:
                if time.monotonic() >= deadline:
                    raise HTTPException(
                        status_code=503,
                        detail=f"Flow '{path.stem}' is being saved by another request; try again",
                    ) from None
                await asyncio.sleep(_LOCK_POLL_SECONDS)
        try:
            yield
        finally:
            lock.release()

    def read(self, path: Path) -> str:
        """Read a flow file."""
        try:
            return path.read_text(encoding="utf-8")
        except Exception as exc:
            raise OperationFailedError(
                code=FLOW_SOURCE_READ_FAILED, message="Failed to read the flow file"
            ) from exc

    def delete(self, path: Path) -> None:
        """Delete a flow file."""
        try:
            path.unlink()
        except Exception as exc:
            raise OperationFailedError(
                code=FLOW_SOURCE_DELETE_FAILED, message="Failed to delete the flow file"
            ) from exc
        logger.info(f"Deleted flow file: {path}")

    def exists(self, path: Path) -> bool:
        """Return whether the flow file is still on disk."""
        return path.exists()

    def to_deployment_path(self, path: Path) -> Path:
        """Map an API-local flow path to the deployment-service container path."""
        return to_container_user_flow_path(path, runtime_user_flows_dir=self._base_dir)


def _save_failed() -> OperationFailedError:
    """The error a write or create of a flow file reports for an unexpected failure."""
    return OperationFailedError(
        code=FLOW_SOURCE_WRITE_FAILED, message="Failed to save the flow file"
    )
