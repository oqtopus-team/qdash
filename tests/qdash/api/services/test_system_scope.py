"""Chip and metrics endpoints narrow to one Qubex System through ``system_id``."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import yaml
from fastapi import HTTPException

from qdash.api.services.system_scope import SystemScope, resolve_system_scope

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


def test_no_system_means_the_whole_chip(two_systems: None) -> None:
    assert resolve_system_scope("chip-1", None) is None
    assert resolve_system_scope("chip-1", "  ") is None


def test_scope_lists_the_qubits_and_muxes_of_the_system(two_systems: None) -> None:
    scope = resolve_system_scope("chip-1", "chip-1-quel3")

    assert scope == SystemScope(
        chip_id="chip-1",
        system_id="chip-1-quel3",
        qids=frozenset(str(q) for q in range(8, 16)),
        mux_ids=frozenset({2, 3}),
    )
    assert scope.includes("9")
    assert scope.includes("9-10")
    assert not scope.includes("7-8")
    assert scope.filter_targets(None) == [str(q) for q in range(8, 16)]
    assert scope.filter_targets(["1", "9", "12-13"]) == ["9", "12-13"]


def test_unknown_system_is_404(two_systems: None) -> None:
    with pytest.raises(HTTPException) as info:
        resolve_system_scope("chip-1", "other")
    assert info.value.status_code == 404


def test_unconfigured_chip_is_404(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "qdash.common.config.qubex_layout.resolve_config_base_path", lambda: tmp_path
    )
    with pytest.raises(HTTPException) as info:
        resolve_system_scope("chip-1", "chip-1")
    assert info.value.status_code == 404
