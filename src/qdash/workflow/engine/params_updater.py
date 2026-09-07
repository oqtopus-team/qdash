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
from qdash.workflow.engine.backend.qubex_paths import get_qubex_paths

if TYPE_CHECKING:
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
    """Resolve worker-side configuration and labels without reconnecting hardware."""

    def __init__(self, backend: BaseBackend, chip_id: str | None) -> None:
        super().__init__()
        self._backend = backend
        self._chip_id = chip_id

    def _resolve_params_dir(self) -> Path | None:
        config_dir = getattr(self._backend, "config", {}).get("params_dir")
        if config_dir:
            path = Path(config_dir)
            if path.exists():
                return path

        # Only call get_session() if already connected (avoid reconnection with empty qids)
        session_obj = None
        try:
            # Check if backend is already initialized (QubexBackend has _exp attribute)
            if hasattr(self._backend, "_exp") and self._backend._exp is not None:
                session_obj = self._backend.get_instance()
        except Exception:
            session_obj = None

        if session_obj is not None:
            params_path = getattr(session_obj, "params_path", None)
            if params_path:
                path = Path(params_path)
                if path.exists():
                    return path

        chip_id = getattr(self._backend, "config", {}).get("chip_id") or self._chip_id
        if not chip_id:
            return None

        for candidate in (
            get_qubex_paths().params_dir(chip_id),
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

        try:
            experiment = self._backend.get_instance()
        except Exception:
            return None

        get_label = getattr(experiment, "get_qubit_label", None)
        if callable(get_label):
            return cast("str", get_label(index))
        return None
