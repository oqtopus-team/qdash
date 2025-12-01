from __future__ import annotations

import logging
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

import yaml
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.logger import logger
from fastapi.responses import FileResponse
from git import Repo
from git.exc import GitCommandError
from qdash.api.lib.auth import get_current_active_user
from qdash.api.schemas.auth import User
from qdash.api.schemas.file import (
    FileTreeNode,
    GitPushRequest,
    SaveFileRequest,
    ValidateFileRequest,
)

router = APIRouter()
gunicorn_logger = logging.getLogger("gunicorn.error")
logger.handlers = gunicorn_logger.handlers
if __name__ != "main":
    logger.setLevel(gunicorn_logger.level)
else:
    logger.setLevel(logging.DEBUG)

# Get config path from environment variable
# In Docker, CONFIG_PATH is mounted to /app/config/qubex
# In local dev, it's ./config/qubex
CONFIG_BASE_PATH = Path(os.getenv("CONFIG_PATH", "./config/qubex"))

# If running in Docker (check if /app exists), use absolute path
if Path("/app").exists() and not CONFIG_BASE_PATH.is_absolute():
    CONFIG_BASE_PATH = Path("/app") / "config" / "qubex"


def validate_config_path(relative_path: str) -> Path:
    """Validate relative_path to prevent path traversal attacks.

    Args:
    ----
        relative_path: Relative path from CONFIG_BASE_PATH (e.g., "64Qv2/config/chip.yaml")

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

    target_path = CONFIG_BASE_PATH / relative_path
    resolved_path = target_path.resolve()

    # Ensure resolved path is within CONFIG_BASE_PATH
    if not str(resolved_path).startswith(str(CONFIG_BASE_PATH.resolve())):
        raise HTTPException(status_code=400, detail="Path outside config directory")

    return resolved_path


def build_file_tree(directory: Path, base_path: Path) -> list[FileTreeNode]:
    """Build file tree structure recursively.

    Args:
    ----
        directory: Directory to scan
        base_path: Base path for calculating relative paths

    Returns:
    -------
        List of FileTreeNode

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
                children = build_file_tree(item, base_path)
                nodes.append(
                    FileTreeNode(
                        name=item.name,
                        path=relative_path,
                        type="directory",
                        children=children if children else None,
                    )
                )
            else:
                nodes.append(
                    FileTreeNode(
                        name=item.name,
                        path=relative_path,
                        type="file",
                        children=None,
                    )
                )

    except PermissionError:
        logger.warning(f"Permission denied accessing directory: {directory}")

    return nodes


@router.get(
    "/file/raw_data",
    summary="download file",
    operation_id="downloadFile",
    response_class=FileResponse,
)
def download_file(path: str) -> FileResponse:
    """Download a file."""
    if not Path(path).exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    return FileResponse(path=path)


@router.get(
    "/file/zip",
    summary="download file or directory as zip",
    operation_id="downloadZipFile",
    response_class=FileResponse,
)
def download_zip_file(path: str) -> FileResponse:
    """Download a file or directory as zip."""
    import shutil
    import tempfile

    source_path = Path(path)
    if not source_path.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")

    # Create a temporary directory that will persist until explicitly removed
    temp_dir = tempfile.mkdtemp()
    temp_dir_path = Path(temp_dir)
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    zip_filename = f"{source_path.name}_{timestamp}.zip"

    try:
        if source_path.is_dir():
            # If it's a directory, zip its contents
            # make_archive returns the path to the created zip file
            actual_zip_path = Path(shutil.make_archive(str(temp_dir_path / source_path.name), "zip", source_path))
        else:
            # If it's a file, create a zip containing just that file
            actual_zip_path = temp_dir_path / zip_filename
            with zipfile.ZipFile(actual_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(source_path, source_path.name)

        if not actual_zip_path.is_file():
            raise Exception(f"Failed to create zip file at {actual_zip_path}")

        logger.info(f"Created zip file: {actual_zip_path}")

        # Create a FileResponse with a cleanup callback
        def cleanup_temp_dir() -> None:
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
                logger.info(f"Cleaned up temp directory: {temp_dir}")
            except Exception as e:
                logger.error(f"Error cleaning up temp directory: {e}")

        background_tasks = BackgroundTasks()
        background_tasks.add_task(cleanup_temp_dir)
        return FileResponse(
            path=str(actual_zip_path),
            filename=zip_filename,
            media_type="application/zip",
            background=background_tasks,
        )

    except Exception as e:
        # Clean up temp directory in case of error
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.error(f"Error creating zip file: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating zip file: {e!s}")


@router.get(
    "/file/tree",
    summary="Get file tree for entire config directory",
    operation_id="getFileTree",
    response_model=list[FileTreeNode],
)
def get_file_tree() -> list[FileTreeNode]:
    """Get file tree structure for entire config directory (all chips).

    Returns
    -------
        File tree structure

    """
    if not CONFIG_BASE_PATH.exists():
        raise HTTPException(status_code=404, detail=f"Config directory not found: {CONFIG_BASE_PATH}")

    return build_file_tree(CONFIG_BASE_PATH, CONFIG_BASE_PATH)


@router.get(
    "/file/content",
    summary="Get file content for editing",
    operation_id="getFileContent",
)
def get_file_content(path: str) -> dict[str, Any]:
    """Get file content for editing.

    Args:
    ----
        path: Relative path from CONFIG_BASE_PATH (e.g., "64Qv2/config/chip.yaml")

    Returns:
    -------
        File content and metadata

    """
    file_path = validate_config_path(path)

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    if not file_path.is_file():
        raise HTTPException(status_code=400, detail=f"Not a file: {path}")

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
    "/file/content",
    summary="Save file content",
    operation_id="saveFileContent",
)
def save_file_content(
    request: SaveFileRequest,
    _current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict[str, str]:
    """Save file content.

    Args:
    ----
        request: Save file request with path and content

    Returns:
    -------
        Success message

    """
    file_path = validate_config_path(request.path)

    try:
        # Create parent directory if it doesn't exist
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write content
        file_path.write_text(request.content, encoding="utf-8")

        logger.info(f"File saved successfully: {file_path}")
        return {
            "message": "File saved successfully",
            "path": request.path,
        }
    except Exception as e:
        logger.error(f"Error saving file {file_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Error saving file: {e!s}")


@router.post(
    "/file/validate",
    summary="Validate file content (YAML/JSON)",
    operation_id="validateFileContent",
)
def validate_file_content(request: ValidateFileRequest) -> dict[str, Any]:
    """Validate YAML or JSON content.

    Args:
    ----
        request: Validation request with content and file_type

    Returns:
    -------
        Validation result

    """
    import json

    try:
        if request.file_type.lower() in ["yaml", "yml"]:
            # Validate YAML
            yaml.safe_load(request.content)
            return {"valid": True, "message": "Valid YAML"}
        elif request.file_type.lower() == "json":
            # Validate JSON
            json.loads(request.content)
            return {"valid": True, "message": "Valid JSON"}
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type. Use 'yaml' or 'json'")
    except yaml.YAMLError as e:
        return {
            "valid": False,
            "message": f"Invalid YAML: {e!s}",
            "error": str(e),
        }
    except json.JSONDecodeError as e:
        return {
            "valid": False,
            "message": f"Invalid JSON: {e!s}",
            "error": str(e),
        }
    except Exception as e:
        logger.error(f"Error validating file content: {e}")
        raise HTTPException(status_code=500, detail=f"Validation error: {e!s}")


@router.get(
    "/file/git/status",
    summary="Get Git status of config directory",
    operation_id="getGitStatus",
)
def get_git_status() -> dict[str, Any]:
    """Get Git status of config directory.

    Returns
    -------
        Git status information

    """
    try:
        if not CONFIG_BASE_PATH.exists():
            raise HTTPException(status_code=404, detail=f"Config directory not found: {CONFIG_BASE_PATH}")

        # Check if directory is a Git repository
        git_dir = CONFIG_BASE_PATH / ".git"
        if not git_dir.exists():
            return {
                "is_git_repo": False,
                "message": "Config directory is not a Git repository",
            }

        repo = Repo(CONFIG_BASE_PATH)

        # Get current branch
        current_branch = repo.active_branch.name

        # Get current commit
        current_commit = repo.head.commit.hexsha[:8]
        commit_message = repo.head.commit.message.strip()

        # Check for uncommitted changes
        is_dirty = repo.is_dirty(untracked_files=True)
        untracked_files = repo.untracked_files
        changed_files = [item.a_path for item in repo.index.diff(None)]

        return {
            "is_git_repo": True,
            "branch": current_branch,
            "commit": current_commit,
            "commit_message": commit_message,
            "is_dirty": is_dirty,
            "changed_files": changed_files,
            "untracked_files": untracked_files,
        }

    except Exception as e:
        logger.error(f"Error getting Git status: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting Git status: {e!s}")


@router.post(
    "/file/git/pull",
    summary="Pull latest config from Git repository",
    operation_id="gitPullConfig",
)
def git_pull_config(
    _current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict[str, Any]:
    """Pull latest config from Git repository.

    Returns
    -------
        Pull operation result

    """
    import shutil
    import tempfile
    from urllib.parse import urlparse, urlunparse

    try:
        # Get authentication details from environment
        github_user = os.getenv("GITHUB_USER")
        github_token = os.getenv("GITHUB_TOKEN")
        repo_url = os.getenv("CONFIG_REPO_URL")

        if not all([github_user, github_token, repo_url]):
            raise HTTPException(
                status_code=500,
                detail="Missing required environment variables: GITHUB_USER, GITHUB_TOKEN, CONFIG_REPO_URL",
            )

        # Parse and reconstruct URL with authentication
        parsed = urlparse(repo_url)
        auth_netloc = f"{github_user}:{github_token}@{parsed.netloc}"
        auth_url = urlunparse((parsed.scheme, auth_netloc, parsed.path, "", "", ""))

        # Create temporary directory and clone repository
        temp_dir = tempfile.mkdtemp()
        temp_dir_path = Path(temp_dir)

        try:
            logger.info("Cloning repository to temporary directory")
            repo = Repo.clone_from(auth_url, temp_dir)

            # Create backup of current config if it exists
            if CONFIG_BASE_PATH.exists():
                backup_dir = (
                    CONFIG_BASE_PATH.parent / f"config_backup_{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}"
                )
                shutil.copytree(CONFIG_BASE_PATH, backup_dir)
                logger.info(f"Created backup at: {backup_dir}")

            # Get latest changes
            logger.info("Fetching latest changes")
            repo.remotes.origin.fetch()
            repo.git.reset("--hard", "origin/main")

            # Create target directory if it doesn't exist
            CONFIG_BASE_PATH.mkdir(parents=True, exist_ok=True)

            # Copy files
            config_source = Path(temp_dir)
            for item in config_source.glob("*"):
                if item.name == ".git":
                    continue

                destination = CONFIG_BASE_PATH / item.name
                if item.is_file():
                    shutil.copy2(item, destination)
                else:
                    shutil.copytree(item, destination, dirs_exist_ok=True)

            # Log success with commit information
            current = repo.head.commit
            commit_sha = current.hexsha[:8]
            commit_msg = current.message.strip()

            logger.info(f"Updated to commit: {commit_sha} - {commit_msg}")
            logger.info(f"Config files updated successfully in: {CONFIG_BASE_PATH}")

            return {
                "success": True,
                "commit": commit_sha,
                "commit_message": commit_msg,
                "message": "Config files updated successfully",
            }

        finally:
            if temp_dir_path.exists():
                shutil.rmtree(temp_dir)

    except GitCommandError as e:
        logger.error(f"Git pull failed: {e.stderr}")
        raise HTTPException(status_code=500, detail=f"Git pull failed: {e.stderr}")
    except Exception as e:
        logger.error(f"Error pulling from Git: {e}")
        raise HTTPException(status_code=500, detail=f"Error pulling from Git: {e!s}")


@router.post(
    "/file/git/push",
    summary="Push config changes to Git repository",
    operation_id="gitPushConfig",
)
def git_push_config(
    request: GitPushRequest,
    _current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict[str, Any]:
    """Push config changes to Git repository.

    Args:
    ----
        request: Push request with commit message

    Returns:
    -------
        Push operation result

    """
    import shutil
    import tempfile
    from urllib.parse import urlparse, urlunparse

    import pendulum

    try:
        # Get authentication details from environment
        github_user = os.getenv("GITHUB_USER")
        github_token = os.getenv("GITHUB_TOKEN")
        repo_url = os.getenv("CONFIG_REPO_URL")

        if not all([github_user, github_token, repo_url]):
            raise HTTPException(
                status_code=500,
                detail="Missing required environment variables: GITHUB_USER, GITHUB_TOKEN, CONFIG_REPO_URL",
            )

        # Parse and reconstruct URL with authentication
        parsed = urlparse(repo_url)
        auth_netloc = f"{github_user}:{github_token}@{parsed.netloc}"
        auth_url = urlunparse((parsed.scheme, auth_netloc, parsed.path, "", "", ""))

        # Create temporary directory and clone repository
        temp_dir = tempfile.mkdtemp()
        temp_dir_path = Path(temp_dir)

        try:
            logger.info("Cloning repository to temporary directory")
            repo = Repo.clone_from(auth_url, temp_dir, branch="main")

            # Copy all files from CONFIG_BASE_PATH to temp repo (excluding .git)
            for item in CONFIG_BASE_PATH.glob("*"):
                if item.name == ".git":
                    continue

                destination = temp_dir_path / item.name
                if item.is_file():
                    shutil.copy2(item, destination)
                else:
                    shutil.copytree(item, destination, dirs_exist_ok=True)

            # Git operations
            repo.git.add(A=True)  # Add all files

            # Check if there are changes to commit
            diff = repo.index.diff("HEAD")
            if not diff and not repo.untracked_files:
                logger.info("No changes to commit")
                return {
                    "success": True,
                    "message": "No changes to commit",
                    "commit": None,
                }

            # Configure git user
            repo.git.config("user.name", "qdash-ui")
            repo.git.config("user.email", "qdash-ui@users.noreply.github.com")

            # Commit with timestamp
            now_jst = pendulum.now("Asia/Tokyo").to_iso8601_string()
            commit_msg = f"{request.commit_message} at {now_jst}"
            repo.index.commit(commit_msg)

            # Push to remote
            logger.info("Pushing to remote repository")
            repo.remotes.origin.push()

            commit_sha = repo.head.commit.hexsha[:8]
            logger.info(f"Pushed commit: {commit_sha}")

            return {
                "success": True,
                "commit": commit_sha,
                "commit_message": commit_msg,
                "message": "Config files pushed successfully",
            }

        finally:
            if temp_dir_path.exists():
                shutil.rmtree(temp_dir)

    except GitCommandError as e:
        logger.error(f"Git push failed: {e.stderr}")
        raise HTTPException(status_code=500, detail=f"Git push failed: {e.stderr}")
    except Exception as e:
        logger.error(f"Error pushing to Git: {e}")
        raise HTTPException(status_code=500, detail=f"Error pushing to Git: {e!s}")
