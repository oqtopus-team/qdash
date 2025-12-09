from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

from qdash.datamodel.task import OutputParameterModel
from qdash.workflow.worker.flows.push_props.formatter import represent_none
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.base import BaseBackend


class ParamsUpdater(Protocol):
    """Protocol for backend-specific parameter updaters."""

    def update(self, qid: str, output_parameters: dict[str, Any]) -> None: ...


def get_params_updater(backend: BaseBackend, chip_id: str | None = None) -> ParamsUpdater | None:
    """Resolve a backend-specific params updater for the given backend."""
    qubex_updater = _resolve_qubex_updater(backend, chip_id)
    if qubex_updater is not None:
        return qubex_updater
    return None


def _resolve_qubex_updater(backend: BaseBackend, chip_id: str | None) -> ParamsUpdater | None:
    try:
        from qdash.workflow.engine.backend.qubex import QubexBackend
    except ImportError:
        return None

    if not isinstance(backend, QubexBackend):
        return None

    return _QubexParamsUpdater(backend, chip_id)


class _QubexParamsUpdater:
    """Synchronize calibration results with Qubex params YAML files."""

    PARAM_FILE_MAP: dict[str, str] = {
        "t1": "t1.yaml",
        "t2_echo": "t2_echo.yaml",
        "t2_star": "t2_star.yaml",
        "readout_amplitude": "readout_amplitude.yaml",
        "resonator_frequency": "readout_frequency.yaml",
        "readout_frequency": "readout_frequency.yaml",
        "control_amplitude": "control_amplitude.yaml",
        "qubit_frequency": "qubit_frequency.yaml",
        "x90_gate_fidelity": "x90_gate_fidelity.yaml",
        "x180_gate_fidelity": "x180_gate_fidelity.yaml",
        "zx90_gate_fidelity": "zx90_gate_fidelity.yaml",
        "average_gate_fidelity": "average_gate_fidelity.yaml",
        "average_readout_fidelity": "average_readout_fidelity.yaml",
    }

    def __init__(self, backend: Any, chip_id: str | None) -> None:
        self._backend = backend
        self._chip_id = chip_id
        self._yaml = YAML(typ="rt")
        self._yaml.preserve_quotes = True
        self._yaml.width = None
        self._yaml.indent(mapping=2, sequence=4, offset=2)
        self._yaml.representer.add_representer(type(None), represent_none)

    def update(self, qid: str, output_parameters: dict[str, Any]) -> None:
        params_dir = self._resolve_params_dir()
        if params_dir is None:
            return

        label = self._resolve_qubit_label(qid)
        if label is None:
            return

        for key, param in output_parameters.items():
            file_name = self.PARAM_FILE_MAP.get(key)
            if file_name is None:
                continue

            value = self._extract_value(param)
            if value is None:
                continue

            file_path = params_dir / file_name
            self._update_yaml(file_path, label, value)

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
            Path(f"/app/config/qubex/{chip_id}/params"),
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

        try:
            experiment = self._backend.get_instance()
        except Exception:
            return None

        get_label = getattr(experiment, "get_qubit_label", None)
        if callable(get_label):
            return cast(str, get_label(index))
        return None

    @staticmethod
    def _extract_value(param: Any) -> float | int | str | None:
        if isinstance(param, OutputParameterModel):
            return _QubexParamsUpdater._coerce_value(param.value)

        value = getattr(param, "value", param)
        return _QubexParamsUpdater._coerce_value(value)

    @staticmethod
    def _coerce_value(value: Any) -> float | int | str | None:
        if value is None:
            return None

        if hasattr(value, "item"):
            try:
                value = value.item()
            except Exception:
                pass

        if isinstance(value, (int, float)):
            numeric = float(value)
            if numeric != numeric:  # NaN guard
                return None
            return numeric

        return value

    def _update_yaml(self, file_path: Path, qubit_label: str, value: float | int | str) -> None:
        if not file_path.exists():
            return

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
            return

        if isinstance(section, CommentedMap):
            self._set_ordered(section, qubit_label, value)
        else:
            section[qubit_label] = value

        with file_path.open("w") as fp:
            self._yaml.dump(data, fp)

    @staticmethod
    def _values_equal(current: Any, new: Any) -> bool:
        if current is None and new is None:
            return True
        if isinstance(current, (int, float)) and isinstance(new, (int, float)):
            return abs(float(current) - float(new)) <= 1e-9
        return current == new

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
