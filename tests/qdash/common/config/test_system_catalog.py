"""SystemCatalog maps a QDash chip to its Qubex Systems in both layouts."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from qdash.common.config.qubex_layout import LayoutKind, QubexLayout
from qdash.common.config.system_catalog import (
    CrossSystemCoupling,
    SystemCatalog,
    SystemSplitRequired,
    default_system_id,
)


def _rows(*mux_ids: int, box: str = "A") -> list[dict[str, Any]]:
    return [
        {
            "mux": mux,
            "ctrl": [f"C{box}{mux}-0"],
            "read_out": f"R{box}{mux}-0",
            "read_in": f"R{box}{mux}-1",
        }
        for mux in mux_ids
    ]


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


@pytest.fixture
def legacy(tmp_path: Path) -> QubexLayout:
    """Legacy tree: chip-keyed wiring, no system.yaml (today's 64Qv3)."""
    _write(tmp_path / "64Qv3" / "config" / "chip.yaml", {"64Qv3": {"n_qubits": 64}})
    _write(tmp_path / "64Qv3" / "config" / "wiring.yaml", {"64Qv3": _rows(0, 1, 2, 3)})
    return QubexLayout.detect(tmp_path)


@pytest.fixture
def shared(tmp_path: Path) -> QubexLayout:
    """Shared tree with two chips; 144Qv3 is driven by a quel1 and a quel3 System."""
    _write(
        tmp_path / "config" / "chip.yaml",
        {
            "144Qv3": {"n_qubits": 144, "topology": {"type": "square_lattice", "mux_size": 4}},
            "16Qv1": {"n_qubits": 16},
        },
    )
    _write(
        tmp_path / "config" / "system.yaml",
        {
            "144Qv3": {
                "chip_id": "144Qv3",
                "backend": "quel1",
                "quel1": {"clock_master": "10.0.0.1"},
            },
            "144Qv3-quel3": {"chip_id": "144Qv3", "backend": "quel3", "quel3": {"endpoint": "x"}},
            "16Qv1": {"chip_id": "16Qv1", "backend": "quel1"},
        },
    )
    _write(
        tmp_path / "config" / "wiring.yaml",
        {
            "144Qv3": _rows(0, 1, 2, box="A"),
            "144Qv3-quel3": _rows(3, 4, box="B"),
            "16Qv1": _rows(0, 1, 2, 3, box="S"),
        },
    )
    return QubexLayout.detect(tmp_path)


def test_legacy_tree_has_one_implicit_system_named_like_the_chip(legacy: QubexLayout) -> None:
    catalog = SystemCatalog(legacy, "64Qv3")

    assert catalog.is_implicit
    assert catalog.system_ids() == ["64Qv3"]
    entry = catalog.systems()[0]
    assert (entry.chip_id, entry.driver, entry.backend) == ("64Qv3", "qubex", "quel1")
    assert entry.mux_ids == frozenset({0, 1, 2, 3})
    assert catalog.default_system_id() == "64Qv3"
    assert catalog.mux_size() == 4
    assert catalog.resolve(["0", "5", "6-7"]) == {"64Qv3": ["0", "5", "6-7"]}
    assert catalog.resolve_single([]) == "64Qv3"
    assert catalog.coupling_feasible("0", "15")


def test_legacy_group_keyed_wiring_is_flattened_for_an_implicit_system(tmp_path: Path) -> None:
    _write(tmp_path / "chip-1" / "config" / "wiring.yaml", {"A": _rows(0, 1), "B": _rows(2)})

    catalog = SystemCatalog(QubexLayout(tmp_path, LayoutKind.LEGACY), "chip-1")

    assert [row["mux"] for row in catalog.wiring_rows()] == [0, 1, 2]
    assert catalog.qid_to_mux()["9"] == 2


def test_legacy_single_entry_system_yaml_keeps_its_backend(tmp_path: Path) -> None:
    _write(tmp_path / "chip-1" / "config" / "wiring.yaml", {"chip-1": _rows(0)})
    _write(
        tmp_path / "chip-1" / "config" / "system.yaml", {"chip_id": "chip-1", "backend": "quel3"}
    )

    catalog = SystemCatalog(QubexLayout(tmp_path, LayoutKind.LEGACY), "chip-1")

    assert catalog.is_implicit
    assert catalog.systems()[0].backend == "quel3"
    assert catalog.systems()[0].system_id == "chip-1"


def test_shared_tree_lists_only_the_systems_of_the_chip(shared: QubexLayout) -> None:
    catalog = SystemCatalog(shared, "144Qv3")

    assert catalog.system_ids() == ["144Qv3", "144Qv3-quel3"]
    assert catalog.entry("144Qv3-quel3").backend == "quel3"
    assert catalog.entry("144Qv3-quel3").mux_ids == frozenset({3, 4})
    assert [row["mux"] for row in catalog.wiring_rows()] == [0, 1, 2, 3, 4]
    assert catalog.default_system_id() == "144Qv3"
    assert catalog.qubex_chip_id == "144Qv3"
    # Rows of 16Qv1 never leak into this chip, so MUX 0 is not duplicated.
    assert catalog.system_of_mux(0) == "144Qv3"
    assert catalog.system_of_mux(3) == "144Qv3-quel3"


def test_shared_tree_resolves_targets_per_system(shared: QubexLayout) -> None:
    catalog = SystemCatalog(shared, "144Qv3")

    assert catalog.resolve(["1", "13", "0-1", "16-17"]) == {
        "144Qv3": ["1", "0-1"],
        "144Qv3-quel3": ["13", "16-17"],
    }
    assert catalog.resolve_single(["4", "5-6"]) == "144Qv3"
    assert catalog.resolve_single([], mux_ids=[3, 4]) == "144Qv3-quel3"
    assert catalog.coupling_feasible("8", "9")
    assert not catalog.coupling_feasible("11", "12")

    with pytest.raises(SystemSplitRequired) as split:
        catalog.resolve_single(["1", "13"])
    assert split.value.assignment == {"144Qv3": ["1"], "144Qv3-quel3": ["13"]}

    with pytest.raises(CrossSystemCoupling):
        catalog.resolve(["11-12"])

    with pytest.raises(KeyError):
        catalog.system_of_qid("40")


def test_system_named_like_the_qdash_chip_wins_as_an_alias(tmp_path: Path) -> None:
    """A second QDash instance owning only the quel3 System uses chip_id 144Qv3-quel3."""
    _write(tmp_path / "config" / "chip.yaml", {"144Qv3": {"n_qubits": 144}})
    _write(
        tmp_path / "config" / "system.yaml",
        {
            "144Qv3": {"chip_id": "144Qv3", "backend": "quel1"},
            "144Qv3-quel3": {"chip_id": "144Qv3", "backend": "quel3"},
        },
    )
    _write(
        tmp_path / "config" / "wiring.yaml", {"144Qv3": _rows(0, 1), "144Qv3-quel3": _rows(2, 3)}
    )

    catalog = SystemCatalog(QubexLayout.detect(tmp_path), "144Qv3-quel3")

    assert catalog.system_ids() == ["144Qv3-quel3"]
    assert catalog.qubex_chip_id == "144Qv3"
    assert catalog.default_system_id() == "144Qv3-quel3"
    assert catalog.mux_ids() == [2, 3]
    assert catalog.resolve_single(["8", "15"]) == "144Qv3-quel3"
    assert QubexLayout.detect(tmp_path).params_dir(catalog.default_system_id()) == (
        tmp_path / "params" / "144Qv3-quel3"
    )


def test_mux_wired_in_two_systems_is_a_configuration_error(tmp_path: Path) -> None:
    _write(tmp_path / "config" / "chip.yaml", {"c": {"n_qubits": 16}})
    _write(
        tmp_path / "config" / "system.yaml",
        {
            "c": {"chip_id": "c", "backend": "quel1"},
            "c-quel3": {"chip_id": "c", "backend": "quel3"},
        },
    )
    _write(tmp_path / "config" / "wiring.yaml", {"c": _rows(0, 1), "c-quel3": _rows(1, 2)})

    with pytest.raises(ValueError, match="MUX 1 is wired in Systems"):
        SystemCatalog(QubexLayout.detect(tmp_path), "c").wiring_rows()


def test_shared_tree_wiring_may_fall_back_to_the_chip_key(tmp_path: Path) -> None:
    _write(tmp_path / "config" / "chip.yaml", {"c": {"n_qubits": 16, "topology": {"mux_size": 2}}})
    _write(tmp_path / "config" / "system.yaml", {"c-sys": {"chip_id": "c", "backend": "quel1"}})
    _write(tmp_path / "config" / "wiring.yaml", {"c": _rows(0, 1)})

    catalog = SystemCatalog(QubexLayout.detect(tmp_path), "c")

    assert catalog.system_ids() == ["c-sys"]
    assert catalog.mux_size() == 2
    assert catalog.mux_of("3") == 1
    assert catalog.qid_to_mux() == {"0": 0, "1": 0, "2": 1, "3": 1}
    assert catalog.default_system_id() == "c-sys"


def test_unknown_chip_in_a_shared_tree_is_reported(tmp_path: Path) -> None:
    _write(tmp_path / "config" / "chip.yaml", {"c": {"n_qubits": 16}})
    _write(tmp_path / "config" / "system.yaml", {"c": {"chip_id": "c"}})
    _write(tmp_path / "config" / "wiring.yaml", {"c": _rows(0)})

    with pytest.raises(LookupError, match=r"neither system\.yaml nor chip\.yaml"):
        SystemCatalog(QubexLayout.detect(tmp_path), "other").systems()


def test_missing_wiring_file_is_reported(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        SystemCatalog(QubexLayout(tmp_path, LayoutKind.LEGACY), "chip-1").wiring_rows()


def test_resources_of_a_system_cover_its_muxes(shared: QubexLayout) -> None:
    catalog = SystemCatalog(shared, "144Qv3")

    resources = catalog.resources_of("144Qv3-quel3")

    assert "mux:3" in resources and "mux:4" in resources
    assert "channel:CB3-0" in resources
    assert "module:read_out:RB4" in resources
    assert not any(resource.startswith("mux:0") for resource in resources)


def test_default_system_id_falls_back_to_the_chip_when_unreadable(tmp_path: Path) -> None:
    layout = QubexLayout(tmp_path, LayoutKind.LEGACY)

    assert default_system_id(layout, "fresh-chip") == "fresh-chip"
