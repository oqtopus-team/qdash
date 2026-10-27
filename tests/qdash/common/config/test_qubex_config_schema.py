"""The layout schemas accept the files QDash writes and reject malformed ones."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from qdash.common.config import qubex_config_schema as schema
from qdash.common.config.qubex_layout import LayoutKind, QubexLayout
from qdash.common.config.qubex_params_templates import templates_dir

REPO_ROOT = Path(__file__).resolve().parents[4]


def _shared(root: Path) -> QubexLayout:
    return QubexLayout(root, LayoutKind.SHARED)


def _legacy(root: Path) -> QubexLayout:
    return QubexLayout(root, LayoutKind.LEGACY)


@pytest.mark.parametrize(
    ("relpath", "expected"),
    [
        ("qubex-config.json", "manifest.schema.json"),
        ("config/chip.yaml", "chip.schema.json"),
        ("config/system.yaml", "system.v2.schema.json"),
        ("config/wiring.yaml", "wiring.schema.json"),
        ("config/box.yaml", "box.schema.json"),
        ("config/skew.yaml", "skew.schema.json"),
        ("config/cable_delay.yaml", None),
        ("params/64Qv3/t1.yaml", "params-file.schema.json"),
        ("params/64Qv3/measurement_defaults.yaml", None),
        ("calibration/64Qv3/calib_note.json", None),
        ("64Qv3/config/chip.yaml", None),
    ],
)
def test_schema_for_shared_layout_paths(tmp_path: Path, relpath: str, expected: str | None) -> None:
    assert schema.schema_for(relpath, _shared(tmp_path)) == expected


@pytest.mark.parametrize(
    ("relpath", "expected"),
    [
        ("64Qv3/config/system.yaml", "system.v1.schema.json"),
        ("64Qv3/config/wiring.yaml", "wiring.schema.json"),
        ("64Qv3/params/t1.yaml", "params-file.schema.json"),
        ("config/chip.yaml", None),
    ],
)
def test_schema_for_legacy_layout_paths(tmp_path: Path, relpath: str, expected: str | None) -> None:
    assert schema.schema_for(relpath, _legacy(tmp_path)) == expected


def test_shared_fixture_tree_satisfies_every_schema(tmp_path: Path) -> None:
    from tests.qdash.api.services.chip._trees import write_shared_tree

    write_shared_tree(tmp_path)
    layout = QubexLayout.detect(tmp_path)

    assert schema.validate_tree(layout, system_ids=["src16", "src16-quel3"]) == []


def test_structural_problems_name_the_file_and_location(tmp_path: Path) -> None:
    layout = _shared(tmp_path)

    chip = schema.validate_text("64Qv3:\n  n_qubits: sixty-four\n", "config/chip.yaml", layout)
    system = schema.validate_text("64Qv3:\n  backend: quel1\n", "config/system.yaml", layout)
    wiring = schema.validate_text("64Qv3:\n- mux: 0\n", "config/wiring.yaml", layout)
    box = schema.validate_text("S1:\n  name: a\n", "config/box.yaml", layout)
    broken = schema.validate_text("x: [", "config/chip.yaml", layout)

    assert [p.location for p in chip] == ["64Qv3/n_qubits"]
    assert "chip_id" in system[0].message
    assert "ctrl" in wiring[0].message
    assert "type" in box[0].message
    assert broken[0].message.startswith("not a valid document")
    assert str(chip[0]).startswith("config/chip.yaml at 64Qv3/n_qubits:")


def test_legacy_single_entry_system_file_is_accepted(tmp_path: Path) -> None:
    layout = _legacy(tmp_path)
    single = "schema_version: 1\nchip_id: 64Qv3\nbackend: quel1\nquel1:\n  clock_master: 10.0.0.1\n"
    catalog = "64Qv3:\n  chip_id: 64Qv3\n  backend: quel1\n"

    assert schema.validate_text(single, "64Qv3/config/system.yaml", layout) == []
    assert schema.validate_text(catalog, "64Qv3/config/system.yaml", layout) == []
    assert schema.validate_text(single, "config/system.yaml", _shared(tmp_path)) != []


def test_every_params_template_satisfies_the_params_file_schema() -> None:
    layout = _shared(REPO_ROOT)
    for path in sorted(templates_dir().rglob("*.yaml")):
        if path.name in schema.PARAMS_SETTINGS_FILES:
            continue
        problems = schema.validate_text(
            path.read_text(encoding="utf-8"), f"params/x/{path.name}", layout
        )
        assert problems == [], f"{path}: {problems}"


def test_manifest_document_satisfies_the_manifest_schema(tmp_path: Path) -> None:
    layout = _shared(tmp_path)
    doc = schema.manifest_document(
        LayoutKind.SHARED, converted_from=LayoutKind.LEGACY, generated_by="test"
    )

    assert schema.validate_text(json.dumps(doc), "qubex-config.json", layout) == []
    assert doc["layout_version"] == "2.0"
    assert doc["converted_from"] == "1.0"
    bad = schema.validate_text('{"layout_version": "3.0"}', "qubex-config.json", layout)
    assert "3.0" in bad[0].message


def test_published_schema_copies_match_the_source() -> None:
    source = schema.schemas_dir()
    published = REPO_ROOT / "docs" / "public" / "schemas" / "qubex-config"
    names = schema.schema_names()

    assert names, "no schemas found"
    assert sorted(p.name for p in published.glob("*.json")) == names
    for name in names:
        assert json.loads((published / name).read_text()) == json.loads((source / name).read_text())
        assert json.loads((source / name).read_text())["$id"] == schema.SCHEMA_BASE_URL + name


def test_params_file_with_a_non_string_unit_is_rejected(tmp_path: Path) -> None:
    content = yaml.safe_dump({"meta": {"unit": 0.2}, "data": {"Q00": 1}})
    problems = schema.validate_text(
        content, "params/64Qv3/readout_amplitude.yaml", _shared(tmp_path)
    )

    assert [p.location for p in problems] == ["meta/unit"]


def test_schemas_status_compares_the_tree_copy_with_the_shipped_schemas(tmp_path: Path) -> None:
    layout = _shared(tmp_path)
    assert schema.schemas_status(layout) == "absent"

    tree = tmp_path / "schemas"
    tree.mkdir()
    for name in schema.schema_names():
        (tree / name).write_text((schema.schemas_dir() / name).read_text())
    assert schema.schemas_status(layout) == "match"

    (tree / "chip.schema.json").write_text("{}")
    assert schema.schemas_status(layout) == "differs"
    (tree / "chip.schema.json").unlink()
    assert schema.schemas_status(layout) == "differs"
