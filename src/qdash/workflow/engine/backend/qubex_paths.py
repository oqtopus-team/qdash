"""Path resolution for Qubex backend.

This module provides centralized path management for Qubex-specific
directories and configuration files.

Environment Variables
---------------------
QDASH_QUBEX_CONFIG_BASE : str
    Base directory for Qubex chip configurations.
    Default: /app/config/qubex

"""

from __future__ import annotations

import os
from pathlib import Path


class QubexPaths:
    """Resolves paths for Qubex backend configuration files.

    This class provides methods to generate paths for chip-specific
    configuration files, parameters, and calibration notes.

    Parameters
    ----------
    config_base : str | None
        Base directory for Qubex configurations. If None, uses
        QDASH_QUBEX_CONFIG_BASE environment variable or default.

    Examples
    --------
    >>> paths = QubexPaths()
    >>> paths.config_dir("64Q")
    PosixPath('/app/config/qubex/64Q/config')

    >>> paths.wiring_yaml("64Q")
    PosixPath('/app/config/qubex/64Q/config/wiring.yaml')

    """

    DEFAULT_CONFIG_BASE = "/app/config/qubex"
    DEFAULT_CALIB_NOTE_PATH = "/app/calib_note.json"

    def __init__(
        self,
        config_base: str | None = None,
    ) -> None:
        self._config_base = Path(
            config_base
            if config_base is not None
            else os.getenv("QDASH_QUBEX_CONFIG_BASE", self.DEFAULT_CONFIG_BASE)
        )

    @property
    def config_base(self) -> Path:
        """Base directory for Qubex configurations."""
        return self._config_base

    @property
    def default_calib_note_path(self) -> Path:
        """Default calibration note path (fallback)."""
        return Path(self.DEFAULT_CALIB_NOTE_PATH)

    # -------------------------------------------------------------------------
    # Chip-specific directories
    # -------------------------------------------------------------------------

    def chip_dir(self, chip_id: str) -> Path:
        """Get the base directory for a chip's configuration.

        Parameters
        ----------
        chip_id : str
            Chip identifier (e.g., "64Q", "64Qv1").

        Returns
        -------
        Path
            Path to the chip's base directory.

        """
        return self._config_base / chip_id

    def config_dir(self, chip_id: str) -> Path:
        """Get the config directory for a chip.

        Parameters
        ----------
        chip_id : str
            Chip identifier.

        Returns
        -------
        Path
            Path to the chip's config directory.

        """
        return self.chip_dir(chip_id) / "config"

    def params_dir(self, chip_id: str) -> Path:
        """Get the params directory for a chip.

        Parameters
        ----------
        chip_id : str
            Chip identifier.

        Returns
        -------
        Path
            Path to the chip's params directory.

        """
        return self.chip_dir(chip_id) / "params"

    def calibration_dir(self, chip_id: str) -> Path:
        """Get the calibration directory for a chip.

        Parameters
        ----------
        chip_id : str
            Chip identifier.

        Returns
        -------
        Path
            Path to the chip's calibration directory.

        """
        return self.chip_dir(chip_id) / "calibration"

    # -------------------------------------------------------------------------
    # Configuration files
    # -------------------------------------------------------------------------

    def wiring_yaml(self, chip_id: str) -> Path:
        """Get the wiring configuration file path.

        Parameters
        ----------
        chip_id : str
            Chip identifier.

        Returns
        -------
        Path
            Path to the wiring.yaml file.

        """
        return self.config_dir(chip_id) / "wiring.yaml"

    def box_yaml(self, chip_id: str) -> Path:
        """Get the box configuration file path.

        Parameters
        ----------
        chip_id : str
            Chip identifier.

        Returns
        -------
        Path
            Path to the box.yaml file.

        """
        return self.config_dir(chip_id) / "box.yaml"

    def skew_yaml(self, chip_id: str) -> Path:
        """Get the skew configuration file path.

        Parameters
        ----------
        chip_id : str
            Chip identifier.

        Returns
        -------
        Path
            Path to the skew.yaml file.

        """
        return self.config_dir(chip_id) / "skew.yaml"

    # -------------------------------------------------------------------------
    # Parameter files
    # -------------------------------------------------------------------------

    def params_yaml(self, chip_id: str) -> Path:
        """Get the params.yaml file path.

        Parameters
        ----------
        chip_id : str
            Chip identifier.

        Returns
        -------
        Path
            Path to the params.yaml file.

        """
        return self.params_dir(chip_id) / "params.yaml"

    def props_yaml(self, chip_id: str) -> Path:
        """Get the props.yaml file path.

        Parameters
        ----------
        chip_id : str
            Chip identifier.

        Returns
        -------
        Path
            Path to the props.yaml file.

        """
        return self.params_dir(chip_id) / "props.yaml"

    # -------------------------------------------------------------------------
    # Calibration files
    # -------------------------------------------------------------------------

    def calib_note_json(self, chip_id: str) -> Path:
        """Get the calibration note JSON file path.

        Parameters
        ----------
        chip_id : str
            Chip identifier.

        Returns
        -------
        Path
            Path to the calib_note.json file.

        """
        return self.calibration_dir(chip_id) / "calib_note.json"


# Default instance for convenience
_default_qubex_paths: QubexPaths | None = None


def get_qubex_paths() -> QubexPaths:
    """Get the default QubexPaths instance.

    Returns a singleton instance of QubexPaths using environment
    variables or defaults.

    Returns
    -------
    QubexPaths
        The default QubexPaths instance.

    """
    global _default_qubex_paths
    if _default_qubex_paths is None:
        _default_qubex_paths = QubexPaths()
    return _default_qubex_paths
