import logging
import os
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError
from prefect import get_run_logger, task
from qdash.common.datetime_utils import now_iso
from qdash.common.paths import QUBEX_CONFIG_BASE


def _sync_local_repo(branch: str, logger: logging.Logger) -> None:
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


# Default source path for calib_note.json (example chip: 64Qv1)
DEFAULT_CALIB_NOTE_PATH = str(QUBEX_CONFIG_BASE / "64Qv1" / "calibration" / "calib_note.json")


@task(task_run_name="Push GitHub")
def push_github(
    source_path: str = DEFAULT_CALIB_NOTE_PATH,
    repo_subpath: str = "64Qv1/calibration/calib_note.json",
    commit_message: str = "Update calib_note.json",
    branch: str = "main",
) -> str:
    """Push local calib_note.json to the GitHub repository.

    Args:
    ----
        source_path: Local path to the updated calib_note.json
        repo_subpath: Relative path inside the repo to replace
        commit_message: Commit message
        branch: Branch to push to

    Returns:
    -------
        str: Commit SHA

    """
    temp_dir = None

    try:
        logger = get_run_logger()
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
        auth_url = urlunparse((scheme, auth_netloc, path, "", "", ""))

        # Clone repository (shallow clone for efficiency)
        temp_dir = tempfile.mkdtemp()

        repo = Repo.clone_from(auth_url, temp_dir, branch=branch, depth=1)

        # Replace file
        target_file_path = Path(temp_dir) / repo_subpath
        target_file_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_file_path)

        # Git operations
        repo.index.add([str(target_file_path.relative_to(temp_dir))])
        # Skip if no changes
        diff = repo.index.diff("HEAD")
        if not diff:
            logger.info("No changes to commit")
            return "No changes to commit"
        now_jst = now_iso()
        repo.git.config("user.name", "github-actions[bot]")
        repo.git.config("user.email", "github-actions[bot]@users.noreply.github.com")
        repo.index.commit(f"{commit_message} at {now_jst}")

        repo.remotes.origin.push()

        commit_sha = str(repo.head.commit.hexsha[:8])
        _sync_local_repo(branch, logger)
        return commit_sha

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
) -> str:
    """Push multiple files to GitHub repository in a single commit.

    Args:
    ----
        files: List of (source_path, repo_subpath) tuples
        commit_message: Commit message
        branch: Branch to push to

    Returns:
    -------
        str: Commit SHA or "No changes to commit"

    """
    temp_dir = None

    try:
        logger = get_run_logger()
        github_user = os.getenv("GITHUB_USER")
        github_token = os.getenv("GITHUB_TOKEN")
        repo_url = os.getenv("CONFIG_REPO_URL")

        if not all([github_user, github_token, repo_url]):
            raise RuntimeError("Missing required environment variables")

        parsed = urlparse(repo_url)
        scheme = str(parsed.scheme)
        netloc = str(parsed.netloc)
        path = str(parsed.path)
        auth_netloc = f"{github_user}:{github_token}@{netloc}"
        auth_url = urlunparse((scheme, auth_netloc, path, "", "", ""))

        # Clone repository once (shallow clone for efficiency)
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

        # Check for changes
        diff = repo.index.diff("HEAD")
        if not diff:
            logger.info("No changes to commit")
            return "No changes to commit"

        now_jst = now_iso()
        repo.git.config("user.name", "github-actions[bot]")
        repo.git.config("user.email", "github-actions[bot]@users.noreply.github.com")
        repo.index.commit(f"{commit_message} at {now_jst}")

        repo.remotes.origin.push()

        logger.info(f"Pushed {len(added_files)} files in single commit")
        commit_sha = str(repo.head.commit.hexsha[:8])
        _sync_local_repo(branch, logger)
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
