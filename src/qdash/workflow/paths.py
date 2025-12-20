"""Path resolution for workflow components.

This module provides centralized path management for workflow-related
directories and files, replacing hardcoded paths throughout the codebase.

Environment Variables
---------------------
QDASH_CALIB_DATA_BASE : str
    Base directory for calibration data storage.
    Default: /app/calib_data

QDASH_WORKFLOW_DIR : str
    Working directory for Prefect deployments.
    Default: /app/qdash/workflow

"""

from __future__ import annotations

import os
from pathlib import Path


class PathResolver:
    """Resolves paths for workflow infrastructure.

    This class provides methods to generate paths for user-specific
    calibration data, execution directories, and other workflow-related
    locations.

    Parameters
    ----------
    calib_data_base : str | None
        Base directory for calibration data. If None, uses
        QDASH_CALIB_DATA_BASE environment variable or default.
    workflow_dir : str | None
        Working directory for Prefect deployments. If None, uses
        QDASH_WORKFLOW_DIR environment variable or default.

    Examples
    --------
    >>> resolver = PathResolver()
    >>> resolver.user_data_dir("alice")
    PosixPath('/app/calib_data/alice')

    >>> resolver.execution_data_dir("alice", "20240101", "001")
    PosixPath('/app/calib_data/alice/20240101/001')

    """

    DEFAULT_CALIB_DATA_BASE = "/app/calib_data"
    DEFAULT_WORKFLOW_DIR = "/app/qdash/workflow"

    def __init__(
        self,
        calib_data_base: str | None = None,
        workflow_dir: str | None = None,
    ) -> None:
        self._calib_data_base = Path(
            calib_data_base
            if calib_data_base is not None
            else os.getenv("QDASH_CALIB_DATA_BASE", self.DEFAULT_CALIB_DATA_BASE)
        )
        self._workflow_dir = Path(
            workflow_dir
            if workflow_dir is not None
            else os.getenv("QDASH_WORKFLOW_DIR", self.DEFAULT_WORKFLOW_DIR)
        )

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
        """Get the base directory for a user's calibration data.

        Parameters
        ----------
        username : str
            Username for the data directory.

        Returns
        -------
        Path
            Path to the user's data directory.

        """
        return self._calib_data_base / username

    def classifier_dir(self, username: str) -> Path:
        """Get the classifier directory for a user.

        Parameters
        ----------
        username : str
            Username for the classifier directory.

        Returns
        -------
        Path
            Path to the user's classifier directory.

        """
        return self.user_data_dir(username) / ".classifier"

    def execution_data_dir(self, username: str, date_str: str, index: str) -> Path:
        """Get the directory for a specific execution's data.

        Parameters
        ----------
        username : str
            Username for the execution.
        date_str : str
            Date string (e.g., "20240101").
        index : str
            Execution index (e.g., "001").

        Returns
        -------
        Path
            Path to the execution data directory.

        """
        return self.user_data_dir(username) / date_str / index


# Default resolver instance for convenience
_default_resolver: PathResolver | None = None


def get_path_resolver() -> PathResolver:
    """Get the default PathResolver instance.

    Returns a singleton instance of PathResolver using environment
    variables or defaults.

    Returns
    -------
    PathResolver
        The default path resolver instance.

    """
    global _default_resolver
    if _default_resolver is None:
        _default_resolver = PathResolver()
    return _default_resolver
