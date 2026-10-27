"""Common params files are projected to every System of the chip; backend files are not."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast
from unittest.mock import MagicMock, patch

import yaml

from qdash.common.config.qubex_layout import QubexLayout
from qdash.workflow.engine.params_updater import _QubexParamsUpdater
from tests.qdash.api.services.chip._trees import write_shared_tree

if TYPE_CHECKING:
    from pathlib import Path


def _updater(root: Path, system_id: str) -> _QubexParamsUpdater:
    layout = QubexLayout.detect(root)
    backend = MagicMock()
    backend.config = {
        "project_id": "project-1",
        "chip_id": "src16",
        "system_id": system_id,
        "params_dir": str(layout.params_dir(system_id)),
    }
    backend.get_instance.side_effect = AssertionError("should not connect")
    backend.is_connected = False
    return _QubexParamsUpdater(backend, chip_id="src16")


def _data(path: Path) -> dict[Any, Any]:
    return cast("dict[Any, Any]", yaml.safe_load(path.read_text())["data"])


def test_common_values_reach_every_system_and_backend_values_stay_local(tmp_path: Path) -> None:
    write_shared_tree(tmp_path)
    layout = QubexLayout.detect(tmp_path)
    for system_id in ("src16", "src16-quel3"):
        (layout.params_dir(system_id) / "qubit_frequency.yaml").write_text("data:\n  Q01: 4.0\n")
    updater = _updater(tmp_path, "src16")

    with (
        patch("qdash.common.config.qubex_layout.QubexLayout.detect", return_value=layout),
        patch("qdash.common.domain.qubit._get_chip_size", return_value=16),
    ):
        updated = updater.update(
            "1", {"qubit_frequency": {"value": 4.5}, "capture_delay": {"value": 9}}
        )

    assert "qubit_frequency.yaml" in updated
    assert _data(layout.params_dir("src16") / "qubit_frequency.yaml")["Q01"] == 4.5
    assert _data(layout.params_dir("src16-quel3") / "qubit_frequency.yaml")["Q01"] == 4.5
    # capture_delay is backend-specific: the other System's file keeps its own values.
    assert _data(layout.params_dir("src16-quel3") / "capture_delay.yaml") == dict.fromkeys(
        range(4), 8
    )


def test_restore_returns_projected_files_to_their_snapshot(tmp_path: Path) -> None:
    write_shared_tree(tmp_path)
    layout = QubexLayout.detect(tmp_path)
    other = layout.params_dir("src16-quel3") / "t1.yaml"
    other.write_text("data:\n  Q01: 10.0\n")
    updater = _updater(tmp_path, "src16")
    params = {"t1": {"value": 12.0}, "t2_echo": {"value": 3.0}}

    with (
        patch("qdash.common.config.qubex_layout.QubexLayout.detect", return_value=layout),
        patch("qdash.common.domain.qubit._get_chip_size", return_value=16),
    ):
        snapshot = updater.snapshot("1", params)
        updater.update("1", params)
        assert _data(other)["Q01"] == 12.0
        assert (layout.params_dir("src16-quel3") / "t2_echo.yaml").exists()
        updater.restore(snapshot)

    assert _data(other)["Q01"] == 10.0
    assert not (layout.params_dir("src16-quel3") / "t2_echo.yaml").exists()
    assert not (layout.params_dir("src16") / "t2_echo.yaml").exists()


def test_legacy_layout_projects_nothing(tmp_path: Path) -> None:
    (tmp_path / "src16" / "config").mkdir(parents=True)
    params = tmp_path / "src16" / "params"
    params.mkdir()
    layout = QubexLayout.detect(tmp_path)
    updater = _updater(tmp_path, "src16")

    with (
        patch("qdash.common.config.qubex_layout.QubexLayout.detect", return_value=layout),
        patch("qdash.common.domain.qubit._get_chip_size", return_value=16),
    ):
        updater.update("1", {"t1": {"value": 12.0}})

    assert _data(params / "t1.yaml")["Q01"] == 12.0
    assert updater._other_system_dirs() == []
