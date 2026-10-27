"""Resolve where Qubex configuration files live for a chip and its Systems.

Two directory layouts are supported and detected automatically:

``legacy``
    ``<root>/<chip_id>/{config,params,calibration}``. Shared files such as
    ``wiring.yaml`` are duplicated per chip, so every lookup needs a chip ID.

``shared``
    ``<root>/config/{chip,system,wiring,box,skew}.yaml`` shared by every chip,
    with ``<root>/params/<system_id>/`` and ``<root>/calibration/<system_id>/``
    owned by one System each. A chip with a single System uses
    ``system_id == chip_id``, so the owned directories keep their old names.

The tree declares its layout in ``<root>/qubex-config.json`` (``layout_version``
``"1.0"`` for legacy, ``"2.0"`` for shared; see ``config/domain/qubex-config-schemas``).
Without a manifest, the presence of ``<root>/config/chip.yaml`` selects ``shared``.
``QUBEX_LAYOUT=shared`` or ``QUBEX_LAYOUT=legacy`` overrides both.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any

from qdash.common.config.path_resolver import resolve_config_base_path

LAYOUT_ENV_VAR = "QUBEX_LAYOUT"
CALIB_NOTE_FILE = "calib_note.json"
MANIFEST_FILE = "qubex-config.json"
"""Root-level manifest declaring ``layout_version``."""


class LayoutKind(StrEnum):
    """Directory layout of a Qubex configuration tree."""

    SHARED = "shared"
    LEGACY = "legacy"

    @property
    def version(self) -> str:
        """Layout version agreed with the qubex team: ``1.0`` legacy, ``2.0`` shared."""
        return LAYOUT_VERSIONS[self]

    @classmethod
    def from_version(cls, version: str) -> LayoutKind:
        for kind, value in LAYOUT_VERSIONS.items():
            if value == str(version):
                return kind
        choices = ", ".join(LAYOUT_VERSIONS.values())
        raise ValueError(f"layout_version must be one of {choices}, got {version!r}")


LAYOUT_VERSIONS: dict[LayoutKind, str] = {LayoutKind.LEGACY: "1.0", LayoutKind.SHARED: "2.0"}


def read_manifest(root: Path) -> dict[str, Any] | None:
    """Parsed ``<root>/qubex-config.json``, or None when the tree has no manifest.

    Raises:
        ValueError: If the manifest is not a JSON object or names an unknown version.

    """
    path = root / MANIFEST_FILE
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} must hold a JSON object")
    version = data.get("layout_version")
    if not isinstance(version, str):
        raise ValueError(f"{path} must declare layout_version as a string")
    LayoutKind.from_version(version)
    return data


def detect_layout_kind(root: Path) -> LayoutKind:
    """Return the layout of ``root``: the env override, the manifest, else a probe."""
    forced = os.getenv(LAYOUT_ENV_VAR, "").strip().lower()
    if forced:
        try:
            return LayoutKind(forced)
        except ValueError as exc:
            choices = ", ".join(kind.value for kind in LayoutKind)
            raise ValueError(f"{LAYOUT_ENV_VAR} must be one of {choices}, got {forced!r}") from exc
    manifest = read_manifest(root)
    if manifest is not None:
        return LayoutKind.from_version(manifest["layout_version"])
    if (root / "config" / "chip.yaml").is_file():
        return LayoutKind.SHARED
    return LayoutKind.LEGACY


@dataclass(frozen=True)
class QubexLayout:
    """Paths inside one Qubex configuration tree.

    Shared files take an optional ``chip_id``; the legacy layout requires it
    because each chip keeps its own copy. Owned directories take a ``system_id``,
    which equals the chip ID for a chip that has a single System.
    """

    root: Path
    kind: LayoutKind

    @classmethod
    def detect(cls, root: Path | str | None = None) -> QubexLayout:
        """Build a layout for ``root`` (default: the resolved configuration base)."""
        base = Path(root) if root is not None else resolve_config_base_path()
        return cls(root=base, kind=detect_layout_kind(base))

    @property
    def is_shared(self) -> bool:
        """Whether shared files are stored once for every chip."""
        return self.kind is LayoutKind.SHARED

    @property
    def version(self) -> str:
        """Layout version (``1.0`` or ``2.0``)."""
        return self.kind.version

    @property
    def manifest_path(self) -> Path:
        """Path of the root manifest, whether or not it exists."""
        return self.root / MANIFEST_FILE

    def manifest(self) -> dict[str, Any] | None:
        """The root manifest, or None when the tree was detected without one."""
        return read_manifest(self.root)

    # ------------------------------------------------------------------ #
    # Shared files
    # ------------------------------------------------------------------ #

    def config_dir(self, chip_id: str | None = None) -> Path:
        """Directory holding chip/system/wiring/box/skew YAML files."""
        if self.is_shared:
            return self.root / "config"
        if not chip_id:
            raise ValueError("chip_id is required to locate shared files in the legacy layout")
        return self.root / chip_id / "config"

    def chip_yaml(self, chip_id: str | None = None) -> Path:
        """Path of ``chip.yaml``."""
        return self.config_dir(chip_id) / "chip.yaml"

    def system_yaml(self, chip_id: str | None = None) -> Path:
        """Path of ``system.yaml``."""
        return self.config_dir(chip_id) / "system.yaml"

    def wiring_yaml(self, chip_id: str | None = None) -> Path:
        """Path of ``wiring.yaml``."""
        return self.config_dir(chip_id) / "wiring.yaml"

    def box_yaml(self, chip_id: str | None = None) -> Path:
        """Path of ``box.yaml``."""
        return self.config_dir(chip_id) / "box.yaml"

    def skew_yaml(self, chip_id: str | None = None) -> Path:
        """Path of ``skew.yaml``."""
        return self.config_dir(chip_id) / "skew.yaml"

    # ------------------------------------------------------------------ #
    # Owned directories (one per System)
    # ------------------------------------------------------------------ #

    def params_dir(self, system_id: str) -> Path:
        """Parameter directory owned by one System."""
        _require_id(system_id, "system_id")
        if self.is_shared:
            return self.root / "params" / system_id
        return self.root / system_id / "params"

    def calibration_dir(self, system_id: str) -> Path:
        """Calibration directory owned by one System."""
        _require_id(system_id, "system_id")
        if self.is_shared:
            return self.root / "calibration" / system_id
        return self.root / system_id / "calibration"

    def calib_note_path(self, system_id: str) -> Path:
        """Path of the System's exported calibration note."""
        return self.calibration_dir(system_id) / CALIB_NOTE_FILE

    # ------------------------------------------------------------------ #
    # Repository paths
    # ------------------------------------------------------------------ #

    def repo_relpath(self, path: Path | str) -> PurePosixPath:
        """Path of a local file relative to the configuration repository root.

        Raises:
            ValueError: If ``path`` is outside the configuration tree.

        """
        candidate = Path(path)
        try:
            relative = candidate.relative_to(self.root)
        except ValueError:
            relative = candidate.resolve().relative_to(self.root.resolve())
        return PurePosixPath(*relative.parts)


def _require_id(value: str, name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{name} must not be empty")
    if value != Path(value).name:
        raise ValueError(f"{name} must be a single path segment, got {value!r}")
