"""GitHub integration for FlowSession - Pull/Push functionality.

This module provides GitHub integration for calibration workflows, allowing:
- Pull: Fetch latest configuration from GitHub repository
- Push: Upload calibration results (calib_note.json, props.yaml, etc.)

The implementation reuses existing push_props logic to maintain compatibility
with the established merge strategy for props.yaml files.
"""

import os
from enum import Enum
from pathlib import Path
from typing import Any

from prefect import get_run_logger
from pydantic import BaseModel, Field


class ConfigFileType(Enum):
    """Configuration file types that can be pushed to GitHub.

    Attributes:
        CALIB_NOTE: calibration/calib_note.json (simple copy)
        PROPS: params/props.yaml (uses ChipDocument merge logic)
        PARAMS: params/params.yaml (simple copy)
        ALL_PARAMS: All *.yaml files in params/ directory
    """

    CALIB_NOTE = "calib_note"
    PROPS = "props"
    PARAMS = "params"
    ALL_PARAMS = "all_params"


class GitHubPushConfig(BaseModel):
    """Configuration for GitHub push operations.

    Attributes:
        enabled: Whether to push to GitHub on finish_calibration()
        file_types: List of file types to push (default: [CALIB_NOTE])
        commit_message: Custom commit message (default: auto-generated)
        branch: Target branch (default: "main")
        props_within_24hrs: For PROPS type, only include data from last 24 hours

    Example:
        ```python
        config = GitHubPushConfig(
            enabled=True,
            file_types=[ConfigFileType.CALIB_NOTE, ConfigFileType.PROPS],
            commit_message="Update calibration results"
        )
        ```
    """

    enabled: bool = False
    file_types: list[ConfigFileType] = Field(default_factory=lambda: [ConfigFileType.CALIB_NOTE])
    commit_message: str | None = None
    branch: str = "main"
    props_within_24hrs: bool = False

    model_config = {"frozen": False}


class GitHubIntegration:
    """GitHub integration handler for calibration workflows.

    This class manages GitHub operations for FlowSession, including:
    - Pulling latest configuration from repository
    - Pushing calibration results with proper merge logic

    The implementation reuses existing infrastructure:
    - pull_github task for config synchronization
    - push_props flow for props.yaml merge logic
    - push_github task for file uploads

    Attributes:
        username: Username for the calibration session
        chip_id: Target chip ID
        execution_id: Unique execution identifier

    Example:
        ```python
        integration = GitHubIntegration("user", "64Qv3", "20250101-001")

        # Pull latest config
        commit_id = integration.pull_config()

        # Push results
        config = GitHubPushConfig(
            enabled=True,
            file_types=[ConfigFileType.CALIB_NOTE, ConfigFileType.PROPS]
        )
        results = integration.push_files(config)
        ```
    """

    def __init__(self, username: str, chip_id: str, execution_id: str) -> None:
        """Initialize GitHub integration.

        Args:
            username: Username for the calibration session
            chip_id: Target chip ID
            execution_id: Unique execution identifier
        """
        self.username = username
        self.chip_id = chip_id
        self.execution_id = execution_id
        self.logger = get_run_logger()

    @staticmethod
    def check_credentials() -> bool:
        """Check if required GitHub credentials are configured.

        Returns:
            True if all required environment variables are set

        Environment Variables:
            GITHUB_USER: GitHub username
            GITHUB_TOKEN: GitHub personal access token
            CONFIG_REPO_URL: Repository URL for configuration files
        """
        required = ["GITHUB_USER", "GITHUB_TOKEN", "CONFIG_REPO_URL"]
        return all(os.getenv(var) for var in required)

    def pull_config(self, target_dir: str = "/app/config/qubex") -> str | None:
        """Pull latest configuration from GitHub repository.

        This method uses the existing pull_github task to fetch the latest
        configuration files from the repository. A backup of the current
        configuration is automatically created.

        Args:
            target_dir: Directory where config files will be updated

        Returns:
            Commit SHA of the pulled configuration, or None if pull failed

        Example:
            ```python
            commit_id = integration.pull_config()
            if commit_id:
                print(f"Updated to commit: {commit_id}")
            ```
        """
        try:
            from qdash.workflow.worker.tasks.pull_github import pull_github

            commit_id = pull_github(target_dir=target_dir)
            self.logger.info(f"Pulled config from GitHub: {commit_id}")
            return commit_id
        except Exception as e:
            self.logger.warning(f"Failed to pull from GitHub: {e}")
            return None

    def push_files(self, push_config: GitHubPushConfig) -> dict[str, Any]:
        """Push calibration results to GitHub repository.

        This method handles different file types with appropriate strategies:
        - CALIB_NOTE: Direct copy of calib_note.json
        - PROPS: Uses ChipDocument extraction and merge logic (existing implementation)
        - PARAMS: Direct copy of params.yaml
        - ALL_PARAMS: Copy all *.yaml files from params/ directory

        Args:
            push_config: Configuration specifying which files to push

        Returns:
            Dictionary mapping file types to commit SHAs or error messages

        Example:
            ```python
            config = GitHubPushConfig(
                enabled=True,
                file_types=[ConfigFileType.CALIB_NOTE, ConfigFileType.PROPS]
            )
            results = integration.push_files(config)
            # {"calib_note": "abc123def", "props": "def456ghi"}
            ```
        """
        results: dict[str, Any] = {}

        for file_type in push_config.file_types:
            try:
                if file_type == ConfigFileType.CALIB_NOTE:
                    result = self._push_calib_note(push_config)
                elif file_type == ConfigFileType.PROPS:
                    result = self._push_props(push_config)
                elif file_type == ConfigFileType.PARAMS:
                    result = self._push_params_file(push_config)
                elif file_type == ConfigFileType.ALL_PARAMS:
                    result = self._push_all_params(push_config)

                results[file_type.value] = result
            except Exception as e:
                self.logger.error(f"Failed to push {file_type.value}: {e}")
                results[file_type.value] = f"Error: {e}"

        return results

    def _push_calib_note(self, config: GitHubPushConfig) -> str:
        """Push calib_note.json (fetch master note from MongoDB and write to config dir).

        This method:
        1. Fetches the master calibration note from MongoDB (task_id="master")
        2. Writes it to /app/config/qubex/{chip_id}/calibration/calib_note.json
        3. Pushes to GitHub

        Args:
            config: Push configuration

        Returns:
            Commit SHA

        Raises:
            FileNotFoundError: If no master calibration note exists in MongoDB
        """
        import json

        from qdash.dbmodel.calibration_note import CalibrationNoteDocument
        from qdash.workflow.worker.tasks.push_github import push_github

        # 1. Fetch master note from MongoDB
        latest = (
            CalibrationNoteDocument.find(
                {"username": self.username, "task_id": "master", "chip_id": self.chip_id}
            )
            .sort([("timestamp", -1)])  # Sort by timestamp descending
            .limit(1)
            .run()
        )

        if not latest:
            msg = f"No master calibration note found in MongoDB for user {self.username}"
            raise FileNotFoundError(msg)

        master_note = latest[0].note

        # 2. Write to /app/config/qubex/{chip_id}/calibration/calib_note.json
        calib_note_dir = f"/app/config/qubex/{self.chip_id}/calibration"
        Path(calib_note_dir).mkdir(parents=True, exist_ok=True)

        source_path = f"{calib_note_dir}/calib_note.json"
        with Path(source_path).open("w", encoding="utf-8") as f:
            json.dump(master_note, f, indent=4, ensure_ascii=False, sort_keys=True)

        self.logger.info(f"Wrote master note to {source_path}")

        # 3. Push to GitHub
        repo_subpath = f"{self.chip_id}/calibration/calib_note.json"
        commit_message = (
            config.commit_message or f"Update calib_note.json from execution {self.execution_id}"
        )

        commit_sha = push_github(
            source_path=source_path,
            repo_subpath=repo_subpath,
            commit_message=commit_message,
            branch=config.branch,
        )

        self.logger.info(f"Pushed calib_note.json: {commit_sha}")
        return str(commit_sha)

    def _push_props(self, config: GitHubPushConfig) -> str:
        """Push props.yaml using existing merge logic.

        This method reuses the existing push_props implementation which:
        1. Extracts chip properties from ChipDocument
        2. Merges with existing props.yaml using ruamel.yaml (preserves comments)
        3. Applies proper formatting (scientific notation, fidelity checks)
        4. Pushes to GitHub

        Args:
            config: Push configuration

        Returns:
            Commit SHA
        """
        from qdash.workflow.worker.flows.push_props.create_props import create_chip_properties
        from qdash.workflow.worker.tasks.push_github import push_github

        source_path = f"/app/config/qubex/{self.chip_id}/params/props.yaml"
        repo_subpath = f"{self.chip_id}/params/props.yaml"

        # Use existing implementation to generate/merge props.yaml from ChipDocument
        create_chip_properties(
            username=self.username,
            source_path=source_path,
            target_path=source_path,
            chip_id=self.chip_id,
        )

        commit_message = (
            config.commit_message or f"Update props.yaml from execution {self.execution_id}"
        )

        commit_sha = push_github(
            source_path=source_path,
            repo_subpath=repo_subpath,
            commit_message=commit_message,
            branch=config.branch,
        )

        self.logger.info(f"Pushed props.yaml: {commit_sha}")
        return str(commit_sha)

    def _push_params_file(self, config: GitHubPushConfig) -> str:
        """Push params.yaml (simple copy).

        Args:
            config: Push configuration

        Returns:
            Commit SHA

        Raises:
            FileNotFoundError: If params.yaml does not exist
        """
        from qdash.workflow.worker.tasks.push_github import push_github

        source_path = f"/app/config/qubex/{self.chip_id}/params/params.yaml"
        repo_subpath = f"{self.chip_id}/params/params.yaml"

        if not Path(source_path).exists():
            msg = f"params.yaml not found: {source_path}"
            raise FileNotFoundError(msg)

        commit_message = (
            config.commit_message or f"Update params.yaml from execution {self.execution_id}"
        )

        commit_sha = push_github(
            source_path=source_path,
            repo_subpath=repo_subpath,
            commit_message=commit_message,
            branch=config.branch,
        )

        self.logger.info(f"Pushed params.yaml: {commit_sha}")
        return str(commit_sha)

    def _push_all_params(self, config: GitHubPushConfig) -> dict[str, str]:
        """Push all yaml files in params directory in a single commit.

        Args:
            config: Push configuration

        Returns:
            Dictionary with commit SHA and list of pushed files
        """
        from qdash.workflow.worker.tasks.push_github import push_github_batch

        params_dir = Path(f"/app/config/qubex/{self.chip_id}/params")

        if not params_dir.exists():
            self.logger.warning(f"Params directory not found: {params_dir}")
            return {"error": f"Directory not found: {params_dir}"}

        # Collect all yaml files
        files: list[tuple[str, str]] = []
        for yaml_file in params_dir.glob("*.yaml"):
            source_path = str(yaml_file)
            repo_subpath = f"{self.chip_id}/params/{yaml_file.name}"
            files.append((source_path, repo_subpath))

        if not files:
            self.logger.info("No yaml files found in params directory")
            return {"status": "No files to push"}

        # Push all files in single commit
        commit_message = (
            config.commit_message or f"Update params from execution {self.execution_id}"
        )

        try:
            commit_sha = push_github_batch(
                files=files,
                commit_message=commit_message,
                branch=config.branch,
            )
            file_names = [Path(f[0]).name for f in files]
            self.logger.info(f"Pushed {len(files)} param files in single commit: {commit_sha}")
            return {"commit": str(commit_sha), "files": file_names}
        except Exception as e:
            self.logger.error(f"Failed to push params: {e}")
            return {"error": str(e)}
