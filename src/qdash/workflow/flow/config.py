"""FlowSession configuration value objects.

This module provides immutable configuration objects for FlowSession,
supporting dependency injection and testability.
"""

from typing import Any

from pydantic import BaseModel, Field, field_validator
from qdash.workflow.flow.github import GitHubPushConfig


class FlowSessionConfig(BaseModel):
    """Immutable configuration for FlowSession.

    This value object encapsulates all initialization parameters for a
    FlowSession, enabling cleaner dependency injection and testability.

    Attributes:
        username: Username for the calibration session
        chip_id: Target chip ID
        qids: List of qubit IDs to calibrate (required for qubex initialization)
        execution_id: Unique execution identifier (e.g., "20240101-001").
            If None, auto-generates using current date and counter.
        backend_name: Backend type, either 'qubex' or 'fake' (default: 'qubex')
        name: Human-readable name for the execution (default: 'Python Flow Execution')
        tags: List of tags for categorization (default: uses name as tag)
        use_lock: Whether to use ExecutionLock to prevent concurrent calibrations (default: True)
        note: Additional notes to store with execution (default: {})
        enable_github_pull: Whether to pull latest config from GitHub before starting (default: False)
        github_push_config: Configuration for GitHub push operations (default: disabled)
        muxes: List of MUX IDs for system-level tasks like CheckSkew (default: None)

    Example:
        ```python
        config = FlowSessionConfig(
            username="alice",
            chip_id="chip_1",
            qids=["0", "1", "2"],
            backend_name="qubex",
            name="My Calibration",
            tags=["production", "daily"],
        )
        session = FlowSession.from_config(config)
        ```
    """

    model_config = {"frozen": True}

    username: str
    chip_id: str
    qids: tuple[str, ...]  # Use tuple for immutability
    execution_id: str | None = None
    backend_name: str = "qubex"
    name: str = "Python Flow Execution"
    tags: tuple[str, ...] | None = None  # Use tuple for immutability
    use_lock: bool = True
    note: dict[str, Any] | None = Field(default=None)
    enable_github_pull: bool = False
    github_push_config: GitHubPushConfig | None = None
    muxes: tuple[int, ...] | None = None  # Use tuple for immutability

    @field_validator("username", "chip_id")
    @classmethod
    def not_empty_string(cls, v: str) -> str:
        """Validate that string fields are not empty."""
        if not v:
            raise ValueError("cannot be empty")
        return v

    @field_validator("qids")
    @classmethod
    def qids_not_empty(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        """Validate that qids is not empty."""
        if not v:
            raise ValueError("qids cannot be empty")
        return v

    @classmethod
    def create(
        cls,
        username: str,
        chip_id: str,
        qids: list[str],
        execution_id: str | None = None,
        backend_name: str = "qubex",
        name: str = "Python Flow Execution",
        tags: list[str] | None = None,
        use_lock: bool = True,
        note: dict[str, Any] | None = None,
        enable_github_pull: bool = False,
        github_push_config: GitHubPushConfig | None = None,
        muxes: list[int] | None = None,
    ) -> "FlowSessionConfig":
        """Create a FlowSessionConfig from list parameters.

        This factory method converts mutable lists to immutable tuples
        for proper value object semantics.

        Args:
            username: Username for the calibration session
            chip_id: Target chip ID
            qids: List of qubit IDs to calibrate
            execution_id: Unique execution identifier (auto-generated if None)
            backend_name: Backend type ('qubex' or 'fake')
            name: Human-readable name for the execution
            tags: List of tags for categorization
            use_lock: Whether to use ExecutionLock
            note: Additional notes to store
            enable_github_pull: Whether to pull from GitHub
            github_push_config: GitHub push configuration
            muxes: List of MUX IDs

        Returns:
            Immutable FlowSessionConfig instance
        """
        return cls(
            username=username,
            chip_id=chip_id,
            qids=tuple(qids),
            execution_id=execution_id,
            backend_name=backend_name,
            name=name,
            tags=tuple(tags) if tags else None,
            use_lock=use_lock,
            note=note,
            enable_github_pull=enable_github_pull,
            github_push_config=github_push_config,
            muxes=tuple(muxes) if muxes else None,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for backward compatibility.

        Returns:
            Dictionary representation suitable for FlowSession.__init__
        """
        return {
            "username": self.username,
            "chip_id": self.chip_id,
            "qids": list(self.qids),
            "execution_id": self.execution_id,
            "backend_name": self.backend_name,
            "name": self.name,
            "tags": list(self.tags) if self.tags else None,
            "use_lock": self.use_lock,
            "note": dict(self.note) if self.note else None,
            "enable_github_pull": self.enable_github_pull,
            "github_push_config": self.github_push_config,
            "muxes": list(self.muxes) if self.muxes else None,
        }

    def with_execution_id(self, execution_id: str) -> "FlowSessionConfig":
        """Create a new config with the specified execution_id.

        Args:
            execution_id: The execution ID to set

        Returns:
            New FlowSessionConfig with updated execution_id
        """
        return FlowSessionConfig(
            username=self.username,
            chip_id=self.chip_id,
            qids=self.qids,
            execution_id=execution_id,
            backend_name=self.backend_name,
            name=self.name,
            tags=self.tags,
            use_lock=self.use_lock,
            note=self.note,
            enable_github_pull=self.enable_github_pull,
            github_push_config=self.github_push_config,
            muxes=self.muxes,
        )

    def with_note_update(self, key: str, value: Any) -> "FlowSessionConfig":
        """Create a new config with an updated note entry.

        Args:
            key: Note key to update
            value: Note value to set

        Returns:
            New FlowSessionConfig with updated note
        """
        new_note = dict(self.note) if self.note else {}
        new_note[key] = value
        return FlowSessionConfig(
            username=self.username,
            chip_id=self.chip_id,
            qids=self.qids,
            execution_id=self.execution_id,
            backend_name=self.backend_name,
            name=self.name,
            tags=self.tags,
            use_lock=self.use_lock,
            note=new_note,
            enable_github_pull=self.enable_github_pull,
            github_push_config=self.github_push_config,
            muxes=self.muxes,
        )


class CalibrationPaths(BaseModel):
    """Immutable paths for calibration data storage.

    This value object encapsulates all path-related configuration
    derived from username and execution_id.

    Attributes:
        user_path: Base path for user data (/app/calib_data/{username})
        classifier_dir: Path for classifier data
        calib_data_path: Path for calibration data
        task_path: Path for task outputs
        fig_path: Path for figures
        calib_path: Path for calibration files
        calib_note_path: Path for calibration notes
    """

    model_config = {"frozen": True}

    user_path: str
    classifier_dir: str
    calib_data_path: str
    task_path: str
    fig_path: str
    calib_path: str
    calib_note_path: str

    @classmethod
    def from_config(cls, username: str, execution_id: str) -> "CalibrationPaths":
        """Create paths from username and execution_id.

        Args:
            username: Username for the session
            execution_id: Execution ID (format: YYYYMMDD-NNN)

        Returns:
            CalibrationPaths with all paths configured
        """
        date_str, index = execution_id.split("-")
        user_path = f"/app/calib_data/{username}"
        calib_data_path = f"{user_path}/{date_str}/{index}"

        return cls(
            user_path=user_path,
            classifier_dir=f"{user_path}/.classifier",
            calib_data_path=calib_data_path,
            task_path=f"{calib_data_path}/task",
            fig_path=f"{calib_data_path}/fig",
            calib_path=f"{calib_data_path}/calib",
            calib_note_path=f"{calib_data_path}/calib_note",
        )
