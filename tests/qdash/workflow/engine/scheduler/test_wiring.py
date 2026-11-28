"""Both schedulers load ``wiring.yaml`` through one shared loader.

The loader supports the chip-keyed and the group-keyed formats, an explicit
path or the default QubexPaths path, and each scheduler caches the result per
instance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

from qdash.common.mux_mapping import MuxMapping
from qdash.workflow.engine.scheduler.cr_scheduler import CRScheduler
from qdash.workflow.engine.scheduler.cr_utils import build_qubit_to_mux_map
from qdash.workflow.engine.scheduler.one_qubit_scheduler import OneQubitScheduler
from qdash.workflow.engine.scheduler.wiring import load_wiring_config

if TYPE_CHECKING:
    from pathlib import Path

MUX_0 = {"mux": 0, "ctrl": [f"Q73A-{i}" for i in range(4)], "read_out": "Q73A-8"}
MUX_1 = {"mux": 1, "ctrl": [f"R21B-{i}" for i in range(4)], "read_out": "R21B-8"}
MUX_2 = {"mux": 2, "ctrl": [f"S159A-{i}" for i in range(4)], "read_out": "S159A-8"}


def _write(path: Path, data: dict[str, Any]) -> Path:
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


def test_chip_keyed_format_selects_only_that_chip(tmp_path: Path) -> None:
    path = _write(tmp_path / "wiring.yaml", {"other": [MUX_2], "chip-x": [MUX_0, MUX_1]})

    assert load_wiring_config("chip-x", path) == [MUX_0, MUX_1]
    assert load_wiring_config("chip-x", str(path)) == [MUX_0, MUX_1]


def test_group_keyed_format_flattens_groups_in_file_order(tmp_path: Path) -> None:
    path = _write(tmp_path / "wiring.yaml", {"B1": [MUX_2], "A2": [MUX_0, MUX_1]})

    assert load_wiring_config("chip-x", path) == [MUX_2, MUX_0, MUX_1]


def test_default_path_comes_from_qubex_paths(tmp_path: Path) -> None:
    path = _write(tmp_path / "wiring.yaml", {"chip-x": [MUX_0]})
    paths = MagicMock()
    paths.wiring_yaml.return_value = path

    with patch("qdash.workflow.engine.scheduler.wiring.get_qubex_paths", return_value=paths):
        assert load_wiring_config("chip-x", None) == [MUX_0]
    paths.wiring_yaml.assert_called_once_with("chip-x")


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    missing = tmp_path / "absent.yaml"

    with pytest.raises(FileNotFoundError, match="Wiring config not found"):
        load_wiring_config("chip-x", missing)


def _cr_scheduler(path: Path) -> CRScheduler:
    return CRScheduler(
        username="u",
        chip_id="chip-x",
        wiring_config_path=path,
        chip_repo=MagicMock(),
        mux_mapping=MuxMapping.legacy(),
    )


@pytest.mark.parametrize(
    "make",
    [
        lambda path: OneQubitScheduler(chip_id="chip-x", wiring_config_path=path),
        _cr_scheduler,
    ],
    ids=["one_qubit", "cr"],
)
def test_schedulers_cache_wiring_per_instance(tmp_path: Path, make: Any) -> None:
    path = _write(tmp_path / "wiring.yaml", {"A2": [MUX_0], "B1": [MUX_1]})
    scheduler = make(path)

    first = scheduler._load_wiring_config()
    path.unlink()

    assert first == [MUX_0, MUX_1]
    assert scheduler._load_wiring_config() is first
    with pytest.raises(FileNotFoundError):
        make(path)._load_wiring_config()


def test_one_qubit_mux_map_matches_cr_mux_map(tmp_path: Path) -> None:
    """The 1-qubit scheduler joins wiring to MUX membership like the CR scheduler."""
    mapping = MuxMapping.from_groups({0: ["0", "1", "2", "3"], 1: ["4", "5", "6", "7"]})
    path = _write(tmp_path / "wiring.yaml", {"chip-x": [MUX_0, MUX_1, MUX_2]})
    scheduler = OneQubitScheduler(chip_id="chip-x", wiring_config_path=path, mux_mapping=mapping)
    wiring = scheduler._load_wiring_config()

    qid_to_mux = scheduler._build_qubit_to_mux_map(wiring)

    assert qid_to_mux == build_qubit_to_mux_map(wiring, mapping)
    # MUX 2 is wired but not defined by the topology, so it has no qubits.
    assert set(qid_to_mux.values()) == {0, 1}
    assert scheduler._build_qubit_to_mux_map([]) is qid_to_mux
