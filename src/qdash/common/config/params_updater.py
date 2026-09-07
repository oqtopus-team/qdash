"""Mapped Qubex YAML persistence shared by the API and workflow runtime."""

from __future__ import annotations

import contextlib
import logging
import math
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from filelock import FileLock
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from qdash.common.config.loader import ConfigLoader
from qdash.datamodel.task import ParameterModel

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = logging.getLogger(__name__)


def represent_none(representer: Any, _: Any) -> Any:
    """Preserve explicit YAML nulls when updating a parameter file."""
    return representer.represent_scalar("tag:yaml.org,2002:null", "null")


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

    def snapshot(self, qid: str, output_parameters: dict[str, Any]) -> dict[str, bytes]: ...

    def update(self, qid: str, output_parameters: dict[str, Any]) -> set[str]: ...

    def verify(self, qid: str, output_parameters: dict[str, Any]) -> set[str]: ...

    def restore(self, snapshot: dict[str, bytes]) -> None: ...


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


class YamlParamsUpdater:
    """Synchronize calibration results with Qubex params YAML files."""

    def __init__(self, params_dir: Path | None = None, label: str | None = None) -> None:
        self._params_dir = params_dir
        self._label = label
        self._locks: dict[Path, FileLock] = {}
        self._param_file_map = _load_param_file_map()
        self._extra_file_map = _load_extra_file_map()
        self._yaml = YAML(typ="rt")
        self._yaml.preserve_quotes = True
        self._yaml.width = None
        self._yaml.indent(mapping=2, sequence=4, offset=2)
        self._yaml.representer.add_representer(type(None), represent_none)

    def _resolve_params_dir(self) -> Path | None:
        return self._params_dir

    def _resolve_qubit_label(self, _qid: str) -> str | None:
        return self._label

    def _file_lock(self, path: Path) -> FileLock:
        # Reuse the instance so snapshot/update/verify/restore can re-enter locks.
        if path not in self._locks:
            self._locks[path] = FileLock(path, timeout=10)
        return self._locks[path]

    @contextlib.contextmanager
    def applied(self, qid: str, parameters: dict[str, Any]) -> Iterator[None]:
        """Hold target locks through verification and the caller's DB commit.

        Unmapped diagnostic outputs stay in the database. Restore the original
        files if either YAML persistence or the caller's commit fails.
        """
        mapped = {
            key: value
            for key, value in parameters.items()
            if self._resolve_file_names({key: value})
        }
        if not mapped:
            yield
            return
        params_dir = self._resolve_params_dir()
        if params_dir is None or not params_dir.is_dir():
            raise ValueError("Qubex params directory is not available")
        targets = self._resolve_file_names(mapped)
        for key, param in mapped.items():
            value = self._extract_value(param)
            if value is None or (isinstance(value, float) and not math.isfinite(value)):
                raise ValueError(f"Parameter '{key}' has no finite YAML value")
        with contextlib.ExitStack() as stack:
            for name in sorted(targets):
                stack.enter_context(self._file_lock(params_dir / (name + ".lock")))
            snapshot = self.snapshot(qid, mapped)
            try:
                self.update(qid, mapped)
                if self.verify(qid, mapped) != targets:
                    raise RuntimeError("Backend verification did not cover all target files")
                yield
            except Exception:
                try:
                    self.restore(snapshot)
                except Exception as exc:
                    raise RuntimeError("Manual update failed and YAML rollback failed") from exc
                raise

    def snapshot(self, _qid: str, output_parameters: dict[str, Any]) -> dict[str, bytes]:
        """Capture mapped parameter files before a multi-file update."""
        params_dir = self._resolve_params_dir()
        if params_dir is None:
            raise ValueError("Qubex params directory is not available")

        snapshots: dict[str, bytes] = {}
        for file_name in sorted(self._resolve_file_names(output_parameters)):
            file_path = params_dir / file_name
            if not file_path.exists():
                raise ValueError(f"Mapped params file does not exist: {file_name}")
            lock_path = file_path.with_suffix(file_path.suffix + ".lock")
            lock_path.touch(exist_ok=True)
            with self._file_lock(lock_path):
                snapshots[file_name] = file_path.read_bytes()
        return snapshots

    def update(self, qid: str, output_parameters: dict[str, Any]) -> set[str]:
        updated_files: set[str] = set()
        params_dir = self._resolve_params_dir()
        if params_dir is None:
            return updated_files

        label = self._resolve_qubit_label(qid)
        if label is None:
            return updated_files

        for key, param in output_parameters.items():
            value = self._extract_value(param)
            if value is None:
                continue
            for file_name in sorted(self._resolve_file_names({key: param})):
                if self._update_yaml(params_dir / file_name, label, value):
                    updated_files.add(file_name)

        return updated_files

    def verify(self, qid: str, output_parameters: dict[str, Any]) -> set[str]:
        """Read back every mapped YAML value and return verified file names."""
        params_dir = self._resolve_params_dir()
        if params_dir is None:
            raise ValueError("Qubex params directory is not available")
        label = self._resolve_qubit_label(qid)
        if label is None:
            raise ValueError(f"Could not resolve Qubex label for qid={qid}")

        verified: set[str] = set()
        for key, param in output_parameters.items():
            expected = self._extract_value(param)
            if expected is None:
                raise ValueError(f"Parameter '{key}' has no verifiable value")
            file_names: list[str] = []
            mapped = self._param_file_map.get(key)
            if mapped is not None:
                file_names.append(mapped)
            file_names.extend(self._extra_file_map.get(key, []))
            if not file_names:
                raise ValueError(f"Parameter '{key}' has no params YAML mapping")

            for file_name in file_names:
                file_path = params_dir / file_name
                if not file_path.exists():
                    raise ValueError(f"Mapped params file does not exist: {file_name}")
                lock_path = file_path.with_suffix(file_path.suffix + ".lock")
                lock_path.touch(exist_ok=True)
                with self._file_lock(lock_path), file_path.open("r") as fp:
                    data = self._yaml.load(fp) or {}
                section = data.get("data") if isinstance(data, dict) else None
                actual = section.get(label) if isinstance(section, dict) else None
                if not self._values_equal(actual, expected):
                    raise ValueError(
                        f"Backend verification failed for {file_name}:{label}: "
                        f"expected {expected!r}, got {actual!r}"
                    )
                verified.add(file_name)
        return verified

    def restore(self, snapshot: dict[str, bytes]) -> None:
        """Atomically restore parameter files captured before an update."""
        params_dir = self._resolve_params_dir()
        if params_dir is None:
            raise ValueError("Qubex params directory is not available")

        for file_name, content in snapshot.items():
            file_path = params_dir / file_name
            lock_path = file_path.with_suffix(file_path.suffix + ".lock")
            lock_path.touch(exist_ok=True)
            with self._file_lock(lock_path):
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    dir=params_dir,
                    suffix=".tmp",
                    delete=False,
                ) as tmp_fp:
                    tmp_path = Path(tmp_fp.name)
                    tmp_fp.write(content)
                try:
                    os.replace(tmp_path, file_path)
                finally:
                    with contextlib.suppress(FileNotFoundError):
                        tmp_path.unlink()

    def _resolve_file_names(self, output_parameters: dict[str, Any]) -> set[str]:
        file_names: set[str] = set()
        for parameter_name in output_parameters:
            mapped = self._param_file_map.get(parameter_name)
            if mapped is not None:
                file_names.add(mapped)
            file_names.update(self._extra_file_map.get(parameter_name, []))
        return file_names

    @staticmethod
    def _extract_value(param: Any) -> float | int | str | None:
        if isinstance(param, ParameterModel):
            return YamlParamsUpdater._coerce_value(param.value)

        if isinstance(param, dict) and "value" in param:
            return YamlParamsUpdater._coerce_value(param.get("value"))

        value = getattr(param, "value", param)
        return YamlParamsUpdater._coerce_value(value)

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

        with self._file_lock(lock_path):
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
