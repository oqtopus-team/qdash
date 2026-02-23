"""Service for config file operations and Git integration."""

from __future__ import annotations

import logging
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from fastapi import BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from git import Repo
from git.exc import GitCommandError
from qdash.api.lib.file_utils import validate_relative_path
from qdash.api.schemas.file import FileTreeNode
from qdash.common.datetime_utils import now_iso
from qdash.common.paths import QUBEX_CONFIG_BASE

logger = logging.getLogger(__name__)


class FileService:
    """Service for config file browsing, editing, and Git operations."""

    def __init__(self, config_base_path: Path | None = None) -> None:
        """Initialize the service.

        Parameters
        ----------
        config_base_path : Path | None
            Base path for config files. Defaults to QUBEX_CONFIG_BASE.

        """
        self._base_path = config_base_path or QUBEX_CONFIG_BASE

    def download_file(self, path: str) -> FileResponse:
        """Download a raw data file.

        Parameters
        ----------
        path : str
            Absolute file path.

        Returns
        -------
        FileResponse
            The file as a downloadable response.

        """
        if not Path(path).exists():
            raise HTTPException(status_code=404, detail=f"File not found: {path}")

        return FileResponse(path=path)

    def download_zip_file(self, path: str) -> FileResponse:
        """Download a file or directory as a ZIP archive.

        Parameters
        ----------
        path : str
            Absolute path to the file or directory.

        Returns
        -------
        FileResponse
            ZIP archive as a downloadable response.

        """
        import shutil
        import tempfile

        source_path = Path(path)
        if not source_path.exists():
            raise HTTPException(status_code=404, detail=f"Path not found: {path}")

        temp_dir = tempfile.mkdtemp()
        temp_dir_path = Path(temp_dir)
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        zip_filename = f"{source_path.name}_{timestamp}.zip"

        try:
            if source_path.is_dir():
                actual_zip_path = Path(
                    shutil.make_archive(str(temp_dir_path / source_path.name), "zip", source_path)
                )
            else:
                actual_zip_path = temp_dir_path / zip_filename
                with zipfile.ZipFile(actual_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    zf.write(source_path, source_path.name)

            if not actual_zip_path.is_file():
                raise Exception(f"Failed to create zip file at {actual_zip_path}")

            logger.info(f"Created zip file: {actual_zip_path}")

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
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.error(f"Error creating zip file: {e}")
            raise HTTPException(status_code=500, detail=f"Error creating zip file: {e!s}")

    def get_file_tree(self) -> list[FileTreeNode]:
        """Get file tree structure for entire config directory.

        Returns
        -------
        list[FileTreeNode]
            File tree structure.

        """
        if not self._base_path.exists():
            raise HTTPException(
                status_code=404, detail=f"Config directory not found: {self._base_path}"
            )

        return self._build_file_tree(self._base_path, self._base_path)

    def get_file_content(self, path: str) -> dict[str, Any]:
        """Get file content for editing.

        Parameters
        ----------
        path : str
            Relative path from config base path.

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

    def save_file_content(self, path: str, content: str) -> dict[str, str]:
        """Save file content.

        Parameters
        ----------
        path : str
            Relative path from config base path.
        content : str
            File content to save.

        Returns
        -------
        dict[str, str]
            Success message.

        """
        file_path = validate_relative_path(path, self._base_path)

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            logger.info(f"File saved successfully: {file_path}")
            return {
                "message": "File saved successfully",
                "path": path,
            }
        except Exception as e:
            logger.error(f"Error saving file {file_path}: {e}")
            raise HTTPException(status_code=500, detail=f"Error saving file: {e!s}")

    def validate_file_content(self, content: str, file_type: str) -> dict[str, Any]:
        """Validate YAML or JSON content.

        Parameters
        ----------
        content : str
            File content to validate.
        file_type : str
            File type ("yaml", "yml", or "json").

        Returns
        -------
        dict[str, Any]
            Validation result.

        """
        import json

        try:
            if file_type.lower() in ["yaml", "yml"]:
                yaml.safe_load(content)
                return {"valid": True, "message": "Valid YAML"}
            elif file_type.lower() == "json":
                json.loads(content)
                return {"valid": True, "message": "Valid JSON"}
            else:
                raise HTTPException(
                    status_code=400, detail="Unsupported file type. Use 'yaml' or 'json'"
                )
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

    def get_git_status(self) -> dict[str, Any]:
        """Get Git status of config directory.

        Returns
        -------
        dict[str, Any]
            Git status information.

        """
        try:
            if not self._base_path.exists():
                raise HTTPException(
                    status_code=404, detail=f"Config directory not found: {self._base_path}"
                )

            git_dir = self._base_path / ".git"
            if not git_dir.exists():
                return {
                    "is_git_repo": False,
                    "message": "Config directory is not a Git repository",
                }

            repo = Repo(self._base_path)

            current_branch = repo.active_branch.name
            current_commit = repo.head.commit.hexsha[:8]
            commit_message = repo.head.commit.message.strip()
            is_dirty = repo.is_dirty(untracked_files=True)
            untracked_files = repo.untracked_files
            changed_files = [item.a_path for item in repo.index.diff(None)]

            has_remote_updates = False
            try:
                repo.remotes.origin.fetch()
                local_sha = repo.head.commit.hexsha
                remote_sha = repo.remotes.origin.refs.main.commit.hexsha
                has_remote_updates = local_sha != remote_sha
            except Exception:
                logger.debug("Failed to fetch remote for update check")

            return {
                "is_git_repo": True,
                "branch": current_branch,
                "commit": current_commit,
                "commit_message": commit_message,
                "is_dirty": is_dirty,
                "changed_files": changed_files,
                "untracked_files": untracked_files,
                "has_remote_updates": has_remote_updates,
            }

        except Exception as e:
            logger.error(f"Error getting Git status: {e}")
            raise HTTPException(status_code=500, detail=f"Error getting Git status: {e!s}")

    def git_pull_config(self) -> dict[str, Any]:
        """Pull latest config from Git repository.

        Returns
        -------
        dict[str, Any]
            Pull operation result.

        """
        import shutil
        from urllib.parse import urlparse, urlunparse

        repo_url = os.getenv("CONFIG_REPO_URL")

        try:
            github_user = os.getenv("GITHUB_USER")
            github_token = os.getenv("GITHUB_TOKEN")

            if not all([github_user, github_token, repo_url]):
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Missing required environment variables:"
                        " GITHUB_USER, GITHUB_TOKEN, CONFIG_REPO_URL"
                    ),
                )

            assert repo_url is not None

            parsed = urlparse(repo_url)
            auth_netloc = f"{github_user}:{github_token}@{parsed.netloc}"
            auth_url: str = urlunparse((parsed.scheme, auth_netloc, parsed.path, "", "", ""))

            if (self._base_path / ".git").exists():
                logger.info("Fetching latest changes from remote")
                repo = Repo(self._base_path)
                repo.remotes.origin.set_url(auth_url)
                repo.remotes.origin.fetch()
                repo.git.reset("--hard", "origin/main")
                repo.git.clean("-fd")
            else:
                logger.info("Cloning repository to config directory")
                if self._base_path.exists():
                    shutil.rmtree(self._base_path)
                self._base_path.parent.mkdir(parents=True, exist_ok=True)
                repo = Repo.clone_from(auth_url, str(self._base_path), depth=1)

            current = repo.head.commit
            commit_sha = current.hexsha[:8]
            commit_msg = (
                current.message
                if isinstance(current.message, str)
                else current.message.decode("utf-8")
            ).strip()

            logger.info(f"Updated to commit: {commit_sha} - {commit_msg}")
            logger.info(f"Config files updated successfully in: {self._base_path}")

            return {
                "success": True,
                "commit": commit_sha,
                "commit_message": commit_msg,
                "message": "Config files updated successfully",
            }

        except GitCommandError as e:
            error_msg = str(e.stderr)
            parsed_err = urlparse(repo_url or "")
            masked_url: str = urlunparse(
                (
                    parsed_err.scheme,
                    str(parsed_err.netloc).split("@")[-1],
                    parsed_err.path,
                    "",
                    "",
                    "",
                )
            )
            logger.error(f"Git pull failed for {masked_url}: {error_msg}")
            raise HTTPException(status_code=500, detail=f"Git pull failed: {error_msg}")
        except Exception as e:
            logger.error(f"Error pulling from Git: {e}")
            raise HTTPException(status_code=500, detail=f"Error pulling from Git: {e!s}")

    def git_push_config(self, commit_message: str) -> dict[str, Any]:
        """Push config changes to Git repository.

        Parameters
        ----------
        commit_message : str
            Commit message for the push.

        Returns
        -------
        dict[str, Any]
            Push operation result.

        """
        import re
        import shutil
        import tempfile
        from urllib.parse import urlparse, urlunparse

        import httpx

        repo_url = os.getenv("CONFIG_REPO_URL")

        try:
            github_user = os.getenv("GITHUB_USER")
            github_token = os.getenv("GITHUB_TOKEN")

            if not all([github_user, github_token, repo_url]):
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Missing required environment variables:"
                        " GITHUB_USER, GITHUB_TOKEN, CONFIG_REPO_URL"
                    ),
                )

            assert repo_url is not None

            match = re.match(r"https?://[^/]+/([^/]+)/([^/]+?)(?:\.git)?$", repo_url)
            if not match:
                raise HTTPException(status_code=500, detail="Invalid CONFIG_REPO_URL format")
            owner = match.group(1)
            repo_name = match.group(2)

            parsed = urlparse(repo_url)
            auth_netloc = f"{github_user}:{github_token}@{parsed.netloc}"
            auth_url: str = urlunparse((parsed.scheme, auth_netloc, parsed.path, "", "", ""))

            temp_dir = tempfile.mkdtemp()
            temp_dir_path = Path(temp_dir)

            try:
                logger.info("Cloning repository to temporary directory")
                repo = Repo.clone_from(auth_url, temp_dir, branch="main", depth=1)

                branch_name = (
                    f"config-update/{datetime.now(tz=timezone.utc).strftime('%Y%m%d-%H%M%S')}"
                )
                repo.git.checkout("-b", branch_name)

                added_files = []
                for item in self._base_path.rglob("*"):
                    if ".git" in item.parts:
                        continue
                    if item.is_file():
                        rel_path = item.relative_to(self._base_path)
                        destination = temp_dir_path / rel_path
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, destination)
                        added_files.append(str(rel_path))

                if not added_files:
                    logger.info("No files to commit")
                    return {
                        "success": True,
                        "message": "No files to commit",
                        "commit": None,
                    }

                repo.index.add(added_files)

                diff = repo.index.diff("HEAD")
                if not diff:
                    logger.info("No changes to commit")
                    return {
                        "success": True,
                        "message": "No changes to commit",
                        "commit": None,
                    }

                repo.git.config("user.name", "github-actions[bot]")
                repo.git.config("user.email", "github-actions[bot]@users.noreply.github.com")

                now_jst = now_iso()
                commit_msg = f"{commit_message} at {now_jst}"
                repo.index.commit(commit_msg)

                logger.info(f"Pushing branch {branch_name} to remote")
                repo.remotes.origin.push(refspec=f"{branch_name}:{branch_name}")

                commit_sha = repo.head.commit.hexsha[:8]

                logger.info("Creating pull request")
                pr_response = httpx.post(
                    f"https://api.github.com/repos/{owner}/{repo_name}/pulls",
                    headers={
                        "Authorization": f"token {github_token}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                    json={
                        "title": commit_message,
                        "head": branch_name,
                        "base": "main",
                        "body": (
                            f"Config update from QDash UI\n\n"
                            f"- Commit: `{commit_sha}`\n"
                            f"- Timestamp: {now_jst}\n"
                        ),
                    },
                    timeout=30,
                )
                pr_response.raise_for_status()
                pr_data = pr_response.json()

                logger.info(f"Pull request created: {pr_data['html_url']}")

                return {
                    "success": True,
                    "commit": commit_sha,
                    "commit_message": commit_msg,
                    "message": "Pull request created successfully",
                    "pr_url": pr_data["html_url"],
                    "pr_number": pr_data["number"],
                    "branch": branch_name,
                }

            finally:
                if temp_dir_path.exists():
                    shutil.rmtree(temp_dir)

        except GitCommandError as e:
            error_msg = str(e.stderr)
            parsed_err = urlparse(repo_url or "")
            masked_url: str = urlunparse(
                (
                    parsed_err.scheme,
                    str(parsed_err.netloc).split("@")[-1],
                    parsed_err.path,
                    "",
                    "",
                    "",
                )
            )
            logger.error(f"Git push failed for {masked_url}: {error_msg}")
            raise HTTPException(status_code=500, detail=f"Git push failed: {error_msg}")
        except httpx.HTTPStatusError as e:
            logger.error(f"GitHub API error: {e.response.text}")
            raise HTTPException(
                status_code=500, detail=f"Failed to create pull request: {e.response.text}"
            )
        except Exception as e:
            logger.error(f"Error pushing to Git: {e}")
            raise HTTPException(status_code=500, detail=f"Error pushing to Git: {e!s}")

    # --- Private helpers ---

    def _build_file_tree(self, directory: Path, base_path: Path) -> list[FileTreeNode]:
        """Build file tree structure recursively."""
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
