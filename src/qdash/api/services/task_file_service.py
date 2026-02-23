"""Service for task file operations."""

from __future__ import annotations

import ast
import contextlib
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from fastapi import HTTPException
from qdash.api.lib.backend_config import (
    get_task_category,
    get_tasks,
    load_backend_config,
)
from qdash.api.lib.config_loader import ConfigLoader
from qdash.api.lib.file_utils import validate_relative_path
from qdash.api.schemas.task_file import (
    BackendConfigResponse,
    FileNodeType,
    ListTaskFileBackendsResponse,
    ListTaskInfoResponse,
    SaveTaskFileRequest,
    TaskFileBackend,
    TaskFileSettings,
    TaskFileTreeNode,
    TaskInfo,
)
from qdash.common.paths import CALIBTASKS_DIR

logger = logging.getLogger(__name__)


class TaskFileService:
    """Service for task file browsing, editing, and metadata extraction."""

    def __init__(self, calibtasks_base_path: Path | None = None) -> None:
        """Initialize the service.

        Parameters
        ----------
        calibtasks_base_path : Path | None
            Base path for calibration task files. Defaults to CALIBTASKS_DIR.

        """
        self._base_path = calibtasks_base_path or CALIBTASKS_DIR
        self._task_cache: dict[str, tuple[float, list[TaskInfo]]] = {}

    def get_settings(self) -> TaskFileSettings:
        """Get task file settings from config/settings.yaml.

        Returns
        -------
        TaskFileSettings
            Task file settings including default backend.

        """
        try:
            settings = ConfigLoader.load_settings()
            ui_settings = settings.get("ui", {})
            task_files_settings = ui_settings.get("task_files", {})
            return TaskFileSettings(
                default_backend=task_files_settings.get("default_backend"),
                default_view_mode=task_files_settings.get("default_view_mode"),
                sort_order=task_files_settings.get("sort_order"),
            )
        except Exception as e:
            logger.warning(f"Failed to load task file settings: {e}")

        return TaskFileSettings()

    def list_backends(self) -> ListTaskFileBackendsResponse:
        """List all available backend directories.

        Returns
        -------
        ListTaskFileBackendsResponse
            List of backend names and paths.

        Raises
        ------
        HTTPException
            404 if calibtasks directory not found.

        """
        if not self._base_path.exists():
            raise HTTPException(
                status_code=404, detail=f"Caltasks directory not found: {self._base_path}"
            )

        backends = []
        try:
            for item in sorted(self._base_path.iterdir()):
                if item.name.startswith(".") or item.name == "__pycache__" or not item.is_dir():
                    continue
                backends.append(TaskFileBackend(name=item.name, path=item.name))
        except PermissionError:
            logger.warning(f"Permission denied accessing directory: {self._base_path}")

        return ListTaskFileBackendsResponse(backends=backends)

    def get_file_tree(self, backend: str) -> list[TaskFileTreeNode]:
        """Get file tree structure for a specific backend directory.

        Parameters
        ----------
        backend : str
            Backend name (e.g., "qubex", "fake").

        Returns
        -------
        list[TaskFileTreeNode]
            File tree structure for the backend.

        """
        backend_path = self._base_path / backend

        if not backend_path.exists():
            raise HTTPException(status_code=404, detail=f"Backend directory not found: {backend}")

        if not backend_path.is_dir():
            raise HTTPException(status_code=400, detail=f"Not a directory: {backend}")

        return self._build_file_tree(backend_path, backend_path)

    def get_file_content(self, path: str) -> dict[str, Any]:
        """Get task file content for viewing/editing.

        Parameters
        ----------
        path : str
            Relative path from base path.

        Returns
        -------
        dict[str, Any]
            File content and metadata.

        """
        file_path = validate_relative_path(path, self._base_path)

        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {path}")

        if not file_path.is_file():
            raise HTTPException(status_code=400, detail=f"Not a file: {path}")

        if file_path.suffix != ".py":
            raise HTTPException(status_code=400, detail="Only Python files are allowed")

        try:
            content = file_path.read_text(encoding="utf-8")
            return {
                "content": content,
                "path": path,
                "name": file_path.name,
                "size": file_path.stat().st_size,
                "modified": datetime.fromtimestamp(
                    file_path.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
            }
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="File is not a text file")
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            raise HTTPException(status_code=500, detail=f"Error reading file: {e!s}")

    def save_file_content(self, request: SaveTaskFileRequest) -> dict[str, str]:
        """Save task file content.

        Parameters
        ----------
        request : SaveTaskFileRequest
            Save file request with path and content.

        Returns
        -------
        dict[str, str]
            Success message.

        """
        file_path = validate_relative_path(request.path, self._base_path)

        if not request.path.endswith(".py"):
            raise HTTPException(status_code=400, detail="Only Python files are allowed")

        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {request.path}")

        try:
            file_path.write_text(request.content, encoding="utf-8")
            logger.info(f"Task file saved successfully: {file_path}")
            return {
                "message": "File saved successfully",
                "path": request.path,
            }
        except Exception as e:
            logger.error(f"Error saving file {file_path}: {e}")
            raise HTTPException(status_code=500, detail=f"Error saving file: {e!s}")

    def get_backend_config(self) -> BackendConfigResponse:
        """Get backend configuration from backend.yaml.

        Returns
        -------
        BackendConfigResponse
            Backend configuration.

        """
        try:
            config = load_backend_config()
            return BackendConfigResponse(
                default_backend=config.default_backend,
                backends={
                    name: {"description": b.description, "tasks": b.tasks}
                    for name, b in config.backends.items()
                },
                categories=config.categories,
            )
        except Exception as e:
            logger.warning(f"Failed to load backend config: {e}")
            return BackendConfigResponse()

    def list_task_info(
        self,
        backend: str,
        sort_order: str | None = None,
        enabled_only: bool = False,
    ) -> ListTaskInfoResponse:
        """List all task definitions found in a backend directory.

        Parameters
        ----------
        backend : str
            Backend name (e.g., "qubex", "fake").
        sort_order : str | None
            Sort order for tasks.
        enabled_only : bool
            If True, only return tasks enabled in backend.yaml.

        Returns
        -------
        ListTaskInfoResponse
            List of task information.

        """
        backend_path = self._base_path / backend

        if not backend_path.exists():
            raise HTTPException(status_code=404, detail=f"Backend directory not found: {backend}")

        if not backend_path.is_dir():
            raise HTTPException(status_code=400, detail=f"Not a directory: {backend}")

        # Check cache
        cache_key = f"{backend}:{sort_order or 'default'}:{enabled_only}"
        current_mtime = self._get_directory_mtime_sum(backend_path)
        cached = self._task_cache.get(cache_key)

        if cached is not None:
            cached_mtime, cached_tasks = cached
            if cached_mtime == current_mtime:
                logger.debug(f"Using cached task list for backend: {backend}")
                return ListTaskInfoResponse(tasks=cached_tasks)

        logger.debug(f"Parsing task files for backend: {backend}")
        tasks = self._collect_tasks_from_directory(backend_path, backend_path)

        available_tasks = set(get_tasks(backend))

        enriched_tasks = []
        for task in tasks:
            task.category = get_task_category(task.name)
            task.enabled = task.name in available_tasks
            enriched_tasks.append(task)

        if enabled_only:
            enriched_tasks = [t for t in enriched_tasks if t.enabled]

        if sort_order == "name_only":
            enriched_tasks.sort(key=lambda t: t.name)
        elif sort_order == "file_path":
            enriched_tasks.sort(key=lambda t: (t.file_path, t.name))
        elif sort_order == "category":
            enriched_tasks.sort(key=lambda t: (t.category or "zzz", t.name))
        else:
            enriched_tasks.sort(key=lambda t: (t.task_type or "", t.name))

        self._task_cache[cache_key] = (current_mtime, enriched_tasks)

        return ListTaskInfoResponse(tasks=enriched_tasks)

    # --- Private helpers ---

    def _build_file_tree(self, directory: Path, base_path: Path) -> list[TaskFileTreeNode]:
        """Build task file tree structure recursively."""
        nodes = []

        try:
            items = sorted(directory.iterdir(), key=lambda x: (not x.is_dir(), x.name))

            for item in items:
                if item.name.startswith(".") or item.name == "__pycache__":
                    continue

                relative_path = str(item.relative_to(base_path))

                if item.is_dir():
                    children = self._build_file_tree(item, base_path)
                    nodes.append(
                        TaskFileTreeNode(
                            name=item.name,
                            path=relative_path,
                            type=FileNodeType.DIRECTORY,
                            children=children if children else None,
                        )
                    )
                elif item.suffix == ".py":
                    nodes.append(
                        TaskFileTreeNode(
                            name=item.name,
                            path=relative_path,
                            type=FileNodeType.FILE,
                            children=None,
                        )
                    )

        except PermissionError:
            logger.warning(f"Permission denied accessing directory: {directory}")

        return nodes

    def _extract_task_info_from_file(self, file_path: Path, relative_path: str) -> list[TaskInfo]:
        """Extract task information from a Python file using AST parsing."""
        tasks: list[TaskInfo] = []

        if not self._is_valid_python_file(file_path):
            return tasks

        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            logger.warning(f"Failed to read file: {relative_path}")
            return tasks

        try:
            tree = ast.parse(content)
        except SyntaxError:
            logger.warning(f"Invalid Python syntax in file: {relative_path}")
            return tasks

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            name_value = None
            task_type_value = None
            docstring = ast.get_docstring(node)

            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    if item.target.id == "name":
                        name_value = self._extract_string_value(item.value)
                    elif item.target.id == "task_type":
                        task_type_value = self._extract_string_value(item.value)
                elif isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            if target.id == "name":
                                name_value = self._extract_string_value(item.value)
                            elif target.id == "task_type":
                                task_type_value = self._extract_string_value(item.value)

            if name_value and isinstance(name_value, str):
                tasks.append(
                    TaskInfo(
                        name=name_value,
                        class_name=node.name,
                        task_type=task_type_value,
                        description=docstring,
                        file_path=relative_path,
                    )
                )

        return tasks

    def _collect_tasks_from_directory(self, directory: Path, base_path: Path) -> list[TaskInfo]:
        """Recursively collect task info from all Python files in a directory."""
        tasks = []

        try:
            for item in directory.iterdir():
                if item.name.startswith(".") or item.name == "__pycache__":
                    continue

                if item.is_dir():
                    tasks.extend(self._collect_tasks_from_directory(item, base_path))
                elif item.suffix == ".py" and item.name != "__init__.py":
                    relative_path = str(item.relative_to(base_path))
                    tasks.extend(self._extract_task_info_from_file(item, relative_path))
        except PermissionError:
            logger.warning(f"Permission denied accessing directory: {directory}")

        return tasks

    @staticmethod
    def _get_directory_mtime_sum(directory: Path) -> float:
        """Calculate sum of modification times for all Python files in directory."""
        mtime_sum = 0.0
        try:
            for item in directory.rglob("*.py"):
                if item.name.startswith(".") or "__pycache__" in str(item):
                    continue
                with contextlib.suppress(OSError):
                    mtime_sum += item.stat().st_mtime
        except PermissionError:
            pass
        return mtime_sum

    @staticmethod
    def _extract_string_value(node: ast.expr | None) -> str | None:
        """Extract string value from AST node."""
        if node is None:
            return None
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    @staticmethod
    def _is_valid_python_file(file_path: Path) -> bool:
        """Check if a file is a valid Python file that can be parsed."""
        if not file_path.exists() or not file_path.is_file() or file_path.suffix != ".py":
            return False
        try:
            if file_path.stat().st_size > 1_000_000:
                logger.warning(f"Skipping large file: {file_path}")
                return False
        except OSError:
            return False
        return True
