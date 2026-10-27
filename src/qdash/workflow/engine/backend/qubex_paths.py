"""Path resolution for Qubex backend.

Thin chip-keyed facade over :class:`~qdash.common.config.qubex_layout.QubexLayout`.
New code should use ``QubexLayout`` (and ``SystemCatalog`` for System-aware
lookups) directly; this class keeps the historical ``chip_id`` API for callers
that have not moved yet. Base paths are imported from qdash.common.config.paths.

For host-side path customization, use .env and docker-compose.yaml volume mounts.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

# Re-export base path from common module
from qdash.common.config.paths import QUBEX_CONFIG_BASE
from qdash.common.config.qubex_layout import QubexLayout
from qdash.common.config.system_catalog import SystemCatalog, SystemSplitRequired

if TYPE_CHECKING:
    from collections.abc import Mapping

logger = logging.getLogger(__name__)

# Qubex-specific paths
DEFAULT_CALIB_NOTE_PATH = Path("/app/calib_note.json")
"""Default calibration note path (fallback)."""


class QubexPaths:
    """Resolves paths for Qubex backend configuration files.

    Examples
    --------
    >>> paths = QubexPaths()
    >>> paths.config_dir("64Q")
    PosixPath('/app/config/qubex-config/64Q/config')

    >>> paths.wiring_yaml("64Q")
    PosixPath('/app/config/qubex-config/64Q/config/wiring.yaml')

    """

    def __init__(self, config_base: Path | None = None) -> None:
        self._config_base = config_base or QUBEX_CONFIG_BASE
        self._layout = QubexLayout.detect(self._config_base)

    @property
    def config_base(self) -> Path:
        """Base directory for Qubex configurations."""
        return self._config_base

    @property
    def layout(self) -> QubexLayout:
        """The detected layout of the configuration tree."""
        return self._layout

    @property
    def default_calib_note_path(self) -> Path:
        """Default calibration note path (fallback)."""
        return DEFAULT_CALIB_NOTE_PATH

    # -------------------------------------------------------------------------
    # Chip-specific directories
    # -------------------------------------------------------------------------

    def chip_dir(self, chip_id: str) -> Path:
        """Get the base directory for a chip's configuration (legacy layout only)."""
        if self._layout.is_shared:
            raise ValueError("The shared layout has no per-chip directory; use QubexLayout")
        return self._config_base / chip_id

    def config_dir(self, chip_id: str) -> Path:
        """Get the config directory for a chip."""
        return self._layout.config_dir(chip_id)

    def params_dir(self, chip_id: str) -> Path:
        """Get the params directory of the System named like the chip."""
        return self._layout.params_dir(chip_id)

    def calibration_dir(self, chip_id: str) -> Path:
        """Get the calibration directory of the System named like the chip."""
        return self._layout.calibration_dir(chip_id)

    # -------------------------------------------------------------------------
    # Configuration files
    # -------------------------------------------------------------------------

    def wiring_yaml(self, chip_id: str) -> Path:
        """Get the wiring configuration file path."""
        return self._layout.wiring_yaml(chip_id)

    def box_yaml(self, chip_id: str) -> Path:
        """Get the box configuration file path."""
        return self._layout.box_yaml(chip_id)

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
        return self._layout.calib_note_path(chip_id)


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


# ---------------------------------------------------------------------------
# Session-level System resolution
# ---------------------------------------------------------------------------


def resolve_session_system_id(config: Mapping[str, Any]) -> str:
    """The Qubex System a backend session connects to.

    An explicit ``system_id`` in the session config wins. Otherwise the chip's
    catalog resolves the targeted ``qids`` (and ``muxes``) to one System. When
    the configuration tree cannot be read, the chip ID is used, which is the
    System name of every single-System chip.

    Raises:
        SystemSplitRequired: If the targets span several Systems.
        ValueError: If the config names no chip.

    """
    explicit = config.get("system_id")
    if explicit:
        return str(explicit)
    chip_id = config.get("chip_id")
    if not chip_id:
        raise ValueError("chip_id must be provided in config")
    catalog = SystemCatalog(QubexLayout.detect(), str(chip_id))
    try:
        return catalog.resolve_single(config.get("qids") or [], mux_ids=config.get("muxes"))
    except SystemSplitRequired:
        raise
    except (OSError, ValueError, LookupError, TypeError) as exc:
        logger.warning(
            "Could not resolve the System for chip %s (%s); using the chip ID", chip_id, exc
        )
        return str(chip_id)


def session_experiment_paths(config: Mapping[str, Any], system_id: str) -> dict[str, str]:
    """``config_dir`` / ``params_dir`` / ``calib_note_path`` for an ``Experiment``.

    Explicit entries in the session config take precedence; the rest come from
    the detected layout: shared files by chip, owned directories by System.
    """
    chip_id = str(config.get("chip_id") or system_id)
    layout = QubexLayout.detect()
    return {
        "config_dir": str(config.get("config_dir") or layout.config_dir(chip_id)),
        "params_dir": str(config.get("params_dir") or layout.params_dir(system_id)),
        "calib_note_path": str(config.get("note_path") or DEFAULT_CALIB_NOTE_PATH),
    }
