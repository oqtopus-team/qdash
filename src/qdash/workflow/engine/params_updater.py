from __future__ import annotations

import contextlib
import logging
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

from filelock import FileLock
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from qdash.common.config.loader import ConfigLoader
from qdash.datamodel.task import ParameterModel
from qdash.workflow.engine.backend.qubex_paths import get_qubex_paths
from qdash.workflow.worker.flows.push_props.formatter import represent_none

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.base import BaseBackend

logger = logging.getLogger(__name__)


def _load_params_updater_settings() -> dict[str, Any]:
    workflow_settings = ConfigLoader.load_workflow()
    if not isinstance(workflow_settings, dict):
        return {}
    settings = workflow_settings.get("params_updater", {})
    if not isinstance(settings, dict):
        return {}
    return settings


def _validate_yaml_file_name(file_name: str) -> str:
    normalized = file_name.strip()
    path = Path(normalized)
    if not normalized or path.name != normalized or path.suffix != ".yaml":
        raise ValueError(f"Invalid params updater YAML file name: {file_name!r}")
    return normalized


def _load_param_file_map() -> dict[str, str]:
    settings = _load_params_updater_settings()
    value = settings.get("parameter_file_map")
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("workflow.params_updater.parameter_file_map must be a mapping")

    result: dict[str, str] = {}
    for parameter_name, file_name in value.items():
        if not isinstance(parameter_name, str) or not isinstance(file_name, str):
            raise ValueError(
                "workflow.params_updater.parameter_file_map must map strings to strings"
            )
        result[parameter_name] = _validate_yaml_file_name(file_name)
    return result


def _load_extra_file_map() -> dict[str, list[str]]:
    settings = _load_params_updater_settings()
    value = settings.get("extra_file_map")
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("workflow.params_updater.extra_file_map must be a mapping")

    result: dict[str, list[str]] = {}
    for parameter_name, file_names in value.items():
        if not isinstance(parameter_name, str) or not isinstance(file_names, list):
            raise ValueError("workflow.params_updater.extra_file_map must map strings to lists")
        if not all(isinstance(file_name, str) for file_name in file_names):
            raise ValueError("workflow.params_updater.extra_file_map values must be string lists")
        result[parameter_name] = [_validate_yaml_file_name(file_name) for file_name in file_names]
    return result


class ParamsUpdater(Protocol):
    """Protocol for backend-specific parameter updaters."""

    def update(self, qid: str, output_parameters: dict[str, Any]) -> set[str]: ...


def resolve_param_yaml_file_names(output_parameters: dict[str, Any]) -> set[str]:
    """Resolve params YAML files addressed by output parameter names.

    This intentionally does not check whether the YAML value would change. Task
    execution may have already updated local params files before finish-time
    GitHub push, but the same files still need to be included in the batch push
    candidate list.
    """
    param_file_map = _load_param_file_map()
    extra_file_map = _load_extra_file_map()

    file_names: set[str] = set()
    for parameter_name in output_parameters:
        file_name = param_file_map.get(parameter_name)
        if file_name is not None:
            file_names.add(file_name)
        file_names.update(extra_file_map.get(parameter_name, []))
    return file_names


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


class _QubexParamsUpdater:
    """Synchronize calibration results with Qubex params YAML files."""

    def __init__(self, backend: Any, chip_id: str | None) -> None:
        self._backend = backend
        self._chip_id = chip_id
        self._param_file_map = _load_param_file_map()
        self._extra_file_map = _load_extra_file_map()
        self._yaml = YAML(typ="rt")
        self._yaml.preserve_quotes = True
        self._yaml.width = None
        self._yaml.indent(mapping=2, sequence=4, offset=2)
        self._yaml.representer.add_representer(type(None), represent_none)

    def update(self, qid: str, output_parameters: dict[str, Any]) -> set[str]:
        updated_files: set[str] = set()
        params_dir = self._resolve_params_dir()
        if params_dir is None:
            return updated_files

        label = self._resolve_qubit_label(qid)
        if label is None:
            return updated_files

        for key, param in output_parameters.items():
            file_name = self._param_file_map.get(key)
            if file_name is None:
                continue

            value = self._extract_value(param)
            if value is None:
                continue

            file_path = params_dir / file_name
            if self._update_yaml(file_path, label, value):
                updated_files.add(file_name)

            for extra_file in self._extra_file_map.get(key, []):
                extra_path = params_dir / extra_file
                if self._update_yaml(extra_path, label, value):
                    updated_files.add(extra_file)

        return updated_files

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

    @staticmethod
    def _extract_value(param: Any) -> float | int | str | None:
        if isinstance(param, ParameterModel):
            return _QubexParamsUpdater._coerce_value(param.value)

        if isinstance(param, dict) and "value" in param:
            return _QubexParamsUpdater._coerce_value(param.get("value"))

        value = getattr(param, "value", param)
        return _QubexParamsUpdater._coerce_value(value)

    @staticmethod
    def _coerce_value(value: Any) -> float | int | str | None:
        if value is None:
            return None

        if hasattr(value, "item"):
            with contextlib.suppress(Exception):
                value = value.item()

        if isinstance(value, (int, float)):
            numeric = float(value)
            if numeric != numeric:  # NaN guard
                return None
            return numeric

        if isinstance(value, str):
            return value
        return None

    def _update_yaml(self, file_path: Path, qubit_label: str, value: float | int | str) -> bool:
        """Update YAML file with file locking and atomic write to prevent race conditions."""
        if not file_path.exists():
            return False

        lock_path = file_path.with_suffix(file_path.suffix + ".lock")
        lock_path.touch(exist_ok=True)

        with FileLock(lock_path):
            # Read current data under lock
            with file_path.open("r") as fp:
                data = self._yaml.load(fp) or CommentedMap()

            if not isinstance(data, CommentedMap):
                data = CommentedMap(data)

            section = data.get("data")
            if section is None or not isinstance(section, dict):
                section = CommentedMap()
                data["data"] = section
            elif not isinstance(section, CommentedMap):
                section = CommentedMap(section)
                data["data"] = section

            current_value = section.get(qubit_label)
            if self._values_equal(current_value, value):
                return False

            if isinstance(section, CommentedMap):
                self._set_ordered(section, qubit_label, value)
            else:
                section[qubit_label] = value

            # Atomic write: write to temp file then rename
            dir_path = file_path.parent
            with tempfile.NamedTemporaryFile(
                mode="w",
                dir=dir_path,
                suffix=".tmp",
                delete=False,
            ) as tmp_fp:
                tmp_path = Path(tmp_fp.name)
                self._yaml.dump(data, tmp_fp)

            # Atomic rename (overwrites target)
            os.replace(tmp_path, file_path)

        lock_path.touch(exist_ok=True)
        return True

    @staticmethod
    def _values_equal(current: Any, new: Any) -> bool:
        if current is None and new is None:
            return True
        if isinstance(current, (int, float)) and isinstance(new, (int, float)):
            return abs(float(current) - float(new)) <= 1e-9
        return bool(current == new)

    @staticmethod
    def _label_index(label: str) -> int | None:
        if len(label) < 3 or label[0] not in {"Q", "q"}:
            return None
        try:
            return int(label[1:])
        except ValueError:
            return None

    def _set_ordered(self, section: CommentedMap, label: str, value: float | int | str) -> None:
        if label in section:
            section[label] = value
            return

        label_index = self._label_index(label)
        if label_index is None:
            section[label] = value
            return

        insert_pos = None
        for idx, existing in enumerate(section):
            existing_index = self._label_index(existing)
            if existing_index is None:
                continue
            if label_index < existing_index:
                insert_pos = idx
                break

        if insert_pos is None:
            section[label] = value
        else:
            section.insert(insert_pos, label, value)
