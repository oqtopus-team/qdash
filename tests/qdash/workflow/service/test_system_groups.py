"""Waves of MUX groups per Qubex System."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import yaml

from qdash.common.config.qubex_layout import QubexLayout
from qdash.common.config.system_catalog import SystemCatalog
from qdash.workflow.service.system_groups import (
    SystemWave,
    plan_system_waves,
    system_of_group,
)


def _write_shared_tree(root: Path, *, backends: tuple[str, str] = ("quel1", "quel3")) -> None:
    config = root / "config"
    config.mkdir(parents=True)
    (config / "chip.yaml").write_text(yaml.safe_dump({"chip-1": {"n_qubits": 16}}))
    (config / "system.yaml").write_text(
        yaml.safe_dump(
            {
                "chip-1": {"chip_id": "chip-1", "backend": backends[0]},
                "chip-1-b": {"chip_id": "chip-1", "backend": backends[1]},
            }
        )
    )
    rows = lambda *ids: [{"mux": m, "ctrl": [f"C{m}-0"], "read_out": f"R{m}-0"} for m in ids]  # noqa: E731
    (config / "wiring.yaml").write_text(
        yaml.safe_dump({"chip-1": rows(0, 1), "chip-1-b": rows(2, 3)})
    )


if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def catalog(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SystemCatalog:
    _write_shared_tree(tmp_path)
    monkeypatch.setattr(
        "qdash.common.config.qubex_layout.resolve_config_base_path", lambda: tmp_path
    )
    return SystemCatalog(QubexLayout.detect(), "chip-1")


def test_system_of_group_names_the_system_and_rejects_spanning_groups(
    catalog: SystemCatalog,
) -> None:
    assert system_of_group(catalog, ["0", "1", "2", "3"]) == "chip-1"
    assert system_of_group(catalog, ["12"]) == "chip-1-b"
    assert system_of_group(catalog, []) is None
    with pytest.raises(ValueError, match="spans Systems"):
        system_of_group(catalog, ["1", "9"])


def test_systems_with_different_backends_share_a_wave(catalog: SystemCatalog) -> None:
    waves = plan_system_waves(
        [["0", "1"], ["8", "9"], ["4", "5"]], catalog, parallel_same_backend=False
    )

    assert len(waves) == 1
    assert set(waves[0].system_ids) == {"chip-1", "chip-1-b"}
    assert waves[0].groups == [["0", "1"], ["4", "5"], ["8", "9"]]
    assert waves[0].group_system_ids == ["chip-1", "chip-1", "chip-1-b"]
    assert waves[0].qids == ["0", "1", "4", "5", "8", "9"]
    assert waves[0].worker_kwargs("group_system_ids") == {
        "group_system_ids": ["chip-1", "chip-1", "chip-1-b"]
    }


def test_systems_with_the_same_backend_run_in_separate_waves_unless_allowed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _write_shared_tree(tmp_path, backends=("quel1", "quel1"))
    monkeypatch.setattr(
        "qdash.common.config.qubex_layout.resolve_config_base_path", lambda: tmp_path
    )
    catalog = SystemCatalog(QubexLayout.detect(), "chip-1")
    groups = [["0", "1"], ["8", "9"]]

    serial = plan_system_waves(groups, catalog, parallel_same_backend=False)
    assert [wave.system_ids for wave in serial] == [("chip-1",), ("chip-1-b",)]

    parallel = plan_system_waves(groups, catalog, parallel_same_backend=True)
    assert len(parallel) == 1
    assert set(parallel[0].system_ids) == {"chip-1", "chip-1-b"}


def test_flag_defaults_to_workflow_yaml(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, catalog: SystemCatalog
) -> None:
    monkeypatch.setattr(
        "qdash.workflow.service.system_groups.parallel_same_backend_enabled", lambda: False
    )
    assert len(plan_system_waves([["0"], ["8"]], catalog)) == 1  # different backends anyway


def test_unknown_chip_keeps_one_untagged_wave(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "qdash.common.config.qubex_layout.resolve_config_base_path", lambda: tmp_path
    )
    catalog = SystemCatalog(QubexLayout.detect(), "missing-chip")

    waves = plan_system_waves([["0", "1"], ["8", "9"]], catalog, parallel_same_backend=False)

    assert waves == [SystemWave((), [["0", "1"], ["8", "9"]], [None, None])]
    assert waves[0].worker_kwargs("group_system_ids") == {}
