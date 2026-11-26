from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse, urlunparse

from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError
from prefect import get_run_logger, task

from qdash.common.config.paths import QUBEX_CONFIG_BASE
from qdash.common.utils.commit_message import format_machine_commit_message
from qdash.common.utils.datetime import now_iso

if TYPE_CHECKING:
    import logging


def _sync_local_repo(
    branch: str, logger: logging.Logger | logging.LoggerAdapter[logging.Logger]
) -> None:
    """Sync the local qubex-config git repository to match the remote after push.

    This resets the local .git state so that ``git status`` shows clean
    after parameters have been pushed to the remote.

    Note: This intentionally uses ``git reset --hard`` because the local
    working tree changes have already been pushed to the remote via a
    temporary clone.  The reset simply brings the local .git state in line
    with what was just pushed.
    """
    local_repo_path = QUBEX_CONFIG_BASE
    git_dir = local_repo_path / ".git"
    if not git_dir.exists():
        return

    try:
        repo = Repo(str(local_repo_path))
        repo.remotes.origin.fetch()
        repo.git.reset("--hard", f"origin/{branch}")
        logger.info(f"Synced local qubex-config repo to origin/{branch}")
    except (GitCommandError, InvalidGitRepositoryError) as e:
        logger.warning(f"Failed to sync local qubex-config repo: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during local repo sync: {e}")


NO_CHANGES = "No changes to commit"


def _authenticated_repo_url() -> str:
    """Build the config repository URL with GitHub credentials from the environment."""
    github_user = os.getenv("GITHUB_USER")
    github_token = os.getenv("GITHUB_TOKEN")
    repo_url = os.getenv("CONFIG_REPO_URL")

    if not all([github_user, github_token, repo_url]):
        raise RuntimeError("Missing required environment variables")

    parsed = urlparse(repo_url)
    # Ensure all URL components are strings
    scheme = str(parsed.scheme)
    netloc = str(parsed.netloc)
    path = str(parsed.path)
    auth_netloc = f"{github_user}:{github_token}@{netloc}"
    return str(urlunparse((scheme, auth_netloc, path, "", "", "")))


def _commit_and_push(
    repo: Repo,
    commit_message: str,
    branch: str,
    sync_local: bool,
    logger: logging.Logger | logging.LoggerAdapter[logging.Logger],
) -> str:
    """Commit the staged files as the bot, push, and return the short commit SHA.

    Returns ``NO_CHANGES`` without committing when the index matches ``HEAD``.
    The local qubex-config repository is synced only after a successful push.
    """
    if not repo.index.diff("HEAD"):
        logger.info(NO_CHANGES)
        return NO_CHANGES
    repo.git.config("user.name", "github-actions[bot]")
    repo.git.config("user.email", "github-actions[bot]@users.noreply.github.com")
    repo.index.commit(format_machine_commit_message(commit_message, now_iso()))

    repo.remotes.origin.push()

    commit_sha = str(repo.head.commit.hexsha[:8])
    if sync_local:
        _sync_local_repo(branch, logger)
    return commit_sha


# Default source path for calib_note.json (example chip: 64Qv1)
DEFAULT_CALIB_NOTE_PATH = str(QUBEX_CONFIG_BASE / "64Qv1" / "calibration" / "calib_note.json")


@task(task_run_name="Push GitHub")
def push_github(
    source_path: str = DEFAULT_CALIB_NOTE_PATH,
    repo_subpath: str = "64Qv1/calibration/calib_note.json",
    commit_message: str = "Update calib_note.json",
    branch: str = "main",
    sync_local: bool = True,
) -> str:
    """Push local calib_note.json to the GitHub repository.

    Args:
    ----
        source_path: Local path to the updated calib_note.json
        repo_subpath: Relative path inside the repo to replace
        commit_message: Commit message
        branch: Branch to push to
        sync_local: Whether to sync the local qubex-config repo after a successful push

    Returns:
    -------
        str: Commit SHA

    """
    temp_dir = None

    try:
        logger = get_run_logger()
        auth_url = _authenticated_repo_url()

        # Clone repository (shallow clone for efficiency)
        temp_dir = tempfile.mkdtemp()
        repo = Repo.clone_from(auth_url, temp_dir, branch=branch, depth=1)

        # Replace file
        target_file_path = Path(temp_dir) / repo_subpath
        target_file_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_file_path)

        # Git operations
        repo.index.add([str(target_file_path.relative_to(temp_dir))])
        return _commit_and_push(repo, commit_message, branch, sync_local, logger)

    except GitCommandError as e:
        raise RuntimeError(f"Git push failed: {e.stderr}")

    except Exception as e:
        raise RuntimeError(f"Push failed: {e!s}")

    finally:
        if temp_dir and Path(temp_dir).exists():
            shutil.rmtree(temp_dir)


@task(task_run_name="Push GitHub Batch")
def push_github_batch(
    files: list[tuple[str, str]],
    commit_message: str = "Update files",
    branch: str = "main",
    sync_local: bool = True,
) -> str:
    """Push multiple files to GitHub repository in a single commit.

    Args:
    ----
        files: List of (source_path, repo_subpath) tuples
        commit_message: Commit message
        branch: Branch to push to
        sync_local: Whether to sync the local qubex-config repo after a successful push

    Returns:
    -------
        str: Commit SHA or "No changes to commit"

    """
    temp_dir = None

    try:
        logger = get_run_logger()
        auth_url = _authenticated_repo_url()

        # Clone repository (shallow clone for efficiency)
        temp_dir = tempfile.mkdtemp()
        repo = Repo.clone_from(auth_url, temp_dir, branch=branch, depth=1)

        # Copy all files
        added_files = []
        for source_path, repo_subpath in files:
            if not Path(source_path).exists():
                logger.warning(f"Source file not found, skipping: {source_path}")
                continue

            target_file_path = Path(temp_dir) / repo_subpath
            target_file_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_file_path)
            added_files.append(str(target_file_path.relative_to(temp_dir)))

        if not added_files:
            logger.info("No files to commit")
            return "No files to commit"

        # Git operations - add all files
        repo.index.add(added_files)

        commit_sha = _commit_and_push(repo, commit_message, branch, sync_local, logger)
        if commit_sha != NO_CHANGES:
            logger.info(f"Pushed {len(added_files)} files in single commit")
        return commit_sha

    except GitCommandError as e:
        raise RuntimeError(f"Git push failed: {e.stderr}")

    except Exception as e:
        raise RuntimeError(f"Push failed: {e!s}")

    finally:
        if temp_dir and Path(temp_dir).exists():
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    # Example usage
    push_github(
        source_path="/workspace/qdash/config/qubex/64Qv1/calibration/calib_note.json",
        repo_subpath="64Qv1/calibration/calib_note.json",
        commit_message="Update calib_note.json",
        branch="main",
    )
