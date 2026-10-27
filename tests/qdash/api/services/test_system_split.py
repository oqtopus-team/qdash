"""Run entry points reject targets that span Qubex Systems."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest
import yaml
from fastapi import HTTPException

from qdash.api.services.system_split import (
    SYSTEM_SPLIT_CODE,
    ensure_single_system,
    targets_from_parameters,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def two_systems(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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


def test_targets_inside_one_system_pass(two_systems: None) -> None:
    assert ensure_single_system("chip-1", ["1", "5"]) == "chip-1"
    assert ensure_single_system("chip-1", ["9-10"]) == "chip-1-quel3"
    assert ensure_single_system("chip-1", [], mux_ids=[2, 3]) == "chip-1-quel3"
    assert ensure_single_system("chip-1", []) is None
    assert ensure_single_system("", ["1"]) is None


def test_targets_spanning_systems_are_rejected_with_the_split(two_systems: None) -> None:
    with pytest.raises(HTTPException) as info:
        ensure_single_system("chip-1", ["1", "9"])

    assert info.value.status_code == 400
    detail = cast("dict[str, Any]", info.value.detail)
    assert detail["code"] == SYSTEM_SPLIT_CODE
    assert detail["chip_id"] == "chip-1"
    assert detail["systems"] == {"chip-1": ["1"], "chip-1-quel3": ["9"]}
    assert "message" in detail


def test_couplings_crossing_a_system_boundary_are_rejected(two_systems: None) -> None:
    with pytest.raises(HTTPException) as info:
        ensure_single_system("chip-1", ["7-8"])
    assert info.value.status_code == 400
    assert cast("dict[str, Any]", info.value.detail)["code"] == SYSTEM_SPLIT_CODE


def test_unreadable_configuration_does_not_block(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "qdash.common.config.qubex_layout.resolve_config_base_path", lambda: tmp_path
    )
    assert ensure_single_system("chip-1", ["1", "9"]) is None


def test_targets_from_parameters_reads_qid_qids_and_mux_ids() -> None:
    assert targets_from_parameters({"qid": " 3 ", "qids": ["4", 5]}) == (["3", "4", "5"], None)
    assert targets_from_parameters({"mux_ids": ["1", 2]}) == ([], [1, 2])
    assert targets_from_parameters({"mux_ids": ["x"]}) == ([], None)
    assert targets_from_parameters({}) == ([], None)
