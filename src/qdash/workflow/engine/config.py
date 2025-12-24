"""Calibration configuration for workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from qdash.workflow.paths import get_path_resolver


@dataclass
class CalibConfig:
    """Configuration for a calibration session.

    Attributes:
        username: Username for the session
        chip_id: Target chip ID
        qids: List of qubit IDs to calibrate
        execution_id: Unique execution identifier (e.g., "20240101-001")
        backend_name: Backend type ('qubex' or 'fake')
        flow_name: Flow name for display
        tags: Tags for categorization
        note: Additional notes
        muxes: MUX IDs for system-level tasks
        project_id: Project ID for multi-tenancy
        enable_github_pull: Whether to pull config from GitHub
        enable_provenance_tracking: Whether to track data provenance for lineage
    """

    username: str
    chip_id: str
    qids: list[str]
    execution_id: str
    backend_name: str = "qubex"
    flow_name: str | None = None
    tags: list[str] | None = None
    note: dict[str, Any] | None = None
    muxes: list[int] | None = None
    project_id: str | None = None
    enable_github_pull: bool = False
    enable_provenance_tracking: bool = False

    # Derived paths (computed after initialization)
    calib_data_path: str = field(default="", init=False)
    classifier_dir: str = field(default="", init=False)

    def __post_init__(self) -> None:
        """Compute derived paths from execution_id."""
        date_str, index = self.execution_id.split("-")
        resolver = get_path_resolver()
        self.classifier_dir = str(resolver.classifier_dir(self.username))
        self.calib_data_path = str(resolver.execution_data_dir(self.username, date_str, index))

        # Set default tags if not provided
        if self.tags is None:
            self.tags = [self.flow_name or "Python Flow Execution"]

        # Set default note if not provided
        if self.note is None:
            self.note = {}
