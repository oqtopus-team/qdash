"""Path resolution for workflow components.

This module provides path management for workflow-related directories and files.
Path constants are imported from qdash.common.config.paths for consistency across
API and workflow modules.

For host-side path customization, use .env and docker-compose.yaml volume mounts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

# Re-export path constants from common module for backward compatibility
from qdash.common.config.paths import (
    CALIB_DATA_BASE,
    CALIBTASKS_DIR,
    SERVICE_DIR,
    TEMPLATES_DIR,
    USER_FLOWS_DIR,
    WORKFLOW_DIR,
)

if TYPE_CHECKING:
    from pathlib import Path


class PathResolver:
    """Resolve project-scoped paths for workflow infrastructure.

    This class provides methods to generate shared project-chip calibration
    paths and immutable execution artifact directories. ``user_data_dir`` is
    retained only for legacy migration support.

    Examples
    --------
    >>> resolver = PathResolver()
    >>> resolver.user_data_dir("alice")
    PosixPath('/app/calib_data/alice')

    >>> resolver.execution_data_dir("proj-1", "chip-1", "20240101-001")
    PosixPath('/app/calib_data/projects/proj-1/chips/chip-1/executions/20240101-001')

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
    # Legacy user-specific paths
    # -------------------------------------------------------------------------

    def user_data_dir(self, username: str) -> Path:
        """Get the base directory for a user's calibration data."""
        return self._calib_data_base / username

    def project_chip_dir(self, project_id: str, chip_id: str) -> Path:
        """Get the shared calibration directory for a project chip."""
        return self._calib_data_base / "projects" / project_id / "chips" / chip_id

    def classifier_dir(self, project_id: str, chip_id: str) -> Path:
        """Get the shared classifier directory for a project chip."""
        return self.project_chip_dir(project_id, chip_id) / "shared" / "classifier"

    def execution_data_dir(self, project_id: str, chip_id: str, execution_id: str) -> Path:
        """Get the immutable artifact directory for an execution."""
        return self.project_chip_dir(project_id, chip_id) / "executions" / execution_id


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
