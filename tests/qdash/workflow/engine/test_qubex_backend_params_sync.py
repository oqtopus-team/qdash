"""Tests for QubexBackend parameter synchronization."""

from __future__ import annotations

from typing import Any

from qdash.workflow.engine.backend.qubex import QubexBackend


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
