"""Path resolution for Qubex backend.

This module provides centralized path management for Qubex-specific
directories and configuration files.

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

QUBEX_CONFIG_BASE = Path("/app/config/qubex")
"""Base directory for Qubex chip configurations."""

DEFAULT_CALIB_NOTE_PATH = Path("/app/calib_note.json")
"""Default calibration note path (fallback)."""


class QubexPaths:
    """Resolves paths for Qubex backend configuration files.

    Examples
    --------
    >>> paths = QubexPaths()
    >>> paths.config_dir("64Q")
    PosixPath('/app/config/qubex/64Q/config')

    >>> paths.wiring_yaml("64Q")
    PosixPath('/app/config/qubex/64Q/config/wiring.yaml')

    """

    def __init__(self, config_base: Path | None = None) -> None:
        self._config_base = config_base or QUBEX_CONFIG_BASE

    @property
    def config_base(self) -> Path:
        """Base directory for Qubex configurations."""
        return self._config_base

    @property
    def default_calib_note_path(self) -> Path:
        """Default calibration note path (fallback)."""
        return DEFAULT_CALIB_NOTE_PATH

    # -------------------------------------------------------------------------
    # Chip-specific directories
    # -------------------------------------------------------------------------

    def chip_dir(self, chip_id: str) -> Path:
        """Get the base directory for a chip's configuration."""
        return self._config_base / chip_id

    def config_dir(self, chip_id: str) -> Path:
        """Get the config directory for a chip."""
        return self.chip_dir(chip_id) / "config"

    def params_dir(self, chip_id: str) -> Path:
        """Get the params directory for a chip."""
        return self.chip_dir(chip_id) / "params"

    def calibration_dir(self, chip_id: str) -> Path:
        """Get the calibration directory for a chip."""
        return self.chip_dir(chip_id) / "calibration"

    # -------------------------------------------------------------------------
    # Configuration files
    # -------------------------------------------------------------------------

    def wiring_yaml(self, chip_id: str) -> Path:
        """Get the wiring configuration file path."""
        return self.config_dir(chip_id) / "wiring.yaml"

    def box_yaml(self, chip_id: str) -> Path:
        """Get the box configuration file path."""
        return self.config_dir(chip_id) / "box.yaml"

    def skew_yaml(self, chip_id: str) -> Path:
        """Get the skew configuration file path."""
        return self.config_dir(chip_id) / "skew.yaml"

    # -------------------------------------------------------------------------
    # Parameter files
    # -------------------------------------------------------------------------

    def params_yaml(self, chip_id: str) -> Path:
        """Get the params.yaml file path."""
        return self.params_dir(chip_id) / "params.yaml"

    def props_yaml(self, chip_id: str) -> Path:
        """Get the props.yaml file path."""
        return self.params_dir(chip_id) / "props.yaml"

    # -------------------------------------------------------------------------
    # Calibration files
    # -------------------------------------------------------------------------

    def calib_note_json(self, chip_id: str) -> Path:
        """Get the calibration note JSON file path."""
        return self.calibration_dir(chip_id) / "calib_note.json"


# Default instance
_default_qubex_paths: QubexPaths | None = None


def get_qubex_paths() -> QubexPaths:
    """Get the default QubexPaths instance."""
    global _default_qubex_paths
    if _default_qubex_paths is None:
        _default_qubex_paths = QubexPaths()
    return _default_qubex_paths


def reset_qubex_paths() -> None:
    """Reset the cached QubexPaths instance."""
    global _default_qubex_paths
    _default_qubex_paths = None
