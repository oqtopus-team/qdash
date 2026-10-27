"""Tests for QubexBackend parameter synchronization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest
import yaml

from qdash.workflow.engine.backend.qubex import QubexBackend

if TYPE_CHECKING:
    from pathlib import Path


class FakeQubitRepo:
    """Fake qubit repository returning DB-shaped calibration data."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def get_calibration_data(self, *, project_id: str, chip_id: str, qid: str) -> dict[str, Any]:
        self.calls.append((project_id, chip_id, qid))
        return {"control_amplitude": {"value": float(qid)}}


class RecordingUpdater:
    """Record params updates requested by the backend."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def update(self, qid: str, output_parameters: dict[str, Any]) -> None:
        self.calls.append((qid, output_parameters))


def test_sync_qubit_params_from_db_splits_coupling_qids(monkeypatch) -> None:
    """Coupling sessions must sync each participating qubit before Qubex connects."""
    repo = FakeQubitRepo()
    updater = RecordingUpdater()

    monkeypatch.setattr(
        "qdash.repository.qubit.MongoQubitCalibrationRepository",
        lambda: repo,
    )
    monkeypatch.setattr(
        "qdash.workflow.engine.params_updater.get_params_updater",
        lambda backend, chip_id: updater,
    )

    backend = QubexBackend(
        {
            "project_id": "project-1",
            "chip_id": "64Qv2",
            "qids": ["47-46", "44-45"],
        }
    )

    backend._sync_qubit_params_from_db(project_id="project-1", chip_id="64Qv2")

    assert repo.calls == [
        ("project-1", "64Qv2", "44"),
        ("project-1", "64Qv2", "45"),
        ("project-1", "64Qv2", "46"),
        ("project-1", "64Qv2", "47"),
    ]
    assert updater.calls == [
        ("44", {"control_amplitude": {"value": 44.0}}),
        ("45", {"control_amplitude": {"value": 45.0}}),
        ("46", {"control_amplitude": {"value": 46.0}}),
        ("47", {"control_amplitude": {"value": 47.0}}),
    ]


def test_connect_passes_readout_duration_to_experiment(monkeypatch: Any) -> None:
    experiment = MagicMock()
    factory = MagicMock(return_value=experiment)
    monkeypatch.setattr("qubex.Experiment", factory)
    backend = QubexBackend(
        {
            "task_type": "qubit",
            "qids": ["0"],
            "chip_id": "chip-1",
            "classifier_dir": "classifiers",
            "readout_duration": 2048.0,
        }
    )

    backend.connect()

    assert factory.call_args.kwargs["readout_duration"] == 2048.0
    experiment.connect.assert_called_once_with()


def _write_shared_tree(root: Path) -> None:
    config = root / "config"
    config.mkdir(parents=True)
    (config / "chip.yaml").write_text(yaml.safe_dump({"chip-1": {"n_qubits": 16}}))
    (config / "system.yaml").write_text(
        yaml.safe_dump(
            {
                "chip-1": {"chip_id": "chip-1", "backend": "quel1"},
                "chip-1-quel3": {"chip_id": "chip-1", "backend": "quel3"},
            }
        )
    )
    rows = lambda *ids: [{"mux": m, "ctrl": [f"C{m}-0"], "read_out": f"R{m}-0"} for m in ids]  # noqa: E731
    (config / "wiring.yaml").write_text(
        yaml.safe_dump({"chip-1": rows(0, 1), "chip-1-quel3": rows(2, 3)})
    )


def test_connect_selects_the_system_by_target_and_passes_system_id(
    monkeypatch: Any, tmp_path: Path
) -> None:
    _write_shared_tree(tmp_path)
    monkeypatch.setattr(
        "qdash.common.config.qubex_layout.resolve_config_base_path", lambda: tmp_path
    )
    experiment = MagicMock()
    factory = MagicMock(return_value=experiment)
    monkeypatch.setattr("qubex.Experiment", factory)
    backend = QubexBackend(
        {"task_type": "qubit", "qids": ["9"], "chip_id": "chip-1", "classifier_dir": "cls"}
    )

    backend.connect()

    kwargs = factory.call_args.kwargs
    assert "chip_id" not in kwargs
    assert kwargs["system_id"] == "chip-1-quel3"
    assert kwargs["config_dir"] == str(tmp_path / "config")
    assert kwargs["params_dir"] == str(tmp_path / "params" / "chip-1-quel3")
    assert backend.config["system_id"] == "chip-1-quel3"


def test_connect_refuses_targets_that_span_systems(monkeypatch: Any, tmp_path: Path) -> None:
    from qdash.common.config.system_catalog import SystemSplitRequired

    _write_shared_tree(tmp_path)
    monkeypatch.setattr(
        "qdash.common.config.qubex_layout.resolve_config_base_path", lambda: tmp_path
    )
    monkeypatch.setattr("qubex.Experiment", MagicMock())
    backend = QubexBackend(
        {"task_type": "qubit", "qids": ["1", "9"], "chip_id": "chip-1", "classifier_dir": "cls"}
    )

    with pytest.raises(SystemSplitRequired):
        backend.connect()


def test_connect_without_a_readable_tree_uses_the_chip_as_system(
    monkeypatch: Any, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "qdash.common.config.qubex_layout.resolve_config_base_path", lambda: tmp_path
    )
    factory = MagicMock(return_value=MagicMock())
    monkeypatch.setattr("qubex.Experiment", factory)
    backend = QubexBackend(
        {"task_type": "qubit", "qids": ["0"], "chip_id": "chip-1", "classifier_dir": "cls"}
    )

    backend.connect()

    assert factory.call_args.kwargs["system_id"] == "chip-1"
    assert factory.call_args.kwargs["params_dir"] == str(tmp_path / "chip-1" / "params")
