"""Two-qubit steps skip couplings that span Systems and record them in the note."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
import yaml

from qdash.workflow.service.steps.two_qubit import CROSS_SYSTEM_NOTE_KEY, drop_cross_system_pairs

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> MagicMock:
    config = tmp_path / "config"
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
    monkeypatch.setattr(
        "qdash.common.config.qubex_layout.resolve_config_base_path", lambda: tmp_path
    )
    monkeypatch.setattr("qdash.workflow.service.steps.two_qubit.get_run_logger", MagicMock)
    svc = MagicMock()
    svc.chip_id = "chip-1"
    return svc


def test_cross_system_pairs_are_dropped_and_noted(service: MagicMock) -> None:
    groups = [[("0", "1"), ("7", "8")], [("12", "13")], [("3", "12")]]

    kept, excluded = drop_cross_system_pairs(service, groups, known_excluded=["5-9"])

    assert kept == [[("0", "1")], [("12", "13")]]
    assert excluded == ["5-9", "7-8", "3-12"]
    service.execution_service.update_note.assert_called_once_with(
        CROSS_SYSTEM_NOTE_KEY, ["5-9", "7-8", "3-12"]
    )


def test_nothing_to_drop_leaves_the_note_alone(service: MagicMock) -> None:
    groups = [[("0", "1")], [("12", "13")]]

    assert drop_cross_system_pairs(service, groups) == (groups, [])
    service.execution_service.update_note.assert_not_called()
