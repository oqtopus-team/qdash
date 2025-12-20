"""Path resolution for workflow components.

This module provides path management for workflow-related directories and files.
Path constants are imported from qdash.common.paths for consistency across
API and workflow modules.

For host-side path customization, use .env and docker-compose.yaml volume mounts.
"""

from __future__ import annotations

from pathlib import Path

# Re-export path constants from common module for backward compatibility
from qdash.common.paths import (
    CALIB_DATA_BASE,
    CALIBTASKS_DIR,
    SERVICE_DIR,
    TEMPLATES_DIR,
    USER_FLOWS_DIR,
    WORKFLOW_DIR,
)


class PathResolver:
    """Resolves paths for workflow infrastructure.

    This class provides methods to generate paths for user-specific
    calibration data, execution directories, and other workflow-related
    locations.

    Examples
    --------
    >>> resolver = PathResolver()
    >>> resolver.user_data_dir("alice")
    PosixPath('/app/calib_data/alice')

    >>> resolver.execution_data_dir("alice", "20240101", "001")
    PosixPath('/app/calib_data/alice/20240101/001')

    """

    def __init__(
        self,
        calib_data_base: Path | None = None,
        workflow_dir: Path | None = None,
    ) -> None:
        self._calib_data_base = calib_data_base or CALIB_DATA_BASE
        self._workflow_dir = workflow_dir or WORKFLOW_DIR

    @property
    def calib_data_base(self) -> Path:
        """Base directory for calibration data."""
        return self._calib_data_base

    @property
    def workflow_dir(self) -> Path:
        """Working directory for Prefect deployments."""
        return self._workflow_dir

    # -------------------------------------------------------------------------
    # User-specific paths
    # -------------------------------------------------------------------------

    def user_data_dir(self, username: str) -> Path:
        """Get the base directory for a user's calibration data."""
        return self._calib_data_base / username

    def classifier_dir(self, username: str) -> Path:
        """Get the classifier directory for a user."""
        return self.user_data_dir(username) / ".classifier"

    def execution_data_dir(self, username: str, date_str: str, index: str) -> Path:
        """Get the directory for a specific execution's data."""
        return self.user_data_dir(username) / date_str / index


# Default resolver instance
_default_resolver: PathResolver | None = None


def get_path_resolver() -> PathResolver:
    """Get the default PathResolver instance."""
    global _default_resolver
    if _default_resolver is None:
        _default_resolver = PathResolver()
    return _default_resolver


def reset_path_resolver() -> None:
    """Reset the cached PathResolver instance."""
    global _default_resolver
    _default_resolver = None
