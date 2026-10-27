"""Service for a git-backed file workspace: browsing, editing, pull, and push as a PR.

Two workspaces are served: the Qubex config tree (``CONFIG_REPO_URL``) and the
task knowledge repository (``KNOWLEDGE_REPO_URL``). The same service drives
both; the workspace sets the directory, the repository, and what happens after
a save or a pull.
"""

from __future__ import annotations

import logging
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

import yaml
from fastapi import BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from git import Repo

from qdash.api.lib.file_utils import validate_relative_path
from qdash.api.schemas.file import FileTreeNode
from qdash.common.config.path_resolver import (
    PathOutsideCalibData,
    resolve_config_base_path,
    resolve_served_calib_data_path,
)
from qdash.common.config.qubex_layout import QubexLayout
from qdash.common.infrastructure.config_repository import (
    ConfigRepository,
    ConfigRepositoryError,
    DirtySharedFiles,
    GitHubSettings,
    RepoMode,
    get_config_repository,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

logger = logging.getLogger(__name__)


class FileService:
    """Service for config file browsing, editing, and Git operations."""

    def __init__(
        self,
        config_base_path: Path | None = None,
        *,
        label: str = "config",
        repo_url_env: str = "CONFIG_REPO_URL",
        after_save: Callable[[], None] | None = None,
        after_pull: Callable[[], None] | None = None,
        push_exclude: tuple[str, ...] = (),
    ) -> None:
        """Initialize the service.

        Parameters
        ----------
        config_base_path : Path | None
            Base path of the workspace. Defaults to the Qubex config tree.
        label : str
            Workspace name used in branch names, PR text, and messages.
        repo_url_env : str
            Environment variable holding the workspace's GitHub repository URL.
        after_save : Callable[[], None] | None
            Hook run after a file is saved (the knowledge workspace regenerates its JSON).
        after_pull : Callable[[], None] | None
            Hook run after a pull succeeds.
        push_exclude : tuple[str, ...]
            Workspace-relative paths left out of pushes (generated files CI rebuilds).

        """
        self._base_path = config_base_path or resolve_config_base_path()
        self._label = label
        self._repo_url_env = repo_url_env
        self._after_save = after_save
        self._after_pull = after_pull
        self._push_exclude = set(push_exclude)

    @property
    def label(self) -> str:
        """Workspace name."""
        return self._label

    def _git_env(self) -> dict[str, str]:
        """Environment for git commands on this workspace.

        The directory is a bind mount owned by the host user while the API runs
        as root, which git refuses as "dubious ownership"; mark it safe for this
        process only instead of writing a global git config. GitHub credentials
        go through a one-shot credential helper so the token never lands in the
        remote URL (which ``.git/config`` would keep in plain text on the mount).
        """
        entries = [("safe.directory", str(self._base_path))]
        github_user = os.getenv("GITHUB_USER")
        github_token = os.getenv("GITHUB_TOKEN")
        env = {"GIT_TERMINAL_PROMPT": "0"}
        if github_user and github_token:
            env["QDASH_GIT_USER"] = github_user
            env["QDASH_GIT_TOKEN"] = github_token
            entries.append(
                (
                    "credential.helper",
                    '!f() { echo "username=$QDASH_GIT_USER"; echo "password=$QDASH_GIT_TOKEN"; }; f',
                )
            )
        env["GIT_CONFIG_COUNT"] = str(len(entries))
        for index, (key, value) in enumerate(entries):
            env[f"GIT_CONFIG_KEY_{index}"] = key
            env[f"GIT_CONFIG_VALUE_{index}"] = value
        return env

    def _open_repo(self) -> Repo:
        """Open the workspace repository with :meth:`_git_env` applied."""
        repo = Repo(self._base_path)
        repo.git.update_environment(**self._git_env())
        return repo

    def _match_owner(self, file_path: Path) -> None:
        """Give a file the owner of its directory when running as root.

        Files the API writes into a bind mount would otherwise be root-owned on
        the host and break the host-side pull.
        """
        if os.name != "posix" or os.geteuid() != 0:
            return
        try:
            parent = file_path.parent.stat()
            os.chown(file_path, parent.st_uid, parent.st_gid)
        except OSError as exc:
            logger.debug("Could not match owner for %s: %s", file_path, exc)

    def _run_hook(self, hook: Callable[[], None] | None, stage: str) -> None:
        """Run a workspace hook; a failing hook fails the request, the file change stays."""
        if hook is None:
            return
        try:
            hook()
        except Exception as e:
            logger.error("%s workspace %s hook failed: %s", self._label, stage, e)
            raise HTTPException(
                status_code=500,
                detail=f"{self._label.capitalize()} {stage} done, but applying it failed: {e!s}",
            )

    def _workspace_files(self) -> Iterator[Path]:
        """Files to push, relative to the workspace, without git internals and excluded paths."""
        for item in sorted(self._base_path.rglob("*")):
            if ".git" in item.parts or not item.is_file():
                continue
            rel_path = item.relative_to(self._base_path)
            if rel_path.as_posix() in self._push_exclude:
                continue
            yield rel_path

    def download_file(self, path: str) -> FileResponse:
        """Download a raw data file from the calibration data tree.

        Parameters
        ----------
        path : str
            Absolute file path inside the calibration data tree.

        Returns
        -------
        FileResponse
            The file as a downloadable response.

        """
        try:
            resolved_path = resolve_served_calib_data_path(path)
        except PathOutsideCalibData:
            raise HTTPException(status_code=404, detail=f"File not found: {path}") from None
        if not resolved_path.is_file():
            raise HTTPException(status_code=404, detail=f"File not found: {path}")

        return FileResponse(path=resolved_path)

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

        source_path = self._resolve_download_path(path)
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

    def _resolve_download_path(self, path: str) -> Path:
        """Resolve a download path to the configured qubex-config tree."""
        base_path = self._base_path.resolve()
        requested_path = Path(path).expanduser()

        if not requested_path.is_absolute():
            return validate_relative_path(path, base_path)

        resolved_path = requested_path.resolve()
        if resolved_path == base_path.parent:
            return base_path

        if not resolved_path.is_relative_to(base_path):
            raise HTTPException(status_code=400, detail="Path outside config directory")

        return resolved_path

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
            base_content = content
            is_saved_change = False
            git_dir = self._base_path / ".git"
            if git_dir.exists():
                repo = self._open_repo()
                if repo.head.is_valid():
                    try:
                        blob = repo.head.commit.tree / Path(path).as_posix()
                        base_content = blob.data_stream.read().decode("utf-8")
                    except KeyError:
                        # An untracked text file has no content in HEAD.
                        base_content = ""
                else:
                    base_content = ""
                is_saved_change = content != base_content

            return {
                "content": content,
                "base_content": base_content,
                "is_saved_change": is_saved_change,
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

    # Raster formats only: an SVG can carry script when opened directly.
    IMAGE_MEDIA_TYPES: ClassVar[dict[str, str]] = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    MAX_IMAGE_BYTES: ClassVar[int] = 10 * 1024 * 1024

    def get_image(self, path: str) -> FileResponse:
        """Return an image inside the workspace, as Markdown previews reference them.

        Parameters
        ----------
        path : str
            Relative path from the workspace base path.

        Returns
        -------
        FileResponse
            The image with its media type.

        """
        file_path = validate_relative_path(path, self._base_path)
        media_type = self.IMAGE_MEDIA_TYPES.get(file_path.suffix.lower())
        if media_type is None:
            raise HTTPException(status_code=400, detail=f"Not an image: {path}")
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail=f"File not found: {path}")
        if file_path.stat().st_size > self.MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail=f"Image is too large: {path}")
        return FileResponse(file_path, media_type=media_type)

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
            self._match_owner(file_path)
            logger.info(f"File saved successfully: {file_path}")
        except Exception as e:
            logger.error(f"Error saving file {file_path}: {e}")
            raise HTTPException(status_code=500, detail=f"Error saving file: {e!s}")
        self._run_hook(self._after_save, "save")
        return {
            "message": "File saved successfully",
            "path": path,
        }

    def validate_file_content(
        self, content: str, file_type: str, path: str | None = None
    ) -> dict[str, Any]:
        """Validate YAML or JSON content, and its layout schema when ``path`` is given.

        Parameters
        ----------
        content : str
            File content to validate.
        file_type : str
            File type ("yaml", "yml", or "json").
        path : str | None
            Workspace-relative path the content will be saved to. In the Qubex config
            workspace it selects the JSON Schema of that file (chip, system, wiring,
            box, skew, params or the manifest); other paths get the syntax check only.

        Returns
        -------
        dict[str, Any]
            Validation result with ``problems`` (schema violations) when a schema applies.

        """
        import json

        try:
            if file_type.lower() in ["yaml", "yml"]:
                yaml.safe_load(content)
                return self._with_schema_problems(
                    {"valid": True, "message": "Valid YAML"}, content, path
                )
            elif file_type.lower() == "json":
                json.loads(content)
                return self._with_schema_problems(
                    {"valid": True, "message": "Valid JSON"}, content, path
                )
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

    def _with_schema_problems(
        self, result: dict[str, Any], content: str, path: str | None
    ) -> dict[str, Any]:
        """Add layout-schema problems for a Qubex config file; other workspaces pass through."""
        if not path or self._label != "config":
            return result
        from qdash.common.config.qubex_config_schema import schema_for, validate_text

        layout = QubexLayout.detect(self._base_path)
        schema_name = schema_for(path, layout)
        if schema_name is None:
            return result
        problems = validate_text(content, path, layout)
        result["schema"] = schema_name
        result["problems"] = [
            {"location": problem.location, "message": problem.message} for problem in problems
        ]
        if problems:
            result["valid"] = False
            result["message"] = f"{len(problems)} schema problem(s) in {path}"
        return result

    def _repository(self, actor: str = "config-ui") -> ConfigRepository:
        """The workspace's repository; the config workspace carries its Qubex layout."""
        settings = GitHubSettings.from_env(repo_url_env=self._repo_url_env)
        root: QubexLayout | Path = self._base_path
        if self._label == "config":
            root = QubexLayout.detect(self._base_path)
        return get_config_repository(root, actor=actor, settings=settings, label=self._label)

    def _require_github_mode(self, repository: ConfigRepository) -> None:
        if repository.mode is not RepoMode.GITHUB:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Missing required environment variables: "
                    + ", ".join(repository.settings.missing_variables)
                ),
            )

    def get_git_status(self) -> dict[str, Any]:
        """Get Git status of the workspace directory.

        Returns
        -------
        dict[str, Any]
            Git status information: the repository mode and layout, head, dirty
            files, unpushed commits, and whether the remote moved on.

        """
        try:
            if not self._base_path.exists():
                raise HTTPException(
                    status_code=404,
                    detail=f"{self._label.capitalize()} directory not found: {self._base_path}",
                )
            status = self._repository().status()
            if not status.is_git_repo:
                return {
                    "is_git_repo": False,
                    "mode": status.mode.value,
                    "layout": status.layout.value if status.layout else None,
                    "message": f"{self._label.capitalize()} directory is not a Git repository",
                }
            return {
                "is_git_repo": True,
                "mode": status.mode.value,
                "layout": status.layout.value if status.layout else None,
                "branch": status.branch,
                "commit": status.head,
                "commit_message": status.head_message,
                "is_dirty": status.is_dirty,
                "changed_files": status.changed_paths,
                "untracked_files": status.untracked_paths,
                "unpushed_commits": status.unpushed_commits,
                "has_remote_updates": status.has_remote_updates,
                "review_required": status.review_required,
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting Git status: {e}")
            raise HTTPException(status_code=500, detail=f"Error getting Git status: {e!s}")

    def git_pull_config(self, force: bool = False) -> dict[str, Any]:
        """Pull latest files from the Git repository.

        Unpublished changes to System-owned files (params, calibration notes) are
        published first. Edited shared files stop the pull with 409 unless ``force``.

        Returns
        -------
        dict[str, Any]
            Pull operation result.

        """
        repository = self._repository()
        self._require_github_mode(repository)
        try:
            result = repository.sync(force=force)
        except DirtySharedFiles as e:
            raise HTTPException(
                status_code=409,
                detail=f"{e!s}. Open a pull request with them or discard them with force.",
            )
        except ConfigRepositoryError as e:
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            logger.error(f"Error pulling from Git: {e}")
            raise HTTPException(status_code=500, detail=f"Error pulling from Git: {e!s}")
        status = repository.status()
        logger.info(f"Updated to commit: {result.commit} - {status.head_message}")
        self._run_hook(self._after_pull, "pull")
        return {
            "success": True,
            "commit": result.commit,
            "commit_message": status.head_message,
            "published": result.published,
            "message": f"{self._label.capitalize()} files updated successfully",
        }

    def git_push_config(self, commit_message: str) -> dict[str, Any]:
        """Open a pull request holding the workspace's changed files.

        Parameters
        ----------
        commit_message : str
            Commit message and pull request title.

        Returns
        -------
        dict[str, Any]
            Push operation result.

        """
        repository = self._repository()
        self._require_github_mode(repository)
        status = repository.status()
        changed = [path for path in status.dirty_paths if path not in self._push_exclude]
        if not changed:
            logger.info("No changes to commit")
            return {"success": True, "message": "No changes to commit", "commit": None}
        try:
            result = repository.propose(changed, commit_message, commit_message)
        except ConfigRepositoryError as e:
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            logger.error(f"Error pushing to Git: {e}")
            raise HTTPException(status_code=500, detail=f"Error pushing to Git: {e!s}")
        if not result.changed:
            return {"success": True, "message": "No changes to commit", "commit": None}
        logger.info(f"Pull request created: {result.pr_url}")
        return {
            "success": True,
            "commit": result.commit,
            "commit_message": commit_message,
            "message": "Pull request created successfully",
            "pr_url": result.pr_url,
            "pr_number": result.pr_number,
            "branch": result.branch,
            "files": result.paths,
        }

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
