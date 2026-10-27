"""Create the Qubex configuration directory of a new chip.

QDash keeps one directory per chip in the Qubex configuration tree and runs
it with ``system_id == chip_id``::

    <config root>/<chip_id>/
      config/{chip,system,wiring,box}.yaml (+ skew.yaml and other hardware files)
      params/*.yaml
      calibration/calib_note.json

:class:`ChipConfigScaffolder` writes that directory when a chip is created:

* ``chip.yaml`` and ``system.yaml`` carry one entry keyed by the chip ID;
* hardware files (wiring, boxes, skew, ...) are copied from an existing system
  when one is named, so a chip installed on the same wiring starts runnable;
* ``params/`` is always new: QDash's templates for the system's backend, with
  empty ``data`` so calibration fills them;
* ``calibration/calib_note.json`` holds ``{}``.

An existing chip directory is never modified.
"""

from __future__ import annotations

import errno
import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from qdash.common.config.loader import ConfigLoader
from qdash.common.config.path_resolver import resolve_config_base_path
from qdash.common.utils.chip_id import CHIP_ID_PATTERN, RESERVED_CHIP_IDS, validate_chip_id

logger = logging.getLogger(__name__)

Backend = Literal["quel1", "quel3"]
DEFAULT_BACKEND: Backend = "quel1"
SUPPORTED_BACKENDS: tuple[Backend, ...] = ("quel1", "quel3")

PARAMS_TEMPLATES_DIR = "domain/qubex-params"

# Files that name the system and are rewritten for the new chip; every other
# file in the source's config/ is hardware description and copied verbatim.
_KEYED_FILES = frozenset({"chip.yaml", "system.yaml", "wiring.yaml"})
_HARDWARE_FILES = ("box.yaml", "skew.yaml", "cable_delay.yaml", "external_devices.yaml")
_SKIP_DIRS = RESERVED_CHIP_IDS
_DIR_NAME = re.compile(CHIP_ID_PATTERN)


class ChipConfigError(ValueError):
    """The configuration cannot be created as asked; the message is for the user."""


@dataclass(frozen=True)
class ConfigSource:
    """An existing system whose hardware files a new chip can copy."""

    system_id: str
    backend: str
    mux_count: int
    files: list[str]


@dataclass
class ScaffoldResult:
    """What :meth:`ChipConfigScaffolder.scaffold` did."""

    status: Literal["created", "existing", "skipped"]
    path: str
    source_system_id: str | None = None
    backend: str | None = None
    files: list[str] = field(default_factory=list)
    message: str = ""


def _load_yaml(path: Path) -> Any:
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _entry_for(payload: Any, system_id: str) -> Any:
    """The entry of ``payload`` for ``system_id``; never infer another system."""
    if not isinstance(payload, dict) or not payload:
        return None
    if system_id in payload:
        return payload[system_id]
    raise ChipConfigError(f"Cannot find system '{system_id}' in configuration entries")


def _dump(path: Path, payload: Any, header: str) -> None:
    body = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    path.write_text(f"{header}\n{body}", encoding="utf-8")


class ChipConfigScaffolder:
    """Create ``<config root>/<chip_id>/`` for a new chip."""

    def __init__(self, config_base: Path | None = None, templates_dir: Path | None = None) -> None:
        self._base = config_base or resolve_config_base_path()
        self._templates = templates_dir or ConfigLoader.get_config_dir() / PARAMS_TEMPLATES_DIR

    @property
    def available(self) -> bool:
        """Whether a configuration tree is mounted."""
        return self._base.is_dir()

    def chip_dir(self, chip_id: str) -> Path:
        return self._base / chip_id

    # ------------------------------------------------------------------ sources

    def list_sources(self) -> list[ConfigSource]:
        """Systems in the tree that have a wiring file, sorted by ID."""
        if not self.available:
            return []
        sources = []
        for directory in sorted(self._base.iterdir()):
            if (
                not directory.is_dir()
                or not _DIR_NAME.fullmatch(directory.name)
                or directory.name in _SKIP_DIRS
            ):
                continue
            if not (directory / "config" / "wiring.yaml").is_file():
                continue
            try:
                sources.append(self._describe_source(directory))
            except Exception as exc:  # one broken directory must not hide the others
                logger.warning("Skipping config source %s: %s", directory.name, exc)
        return sources

    def _describe_source(self, directory: Path) -> ConfigSource:
        system_id = directory.name
        config_dir = directory / "config"
        rows = _entry_for(_load_yaml(config_dir / "wiring.yaml"), system_id)
        system = self._source_system_entry(directory)
        files = sorted(
            path.name
            for path in config_dir.iterdir()
            if path.is_file() and path.name not in {"chip.yaml", "system.yaml"}
        )
        return ConfigSource(
            system_id=system_id,
            backend=str(system.get("backend", DEFAULT_BACKEND)),
            mux_count=len(rows) if isinstance(rows, list) else 0,
            files=files,
        )

    def _source_system_entry(self, directory: Path) -> dict[str, Any]:
        """The source's ``system.yaml`` entry, or one built from a legacy ``chip.yaml``."""
        config_dir = directory / "config"
        entry = _entry_for(_load_yaml(config_dir / "system.yaml"), directory.name)
        if isinstance(entry, dict) and entry.get("backend"):
            return dict(entry)
        chip = _entry_for(_load_yaml(config_dir / "chip.yaml"), directory.name)
        system: dict[str, Any] = {"backend": DEFAULT_BACKEND}
        if isinstance(chip, dict) and chip.get("clock_master"):
            system[DEFAULT_BACKEND] = {"clock_master": chip["clock_master"]}
        return system

    # ----------------------------------------------------------------- scaffold

    def scaffold(
        self,
        *,
        chip_id: str,
        n_qubits: int,
        source_system_id: str | None = None,
        backend: str | None = None,
    ) -> ScaffoldResult:
        """Write the chip directory; an existing one is left untouched."""
        try:
            validate_chip_id(chip_id)
        except ValueError as exc:
            raise ChipConfigError(str(exc)) from exc
        if not self.available:
            return ScaffoldResult(
                status="skipped",
                path=chip_id,
                message="No Qubex configuration tree is mounted; no files were created.",
            )
        target = self.chip_dir(chip_id)
        if target.exists():
            return ScaffoldResult(
                status="existing",
                path=chip_id,
                message=f"{chip_id}/ already exists in the configuration tree and was kept as is.",
            )

        system, rows, hardware = self._plan_hardware(source_system_id, backend)
        system_backend = str(system["backend"])
        if system_backend not in SUPPORTED_BACKENDS:
            raise ChipConfigError(
                f"Backend '{system_backend}' has no parameter templates "
                f"(supported: {', '.join(SUPPORTED_BACKENDS)})"
            )

        staging = Path(tempfile.mkdtemp(prefix=f".{chip_id}.", dir=self._base))
        try:
            files = self._write_tree(
                staging,
                chip_id=chip_id,
                n_qubits=n_qubits,
                system=system,
                rows=rows,
                hardware=hardware,
                source_system_id=source_system_id,
            )
            staging.chmod(0o755)
            try:
                staging.rename(target)
            except OSError as exc:
                if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY} or not target.is_dir():
                    raise
                shutil.rmtree(staging, ignore_errors=True)
                return ScaffoldResult(
                    status="existing",
                    path=chip_id,
                    message=f"{chip_id}/ already exists in the configuration tree and was kept as is.",
                )
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        self._match_owner(target)
        logger.info(
            "Created configuration %s/ (backend=%s, wiring from %s)",
            chip_id,
            system_backend,
            source_system_id or "none",
        )
        return ScaffoldResult(
            status="created",
            path=chip_id,
            source_system_id=source_system_id,
            backend=system_backend,
            files=files,
            message=(
                f"Created {chip_id}/ in the configuration tree. "
                "Push it from the Config page to share it."
            ),
        )

    def remove(self, chip_id: str) -> None:
        """Delete a directory this scaffolder created (used to roll back)."""
        shutil.rmtree(self.chip_dir(chip_id), ignore_errors=True)

    def _plan_hardware(
        self, source_system_id: str | None, backend: str | None
    ) -> tuple[dict[str, Any], list[Any], list[Path]]:
        if source_system_id is None:
            return {"backend": backend or DEFAULT_BACKEND}, [], []

        source = self.chip_dir(source_system_id)
        if (
            not _DIR_NAME.fullmatch(source_system_id)
            or source_system_id in _SKIP_DIRS
            or not (source / "config" / "wiring.yaml").is_file()
        ):
            raise ChipConfigError(f"System '{source_system_id}' has no config/wiring.yaml")
        system = self._source_system_entry(source)
        if backend is not None and backend != system["backend"]:
            raise ChipConfigError(
                f"System '{source_system_id}' uses backend '{system['backend']}', not '{backend}'"
            )
        rows = _entry_for(_load_yaml(source / "config" / "wiring.yaml"), source_system_id)
        if not isinstance(rows, list):
            raise ChipConfigError(
                f"Cannot find the wiring of '{source_system_id}' in its wiring.yaml"
            )
        hardware = [
            path
            for path in sorted((source / "config").iterdir())
            if path.is_file() and path.name not in _KEYED_FILES
        ]
        return system, rows, hardware

    def _write_tree(
        self,
        root: Path,
        *,
        chip_id: str,
        n_qubits: int,
        system: dict[str, Any],
        rows: list[Any],
        hardware: list[Path],
        source_system_id: str | None,
    ) -> list[str]:
        config_dir = root / "config"
        params_dir = root / "params"
        calibration_dir = root / "calibration"
        for directory in (config_dir, params_dir, calibration_dir):
            directory.mkdir(parents=True)

        origin = f"wiring copied from {source_system_id}" if source_system_id else "empty wiring"
        header = f"# Generated by QDash for {chip_id} (system_id == chip_id; {origin})."
        system_entry = {"chip_id": chip_id, **{k: v for k, v in system.items() if k != "chip_id"}}
        _dump(config_dir / "chip.yaml", {chip_id: {"name": chip_id, "n_qubits": n_qubits}}, header)
        _dump(config_dir / "system.yaml", {chip_id: system_entry}, header)
        _dump(config_dir / "wiring.yaml", {chip_id: rows}, header)
        for path in hardware:
            shutil.copy2(path, config_dir / path.name)
        if not (config_dir / "box.yaml").exists():
            _dump(config_dir / "box.yaml", {}, header)

        for template in self._param_templates(str(system["backend"])):
            shutil.copy2(template, params_dir / template.name)
        (calibration_dir / "calib_note.json").write_text("{}\n", encoding="utf-8")

        written = [
            path.relative_to(root).as_posix() for path in sorted(root.rglob("*")) if path.is_file()
        ]
        return [f"{chip_id}/{path}" for path in written]

    def _param_templates(self, backend: str) -> list[Path]:
        """Common templates plus the backend's, the backend's winning on a name clash."""
        templates: dict[str, Path] = {}
        for group in ("common", backend):
            directory = self._templates / group
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.yaml")):
                templates[path.name] = path
        if not templates:
            raise ChipConfigError(f"No parameter templates found in {self._templates}")
        return [templates[name] for name in sorted(templates)]

    def _match_owner(self, root: Path) -> None:
        """Give the new files the tree's owner when running as root (bind mounts)."""
        if os.name != "posix" or os.geteuid() != 0:
            return
        try:
            owner = self._base.stat()
            for path in [root, *root.rglob("*")]:
                os.chown(path, owner.st_uid, owner.st_gid)
        except OSError as exc:
            logger.debug("Could not match owner for %s: %s", root, exc)
