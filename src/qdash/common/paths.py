"""Container-side path constants shared between API and Workflow modules.

This module provides centralized path management for all container-side paths.
Host-side paths should be configured via .env and docker-compose.yaml volume mounts.

Example .env:
    CALIB_DATA_PATH=./my-custom-path/calib_data
    CONFIG_PATH=./config/qubex

Example docker-compose.yaml:
    volumes:
      - ${CALIB_DATA_PATH}:/app/calib_data
      - ${CONFIG_PATH}:/app/config/qubex
"""

from __future__ import annotations

from pathlib import Path

# =============================================================================
# Base directories
# =============================================================================

CONFIG_DIR: Path = Path("/app/config")
"""Base directory for configuration files (settings.yaml, metrics.yaml, etc.)."""

CALIB_DATA_BASE: Path = Path("/app/calib_data")
"""Base directory for calibration data storage."""

WORKFLOW_DIR: Path = Path("/app/qdash/workflow")
"""Base directory for workflow module."""

# =============================================================================
# Workflow subdirectories
# =============================================================================

CALIBTASKS_DIR: Path = WORKFLOW_DIR / "calibtasks"
"""Directory containing calibration task definitions."""

USER_FLOWS_DIR: Path = WORKFLOW_DIR / "user_flows"
"""Directory for user-created flow definitions."""

TEMPLATES_DIR: Path = WORKFLOW_DIR / "templates"
"""Directory for flow templates."""

SERVICE_DIR: Path = WORKFLOW_DIR / "service"
"""Directory for calibration service modules."""

# =============================================================================
# Qubex backend paths
# =============================================================================

QUBEX_CONFIG_BASE: Path = CONFIG_DIR / "qubex"
"""Base directory for Qubex backend configuration files."""
