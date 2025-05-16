import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from git import Repo
from git.exc import GitCommandError
from prefect import flow, get_run_logger


@flow(flow_run_name="Update Config")
def update_config(target_dir: str | Path = "/app/config") -> str:
    """Update configuration files from the remote repository.

    Args:
    ----
        target_dir: The directory where configuration files will be updated.
                   Defaults to "config" in the current working directory.

    Raises:
    ------
        RuntimeError: If required environment variables are missing or if there are
                     issues with cloning/updating the repository.

    """
    target_dir = Path(target_dir)
    temp_dir = None
    logger = get_run_logger()

    try:
        # Get authentication details from environment
        github_user = os.getenv("GITHUB_USER")
        github_token = os.getenv("GITHUB_TOKEN")
        repo_url = os.getenv("CONFIG_REPO_URL")

        if not all([github_user, github_token]):
            raise RuntimeError("Missing required environment variables: GITHUB_USER, GITHUB_TOKEN")

        # Parse and reconstruct URL with authentication
        parsed = urlparse(repo_url)
        auth_netloc = f"{github_user}:{github_token}@{parsed.netloc}"
        auth_url = urlunparse((parsed.scheme, auth_netloc, parsed.path, "", "", ""))

        # Create temporary directory and clone repository
        temp_dir = tempfile.mkdtemp()
        logger.info("Cloning repository to temporary directory")
        repo = Repo.clone_from(auth_url, temp_dir)

        # Create backup of current config if it exists
        if target_dir.exists():
            backup_dir = (
                target_dir.parent
                / f"config_backup_{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            )
            shutil.copytree(target_dir, backup_dir)
            logger.info(f"Created backup at: {backup_dir}")

        # Get latest changes
        logger.info("Fetching latest changes")
        repo.remotes.origin.fetch()
        repo.git.reset("--hard", "origin/main")

        # Create target directory if it doesn't exist
        target_dir.mkdir(parents=True, exist_ok=True)

        # Copy files
        config_source = Path(temp_dir)
        for item in config_source.glob("*"):
            if item.name == ".git":
                continue

            destination = target_dir / item.name
            if item.is_file():
                shutil.copy2(item, destination)
            else:
                shutil.copytree(item, destination, dirs_exist_ok=True)

        # Log success with commit information
        current = repo.head.commit
        logger.info(f"Updated to commit: {current.hexsha[:8]} - {current.message.strip()}")
        logger.info(f"Config files updated successfully in: {target_dir}")

    except GitCommandError as e:
        # Mask credentials in error message
        error_msg = str(e.stderr)
        parsed = urlparse(repo_url)
        masked_url = urlunparse(
            (parsed.scheme, parsed.netloc.split("@")[-1], parsed.path, "", "", "")
        )
        raise RuntimeError(f"Git operation failed for {masked_url}: {error_msg}")

    except Exception as e:
        raise RuntimeError(f"Failed to update config: {e!s}")

    finally:
        if temp_dir and Path(temp_dir).exists():
            shutil.rmtree(temp_dir)

        return current.hexsha[:8] if current else None
