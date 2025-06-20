import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urlunparse

import requests
from git import Repo
from git.exc import GitCommandError
from prefect import flow, get_run_logger
from prefect.logging import get_run_logger
from qdash.config import get_settings
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.initialize import initialize
from qdash.workflow.utils.slack import SlackContents, Status
from qdash.workflow.worker.chip_info.flow import (
    get_chip_properties,
    merge_properties,
    read_base_properties,
    write_yaml,
)


@flow(name="update-props-pr", log_prints=True)
def update_props_pr(username: str = "admin") -> None:
    """Update props.yaml and create a PR.

    This flow performs the following steps:
    1. Clones the configuration repository
    2. Gets current chip properties from database
    3. Merges with base properties from props.yaml
    4. Creates a new branch and commits changes
    5. Creates a pull request
    6. Sends a Slack notification

    Args:
    ----
        username: The username to get the current chip for. Defaults to "admin".

    Raises:
    ------
        RuntimeError: If required environment variables are missing or if there are
                     issues with Git operations.

    """
    logger = get_run_logger()
    temp_dir: str | None = None

    try:
        # Get authentication details from environment
        github_user = os.getenv("GITHUB_USER")
        github_token = os.getenv("GITHUB_TOKEN")
        repo_url = os.getenv("CONFIG_REPO_URL")

        if not all([github_user, github_token, repo_url]):
            raise RuntimeError(
                "Missing required environment variables: GITHUB_USER, GITHUB_TOKEN, CONFIG_REPO_URL"
            )

        # Parse and reconstruct URL with authentication
        parsed = urlparse(repo_url)
        # Convert URL components to str to handle potential bytes
        scheme = str(parsed.scheme) if parsed.scheme else "https"
        netloc = str(parsed.netloc) if parsed.netloc else ""
        path = str(parsed.path) if parsed.path else ""
        auth_netloc = f"{github_user}:{github_token}@{netloc}"
        auth_url = urlunparse((scheme, auth_netloc, path, "", "", ""))

        # Create temporary directory and clone repository
        temp_dir = tempfile.mkdtemp()
        logger.info("Cloning repository to temporary directory")
        repo = Repo.clone_from(str(auth_url), temp_dir)

        # Initialize database connection
        initialize()

        # Get current chip
        logger.info(f"Getting current chip for user: {username}")
        chip = ChipDocument.get_current_chip(username=username)
        if not chip:
            raise RuntimeError(f"No current chip found for user: {username}")

        # Convert properties
        logger.info("Converting chip properties")
        chip_props = get_chip_properties(chip)

        # Read base properties from cloned repo
        logger.info("Reading base properties from props.yaml")
        props_path = f"{temp_dir}/props.yaml"
        base_props = read_base_properties(filename=props_path)

        # Merge properties
        logger.info("Merging properties")
        merged_props = merge_properties(base_props, chip_props)

        # Create new branch
        current_time = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        branch_name = f"update-props-{current_time}"
        logger.info(f"Creating new branch: {branch_name}")
        repo.git.checkout("-b", branch_name)

        # Write updated props.yaml to repo
        logger.info("Writing updated props.yaml")
        write_yaml(merged_props, filename=props_path)

        # Stage and commit changes
        logger.info("Committing changes")
        repo.index.add("props.yaml")
        repo.index.commit("feat: update props.yaml with latest calibration data")

        # Push changes
        logger.info(f"Pushing changes to branch: {branch_name}")
        repo.git.push("origin", branch_name)

        # Create PR using GitHub REST API
        logger.info("Creating pull request")
        # Remove .git suffix and leading slash from repo path for API URL
        repo_path = str(parsed.path).lstrip("/").replace(".git", "") if parsed.path else ""
        api_url = f"https://api.github.com/repos/{repo_path}/pulls"
        logger.info(f"Using GitHub API URL: {api_url}")
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {github_token}",
        }
        data = {
            "title": "feat: update props.yaml with latest calibration data",
            "body": "Update props.yaml with latest calibration data from the current chip.",
            "head": branch_name,
            "base": "main",
        }
        response = requests.post(api_url, headers=headers, json=data)
        try:
            response.raise_for_status()
            pr_data = response.json()
        except requests.exceptions.HTTPError as e:
            error_details = response.json() if response.text else "No error details available"
            logger.error(f"GitHub API error response: {error_details}")
            raise RuntimeError(f"GitHub API error: {e!s}. Details: {error_details}")

        # Log success
        commit = repo.head.commit
        logger.info(f"Changes pushed to branch {branch_name}")
        logger.info(f"Commit: {commit.hexsha[:8]} - {str(commit.message).strip()}")
        logger.info(f"PR created: {pr_data['html_url']}")

        # Send Slack notification
        settings = get_settings()
        slack = SlackContents(
            status=Status.SUCCESS,
            title="props.yaml PR",
            msg=f"Created PR for props.yaml update: {pr_data['html_url']}",
            ts="",
            path=props_path,
            header=f"branch: {branch_name}\ncommit: {commit.hexsha[:8]}",
            channel=settings.slack_channel_id,
            token=settings.slack_bot_token,
        )
        slack.send_slack()

    except GitCommandError as e:
        # Mask credentials in error message
        error_msg = str(e.stderr)
        if repo_url:
            parsed = urlparse(repo_url)
            # Convert URL components to str
            scheme = str(parsed.scheme) if parsed.scheme else "https"
            netloc = str(parsed.netloc).split("@")[-1] if parsed.netloc else ""
            path = str(parsed.path) if parsed.path else ""
            masked_url = urlunparse((scheme, netloc, path, "", "", ""))
        else:
            masked_url = "unknown repository URL"
        logger.error(f"Git operation failed for {masked_url}")
        raise RuntimeError(f"Git operation failed for {masked_url}: {error_msg}")

    except Exception as e:
        logger.error(f"Failed to update props and create PR: {e!s}")
        raise RuntimeError(f"Failed to update props and create PR: {e!s}")

    finally:
        # Clean up temporary directory
        if temp_dir and Path(temp_dir).exists():
            logger.info("Cleaning up temporary directory")
            shutil.rmtree(temp_dir)
