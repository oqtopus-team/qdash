"""Task file router for QDash API."""

from __future__ import annotations

import ast
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

import yaml
from fastapi import APIRouter, Depends, HTTPException
from fastapi.logger import logger
from qdash.api.lib.auth import get_current_active_user
from qdash.api.schemas.auth import User
from qdash.api.schemas.task_file import (
    FileNodeType,
    ListTaskFileBackendsResponse,
    ListTaskInfoResponse,
    SaveTaskFileRequest,
    TaskFileBackend,
    TaskFileSettings,
    TaskFileTreeNode,
    TaskInfo,
)

router = APIRouter()
gunicorn_logger = logging.getLogger("gunicorn.error")
logger.handlers = gunicorn_logger.handlers
if __name__ != "main":
    logger.setLevel(gunicorn_logger.level)
else:
    logger.setLevel(logging.DEBUG)

# Get caltasks path from environment variable or use default
# In Docker, this path is typically /app/src/qdash/workflow/caltasks
# In local dev, it's ./src/qdash/workflow/caltasks
CALTASKS_BASE_PATH = Path(os.getenv("CALTASKS_PATH", "./src/qdash/workflow/caltasks"))

# If running in Docker (check if /app exists), use absolute path
if Path("/app").exists() and not CALTASKS_BASE_PATH.is_absolute():
    CALTASKS_BASE_PATH = Path("/app") / "src" / "qdash" / "workflow" / "caltasks"

# Settings file path
SETTINGS_PATH = Path(os.getenv("SETTINGS_PATH", "./config/settings.yaml"))
if Path("/app").exists() and not SETTINGS_PATH.is_absolute():
    SETTINGS_PATH = Path("/app") / "config" / "settings.yaml"

# Cache for task metadata: {backend: (mtime_sum, tasks)}
# Cache is invalidated when sum of file modification times changes
_task_cache: dict[str, tuple[float, list[TaskInfo]]] = {}


def validate_task_file_path(relative_path: str) -> Path:
    """Validate relative_path to prevent path traversal attacks.

    Args:
    ----
        relative_path: Relative path from CALTASKS_BASE_PATH (e.g., "qubex/one_qubit_coarse/check_rabi.py")

    Returns:
    -------
        Resolved absolute path

    Raises:
    ------
        HTTPException: If validation fails

    """
    # Prevent path traversal
    if ".." in relative_path:
        raise HTTPException(status_code=400, detail="Path traversal detected")

    target_path = CALTASKS_BASE_PATH / relative_path
    resolved_path = target_path.resolve()

    # Ensure resolved path is within CALTASKS_BASE_PATH
    if not str(resolved_path).startswith(str(CALTASKS_BASE_PATH.resolve())):
        raise HTTPException(status_code=400, detail="Path outside caltasks directory")

    return resolved_path


def build_task_file_tree(directory: Path, base_path: Path) -> list[TaskFileTreeNode]:
    """Build task file tree structure recursively.

    Args:
    ----
        directory: Directory to scan
        base_path: Base path for calculating relative paths

    Returns:
    -------
        List of TaskFileTreeNode

    """
    nodes = []

    try:
        items = sorted(directory.iterdir(), key=lambda x: (not x.is_dir(), x.name))

        for item in items:
            # Skip hidden files and __pycache__
            if item.name.startswith(".") or item.name == "__pycache__":
                continue

            relative_path = str(item.relative_to(base_path))

            if item.is_dir():
                children = build_task_file_tree(item, base_path)
                nodes.append(
                    TaskFileTreeNode(
                        name=item.name,
                        path=relative_path,
                        type=FileNodeType.DIRECTORY,
                        children=children if children else None,
                    )
                )
            else:
                # Only include Python files
                if item.suffix == ".py":
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


@router.get(
    "/task-files/settings",
    response_model=TaskFileSettings,
    summary="Get task file settings",
    operation_id="getTaskFileSettings",
)
def get_task_file_settings() -> TaskFileSettings:
    """Get task file settings from config/settings.yaml.

    Returns
    -------
        Task file settings including default backend

    """
    try:
        if SETTINGS_PATH.exists():
            with open(SETTINGS_PATH, encoding="utf-8") as f:
                settings = yaml.safe_load(f)
                task_files_settings = settings.get("task_files", {})
                return TaskFileSettings(
                    default_backend=task_files_settings.get("default_backend"),
                    default_view_mode=task_files_settings.get("default_view_mode"),
                    sort_order=task_files_settings.get("sort_order"),
                )
    except Exception as e:
        logger.warning(f"Failed to load settings from {SETTINGS_PATH}: {e}")

    return TaskFileSettings()


@router.get(
    "/task-files/backends",
    response_model=ListTaskFileBackendsResponse,
    summary="List available task file backends",
    operation_id="listTaskFileBackends",
)
def list_task_file_backends() -> ListTaskFileBackendsResponse:
    """List all available backend directories in caltasks.

    Returns
    -------
        List of backend names and paths

    """
    if not CALTASKS_BASE_PATH.exists():
        raise HTTPException(status_code=404, detail=f"Caltasks directory not found: {CALTASKS_BASE_PATH}")

    backends = []
    try:
        for item in sorted(CALTASKS_BASE_PATH.iterdir()):
            # Skip hidden files, __pycache__, and non-directories
            if item.name.startswith(".") or item.name == "__pycache__" or not item.is_dir():
                continue
            backends.append(TaskFileBackend(name=item.name, path=item.name))
    except PermissionError:
        logger.warning(f"Permission denied accessing directory: {CALTASKS_BASE_PATH}")

    return ListTaskFileBackendsResponse(backends=backends)


@router.get(
    "/task-files/tree",
    summary="Get file tree for a specific backend",
    operation_id="getTaskFileTree",
    response_model=list[TaskFileTreeNode],
)
def get_task_file_tree(backend: str) -> list[TaskFileTreeNode]:
    """Get file tree structure for a specific backend directory.

    Args:
    ----
        backend: Backend name (e.g., "qubex", "fake")

    Returns:
    -------
        File tree structure for the backend

    """
    backend_path = CALTASKS_BASE_PATH / backend

    if not backend_path.exists():
        raise HTTPException(status_code=404, detail=f"Backend directory not found: {backend}")

    if not backend_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {backend}")

    return build_task_file_tree(backend_path, backend_path)


@router.get(
    "/task-files/content",
    summary="Get task file content for viewing/editing",
    operation_id="getTaskFileContent",
)
def get_task_file_content(path: str) -> dict[str, Any]:
    """Get task file content for viewing/editing.

    Args:
    ----
        path: Relative path from CALTASKS_BASE_PATH (e.g., "qubex/one_qubit_coarse/check_rabi.py")

    Returns:
    -------
        File content and metadata

    """
    file_path = validate_task_file_path(path)

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    if not file_path.is_file():
        raise HTTPException(status_code=400, detail=f"Not a file: {path}")

    # Only allow Python files
    if file_path.suffix != ".py":
        raise HTTPException(status_code=400, detail="Only Python files are allowed")

    try:
        content = file_path.read_text(encoding="utf-8")
        return {
            "content": content,
            "path": path,
            "name": file_path.name,
            "size": file_path.stat().st_size,
            "modified": datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc).isoformat(),
        }
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File is not a text file")
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Error reading file: {e!s}")


@router.put(
    "/task-files/content",
    summary="Save task file content",
    operation_id="saveTaskFileContent",
)
def save_task_file_content(
    request: SaveTaskFileRequest,
    _current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict[str, str]:
    """Save task file content.

    Args:
    ----
        request: Save file request with path and content

    Returns:
    -------
        Success message

    """
    file_path = validate_task_file_path(request.path)

    # Only allow Python files
    if not request.path.endswith(".py"):
        raise HTTPException(status_code=400, detail="Only Python files are allowed")

    # Only allow editing existing files (no creating new files)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {request.path}")

    try:
        # Write content
        file_path.write_text(request.content, encoding="utf-8")

        logger.info(f"Task file saved successfully: {file_path}")
        return {
            "message": "File saved successfully",
            "path": request.path,
        }
    except Exception as e:
        logger.error(f"Error saving file {file_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Error saving file: {e!s}")


def _extract_string_value(node: ast.expr | None) -> str | None:
    """Extract string value from AST node, handling various assignment patterns.

    Handles:
    - Simple constants: name = "CheckRabi"
    - Annotated assignments: name: str = "CheckRabi"

    Does NOT handle (returns None):
    - Dynamic assignments: name = get_task_name()
    - Complex expressions: name = PREFIX + "_task"
    - f-strings: name = f"{prefix}_task"

    Args:
    ----
        node: AST expression node

    Returns:
    -------
        String value if extractable, None otherwise

    """
    if node is None:
        return None

    # Handle simple string constants
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value

    return None


def _is_valid_python_file(file_path: Path) -> bool:
    """Check if a file is a valid Python file that can be parsed.

    Args:
    ----
        file_path: Path to the file

    Returns:
    -------
        True if file is valid Python, False otherwise

    """
    if not file_path.exists():
        return False

    if not file_path.is_file():
        return False

    if file_path.suffix != ".py":
        return False

    # Check file size (skip very large files > 1MB)
    try:
        if file_path.stat().st_size > 1_000_000:
            logger.warning(f"Skipping large file: {file_path}")
            return False
    except OSError:
        return False

    return True


def extract_task_info_from_file(file_path: Path, relative_path: str) -> list[TaskInfo]:
    """Extract task information from a Python file using AST parsing.

    Args:
    ----
        file_path: Absolute path to the Python file
        relative_path: Relative path for display

    Returns:
    -------
        List of TaskInfo objects found in the file

    """
    tasks = []

    # Validate file before parsing
    if not _is_valid_python_file(file_path):
        return tasks

    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # Log without exposing file details
        logger.warning(f"Failed to read file: {relative_path}")
        return tasks

    try:
        tree = ast.parse(content)
    except SyntaxError:
        # Log without exposing syntax error details
        logger.warning(f"Invalid Python syntax in file: {relative_path}")
        return tasks

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue

        # Look for classes that might be tasks
        name_value = None
        task_type_value = None
        docstring = ast.get_docstring(node)

        for item in node.body:
            # Handle annotated assignments: name: str = "value"
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                if item.target.id == "name":
                    name_value = _extract_string_value(item.value)
                elif item.target.id == "task_type":
                    task_type_value = _extract_string_value(item.value)

            # Handle simple assignments: name = "value"
            elif isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        if target.id == "name":
                            name_value = _extract_string_value(item.value)
                        elif target.id == "task_type":
                            task_type_value = _extract_string_value(item.value)

        # Only include if it has a valid string name attribute (indicating it's a task)
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


def collect_tasks_from_directory(directory: Path, base_path: Path) -> list[TaskInfo]:
    """Recursively collect task info from all Python files in a directory.

    Args:
    ----
        directory: Directory to scan
        base_path: Base path for calculating relative paths

    Returns:
    -------
        List of TaskInfo objects

    """
    tasks = []

    try:
        for item in directory.iterdir():
            if item.name.startswith(".") or item.name == "__pycache__":
                continue

            if item.is_dir():
                tasks.extend(collect_tasks_from_directory(item, base_path))
            elif item.suffix == ".py" and item.name != "__init__.py":
                relative_path = str(item.relative_to(base_path))
                tasks.extend(extract_task_info_from_file(item, relative_path))
    except PermissionError:
        logger.warning(f"Permission denied accessing directory: {directory}")

    return tasks


def _get_directory_mtime_sum(directory: Path) -> float:
    """Calculate sum of modification times for all Python files in directory.

    Used for cache invalidation.

    Args:
    ----
        directory: Directory to scan

    Returns:
    -------
        Sum of file modification times

    """
    mtime_sum = 0.0
    try:
        for item in directory.rglob("*.py"):
            if item.name.startswith(".") or "__pycache__" in str(item):
                continue
            try:
                mtime_sum += item.stat().st_mtime
            except OSError:
                pass
    except PermissionError:
        pass
    return mtime_sum


@router.get(
    "/task-files/tasks",
    response_model=ListTaskInfoResponse,
    summary="List all tasks in a backend",
    operation_id="listTaskInfo",
)
def list_task_info(
    backend: str,
    sort_order: str | None = None,
) -> ListTaskInfoResponse:
    """List all task definitions found in a backend directory.

    Parses Python files to extract task names, types, and descriptions.
    Results are cached and invalidated when files are modified.

    Args:
    ----
        backend: Backend name (e.g., "qubex", "fake")
        sort_order: Sort order for tasks ("type_then_name", "name_only", "file_path")

    Returns:
    -------
        List of task information

    """
    backend_path = CALTASKS_BASE_PATH / backend

    if not backend_path.exists():
        raise HTTPException(status_code=404, detail=f"Backend directory not found: {backend}")

    if not backend_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {backend}")

    # Check cache (include sort_order in cache key)
    cache_key = f"{backend}:{sort_order or 'default'}"
    current_mtime = _get_directory_mtime_sum(backend_path)
    cached = _task_cache.get(cache_key)

    if cached is not None:
        cached_mtime, cached_tasks = cached
        if cached_mtime == current_mtime:
            logger.debug(f"Using cached task list for backend: {backend}")
            return ListTaskInfoResponse(tasks=cached_tasks)

    # Parse files and update cache
    logger.debug(f"Parsing task files for backend: {backend}")
    tasks = collect_tasks_from_directory(backend_path, backend_path)

    # Sort based on sort_order parameter
    if sort_order == "name_only":
        tasks.sort(key=lambda t: t.name)
    elif sort_order == "file_path":
        tasks.sort(key=lambda t: (t.file_path, t.name))
    else:
        # Default: type_then_name
        tasks.sort(key=lambda t: (t.task_type or "", t.name))

    # Update cache
    _task_cache[cache_key] = (current_mtime, tasks)

    return ListTaskInfoResponse(tasks=tasks)
