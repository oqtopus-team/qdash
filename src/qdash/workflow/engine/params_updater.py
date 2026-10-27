"""Resolve workflow backends for the shared Qubex YAML parameter updater."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, cast

from qdash.common.config.loader import ConfigLoader
from qdash.common.config.params_updater import (
    ParamsUpdater,
    YamlParamsUpdater,
    _load_extra_file_map,
    _load_param_file_map,
    resolve_param_yaml_file_names,
)
from qdash.common.config.qubex_layout import QubexLayout
from qdash.common.config.qubex_params_templates import is_common_file
from qdash.common.config.system_catalog import SystemCatalog

if TYPE_CHECKING:
    from typing import Any

    from qdash.workflow.engine.backend.base import BaseBackend

logger = logging.getLogger(__name__)

__all__ = [
    "ConfigLoader",
    "ParamsUpdater",
    "_load_extra_file_map",
    "_load_param_file_map",
    "get_params_updater",
    "resolve_param_yaml_file_names",
]


def get_params_updater(
    backend: BaseBackend | None, chip_id: str | None = None
) -> ParamsUpdater | None:
    """Resolve a backend-specific params updater for the given backend."""
    if backend is None:
        return None
    qubex_updater = _resolve_qubex_updater(backend, chip_id)
    if qubex_updater is not None:
        return qubex_updater
    fake_updater = _resolve_fake_updater(backend, chip_id)
    if fake_updater is not None:
        return fake_updater
    return None


def _resolve_qubex_updater(backend: BaseBackend, chip_id: str | None) -> ParamsUpdater | None:
    try:
        from qdash.workflow.engine.backend.qubex import QubexBackend
    except ImportError:
        return None

    if not isinstance(backend, QubexBackend):
        return None

    return _QubexParamsUpdater(backend, chip_id)


def _resolve_fake_updater(backend: BaseBackend, chip_id: str | None) -> ParamsUpdater | None:
    try:
        from qdash.workflow.engine.backend.fake import FakeBackend
    except ImportError:
        return None

    if not isinstance(backend, FakeBackend):
        return None

    return _QubexParamsUpdater(backend, chip_id)


class _QubexParamsUpdater(YamlParamsUpdater):
    """Resolve worker-side configuration and labels without reconnecting hardware.

    Physics values (the common template files) describe the chip, so they are
    projected into the ``params`` directory of every System of the chip; backend
    files (``capture_delay.yaml`` and the like) are written only to the session's
    own System directory. Projection targets are snapshotted and restored with
    the primary files so a failed update leaves every System unchanged.
    """

    def __init__(self, backend: BaseBackend, chip_id: str | None) -> None:
        super().__init__()
        self._backend = backend
        self._chip_id = chip_id
        self._projection_targets: list[Path] | None = None

    # ----------------------------------------------------------- projection

    def _resolve_chip_id(self) -> str | None:
        backend_config = getattr(self._backend, "config", {})
        return backend_config.get("chip_id") or self._chip_id

    def _other_system_dirs(self) -> list[Path]:
        """``params`` directories of the chip's other Systems (shared layout only)."""
        if self._projection_targets is not None:
            return self._projection_targets
        targets: list[Path] = []
        chip_id = self._resolve_chip_id()
        primary = self._resolve_params_dir()
        if chip_id and primary is not None:
            try:
                layout = QubexLayout.detect()
                systems = SystemCatalog(layout, chip_id).systems() if layout.is_shared else []
            except Exception:
                systems = []
            for entry in systems:
                candidate = layout.params_dir(entry.system_id)
                if candidate.is_dir() and candidate.resolve() != primary.resolve():
                    targets.append(candidate)
        self._projection_targets = targets
        return targets

    def _projection_paths(self, file_name: str) -> list[Path]:
        if not is_common_file(file_name):
            return []
        return [directory / file_name for directory in self._other_system_dirs()]

    def snapshot(self, qid: str, output_parameters: dict[str, Any]) -> dict[str, bytes | None]:
        snapshots = super().snapshot(qid, output_parameters)
        for file_name in sorted(self._resolve_file_names(output_parameters)):
            for path in self._projection_paths(file_name):
                lock_path = path.with_suffix(path.suffix + ".lock")
                lock_path.touch(exist_ok=True)
                with self._file_lock(lock_path):
                    try:
                        snapshots[str(path)] = path.read_bytes()
                    except FileNotFoundError:
                        snapshots[str(path)] = None
        return snapshots

    def update(self, qid: str, output_parameters: dict[str, Any]) -> set[str]:
        updated = super().update(qid, output_parameters)
        label = self._resolve_qubit_label(qid)
        if label is None:
            return updated
        for key, param in output_parameters.items():
            value = self._extract_value(param)
            if value is None:
                continue
            for file_name in sorted(self._resolve_file_names({key: param})):
                for path in self._projection_paths(file_name):
                    self._project(path, label, value)
        return updated

    def _project(self, path: Path, label: str, value: float | int | str) -> None:
        try:
            self._update_yaml(path, label, value)
        except Exception as exc:
            logger.warning("Could not project %s to %s: %s", path.name, path.parent, exc)

    def restore(self, snapshot: dict[str, bytes | None]) -> None:
        primary = {
            name: content for name, content in snapshot.items() if not Path(name).is_absolute()
        }
        super().restore(primary)
        for name, content in snapshot.items():
            path = Path(name)
            if not path.is_absolute():
                continue
            lock_path = path.with_suffix(path.suffix + ".lock")
            lock_path.touch(exist_ok=True)
            with self._file_lock(lock_path):
                if content is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(content)

    def _resolve_params_dir(self) -> Path | None:
        config_dir = getattr(self._backend, "config", {}).get("params_dir")
        if config_dir:
            path = Path(config_dir)
            if path.exists():
                return path

        # Only request the session if already connected (avoid reconnecting with empty qids).
        session_obj = None
        try:
            if self._backend.is_connected:
                session_obj = self._backend.get_instance()
        except Exception:
            session_obj = None

        if session_obj is not None:
            params_path = getattr(session_obj, "params_path", None)
            if params_path:
                path = Path(params_path)
                if path.exists():
                    return path

        backend_config = getattr(self._backend, "config", {})
        chip_id = backend_config.get("chip_id") or self._chip_id
        if not chip_id:
            return None

        system_id = backend_config.get("system_id") or chip_id
        for candidate in (
            QubexLayout.detect().params_dir(system_id),
            Path("config") / "qubex" / chip_id / "params",
        ):
            if candidate.exists():
                return candidate

        return None

    def _resolve_qubit_label(self, qid: str) -> str | None:
        try:
            index = int(qid)
        except ValueError:
            return qid

        config = getattr(self._backend, "config", {})
        project_id = config.get("project_id")
        chip_id = config.get("chip_id") or self._chip_id
        if project_id and chip_id:
            try:
                from qdash.common.domain.qubit import qid_to_label_from_chip

                return qid_to_label_from_chip(qid, project_id=project_id, chip_id=chip_id)
            except Exception:
                logger.debug(
                    "Failed to resolve qid label from chip metadata for qid=%s",
                    qid,
                    exc_info=True,
                )

        # A pipeline owner can prepare calibration files without connecting
        # hardware. Do not reconnect it as a label lookup fallback.
        if not self._backend.is_connected:
            return None

        try:
            experiment = self._backend.get_instance()
        except Exception:
            return None

        get_label = getattr(experiment, "get_qubit_label", None)
        if callable(get_label):
            return cast("str", get_label(index))
        return None
