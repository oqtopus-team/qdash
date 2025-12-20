"""Path resolution for workflow components.

This module provides centralized path management for workflow-related
directories and files.

Container-side paths are defined as constants. Host-side paths should be
configured via .env and docker-compose.yaml volume mounts.

"""

from __future__ import annotations

from pathlib import Path

# =============================================================================
# Container-side path constants
# =============================================================================
# These paths are fixed inside the container. To customize where data is stored
# on the host, configure volume mounts in docker-compose.yaml and .env.
#
# Example .env:
#   CALIB_DATA_PATH=./my-custom-path/calib_data
#
# Example docker-compose.yaml:
#   volumes:
#     - ${CALIB_DATA_PATH}:/app/calib_data

CALIB_DATA_BASE = Path("/app/calib_data")
"""Base directory for calibration data storage."""

WORKFLOW_DIR = Path("/app/qdash/workflow")
"""Working directory for Prefect deployments."""


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
