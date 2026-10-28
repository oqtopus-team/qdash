"""Tests for ChipConfigScaffolder."""

import errno
from pathlib import Path

import pytest
import yaml

from qdash.api.services.chip.config_scaffold import ChipConfigError, ChipConfigScaffolder

TEMPLATES = Path(__file__).resolve().parents[5] / "config" / "domain" / "qubex-params"
CONFIG_TEMPLATES = TEMPLATES.parent / "qubex-config"


def _load(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A per-chip configuration tree with one quel1 system and one quel3 system."""
    root = tmp_path / "qubex-config"
    rows = [{"mux": 0, "ctrl": ["S1R-7"], "read_out": "S1R-1", "read_in": "S1R-0"}]
    _write(
        root / "64Qv3/config/chip.yaml",
        {"64Qv3": {"name": "old", "n_qubits": 64, "clock_master": "10.0.0.1"}},
    )
    _write(root / "64Qv3/config/wiring.yaml", {"64Qv3": rows})
    (root / "64Qv3/config/box.yaml").write_text(
        "# boxes\nS1R:\n  type: quel1se-riken8\n", encoding="utf-8"
    )
    _write(root / "64Qv3/config/skew.yaml", {"box_setting": {}})
    _write(
        root / "144Q-quel3/config/system.yaml",
        {
            "144Q-quel3": {
                "chip_id": "144Q-quel3",
                "backend": "quel3",
                "quel3": {"endpoint": "1.2.3.4"},
            }
        },
    )
    _write(root / "144Q-quel3/config/chip.yaml", {"144Q-quel3": {"name": "q3", "n_qubits": 144}})
    _write(root / "144Q-quel3/config/wiring.yaml", {"144Q-quel3": rows * 2})
    _write(root / "144Q-quel3/config/cable_delay.yaml", {"quel3-a": {"tx_p02": 818.0}})
    _write(root / "template/config/wiring.yaml", {"x": []})
    return root


@pytest.fixture
def scaffolder(tree: Path) -> ChipConfigScaffolder:
    return ChipConfigScaffolder(
        config_base=tree, templates_dir=TEMPLATES, config_templates_dir=CONFIG_TEMPLATES
    )


def test_list_sources_reports_backend_and_mux_count(scaffolder):
    sources = {source.system_id: source for source in scaffolder.list_sources()}

    assert set(sources) == {"144Q-quel3", "64Qv3"}
    assert sources["64Qv3"].backend == "quel1"
    assert sources["64Qv3"].mux_count == 1
    assert sources["144Q-quel3"].backend == "quel3"
    assert sources["144Q-quel3"].mux_count == 2
    assert "cable_delay.yaml" in sources["144Q-quel3"].files


def test_scaffold_without_source_uses_chip_id_as_system_id(scaffolder, tree):
    result = scaffolder.scaffold(chip_id="64Qv4", n_qubits=64)

    assert result.status == "created"
    config = tree / "64Qv4" / "config"
    assert _load(config / "chip.yaml") == {"64Qv4": {"name": "64Qv4", "n_qubits": 64}}
    assert _load(config / "system.yaml") == {"64Qv4": {"chip_id": "64Qv4", "backend": "quel1"}}
    assert _load(config / "wiring.yaml") == {"64Qv4": []}
    assert _load(config / "box.yaml") == {}
    assert (tree / "64Qv4/params/capture_delay_word.yaml").is_file()
    assert _load(tree / "64Qv4/params/qubit_frequency.yaml")["data"] == {}
    assert (tree / "64Qv4/calibration/calib_note.json").read_text().strip() == "{}"
    assert not list(tree.glob(".64Qv4.*"))


def test_scaffold_copies_wiring_and_hardware_from_legacy_source(scaffolder, tree):
    result = scaffolder.scaffold(chip_id="64Qv4", n_qubits=64, source_system_id="64Qv3")

    config = tree / "64Qv4" / "config"
    assert result.source_system_id == "64Qv3"
    assert _load(config / "wiring.yaml") == {
        "64Qv4": _load(tree / "64Qv3/config/wiring.yaml")["64Qv3"]
    }
    assert _load(config / "system.yaml") == {
        "64Qv4": {"chip_id": "64Qv4", "backend": "quel1", "quel1": {"clock_master": "10.0.0.1"}}
    }
    assert (config / "box.yaml").read_text().startswith("# boxes")
    assert (config / "skew.yaml").read_bytes() == (tree / "64Qv3/config/skew.yaml").read_bytes()
    assert "old" not in (config / "chip.yaml").read_text()


def test_scaffold_from_quel3_source_uses_quel3_params(scaffolder, tree):
    result = scaffolder.scaffold(chip_id="144Qv4", n_qubits=144, source_system_id="144Q-quel3")

    assert result.backend == "quel3"
    system = _load(tree / "144Qv4/config/system.yaml")["144Qv4"]
    assert system == {"chip_id": "144Qv4", "backend": "quel3", "quel3": {"endpoint": "1.2.3.4"}}
    assert (tree / "144Qv4/config/cable_delay.yaml").is_file()
    assert _load(tree / "144Qv4/params/capture_delay.yaml")["meta"]["unit"] == "ns"
    assert not (tree / "144Qv4/params/capture_delay_word.yaml").exists()


def test_scaffold_keeps_existing_directory(scaffolder, tree):
    before = (tree / "64Qv3/config/wiring.yaml").read_text()

    result = scaffolder.scaffold(chip_id="64Qv3", n_qubits=64, source_system_id="144Q-quel3")

    assert result.status == "existing"
    assert (tree / "64Qv3/config/wiring.yaml").read_text() == before


@pytest.mark.parametrize("chip_id", ["64Qv4", "chip-01.v2_test"])
def test_scaffold_skips_without_tree(tmp_path, chip_id):
    scaffolder = ChipConfigScaffolder(config_base=tmp_path / "missing", templates_dir=TEMPLATES)

    assert scaffolder.scaffold(chip_id=chip_id, n_qubits=64).status == "skipped"
    assert scaffolder.list_sources() == []
    assert not (tmp_path / "missing").exists()


@pytest.mark.parametrize("chip_id", ["my chip", "../escape", "template", "64Qv4\n"])
def test_scaffold_rejects_invalid_id_without_tree(tmp_path, chip_id):
    scaffolder = ChipConfigScaffolder(config_base=tmp_path / "missing", templates_dir=TEMPLATES)
    with pytest.raises(ChipConfigError):
        scaffolder.scaffold(chip_id=chip_id, n_qubits=64)
    assert not (tmp_path / "missing").exists()


def test_scaffold_rejects_trailing_newline_in_chip_id(scaffolder, tree):
    with pytest.raises(ChipConfigError):
        scaffolder.scaffold(chip_id="64Qv4\n", n_qubits=64)
    assert not (tree / "64Qv4\n").exists()


def test_scaffold_rejects_trailing_newline_in_existing_source(scaffolder, tree):
    source_id = "source\n"
    _write(tree / source_id / "config/wiring.yaml", {source_id: []})
    assert source_id not in [source.system_id for source in scaffolder.list_sources()]
    with pytest.raises(ChipConfigError):
        scaffolder.scaffold(chip_id="64Qv4", n_qubits=64, source_system_id=source_id)
    assert not (tree / "64Qv4").exists()


@pytest.mark.parametrize("chip_id", ["template", "archive", "schemas", "scripts"])
def test_scaffold_rejects_reserved_chip_id(scaffolder, chip_id):
    with pytest.raises(ChipConfigError, match="reserved"):
        scaffolder.scaffold(chip_id=chip_id, n_qubits=64)


@pytest.mark.parametrize("filename", ["wiring.yaml", "system.yaml", "chip.yaml"])
def test_scaffold_rejects_unrelated_single_entry(scaffolder, tree, filename):
    _write(tree / "64Qv3/config" / filename, {"unrelated": {"backend": "quel3"}})
    with pytest.raises(ChipConfigError, match="Cannot find system"):
        scaffolder.scaffold(chip_id="64Qv4", n_qubits=64, source_system_id="64Qv3")
    assert not (tree / "64Qv4").exists()
    assert "64Qv3" not in [source.system_id for source in scaffolder.list_sources()]


def test_source_without_system_or_chip_uses_default_backend(scaffolder, tree):
    _write(tree / "minimal/config/wiring.yaml", {"minimal": []})
    result = scaffolder.scaffold(chip_id="64Qv4", n_qubits=64, source_system_id="minimal")
    assert result.backend == "quel1"
    assert "minimal" in [source.system_id for source in scaffolder.list_sources()]


def test_scaffold_keeps_concurrently_created_directory(scaffolder, tree, monkeypatch):
    rename = Path.rename

    def concurrent_rename(staging, target):
        target.mkdir()
        (target / "sentinel").write_text("keep")
        return rename(staging, target)

    monkeypatch.setattr(Path, "rename", concurrent_rename)
    result = scaffolder.scaffold(chip_id="64Qv4", n_qubits=64)
    assert result.status == "existing"
    assert (tree / "64Qv4/sentinel").read_text() == "keep"
    assert not list(tree.glob(".64Qv4.*"))


def test_scaffold_does_not_hide_other_rename_errors(scaffolder, tree, monkeypatch):
    def fail_rename(staging, target):
        target.mkdir()
        raise PermissionError(errno.EACCES, "permission denied")

    monkeypatch.setattr(Path, "rename", fail_rename)
    with pytest.raises(PermissionError):
        scaffolder.scaffold(chip_id="64Qv4", n_qubits=64)
    assert not list(tree.glob(".64Qv4.*"))


@pytest.mark.parametrize("source", ["missing", "template", "../64Qv3", "64Qv3/config"])
def test_scaffold_rejects_unusable_source(scaffolder, tree, source):
    with pytest.raises(ChipConfigError):
        scaffolder.scaffold(chip_id="64Qv4", n_qubits=64, source_system_id=source)
    assert not (tree / "64Qv4").exists()


def test_scaffold_rejects_backend_mismatch(scaffolder):
    with pytest.raises(ChipConfigError, match="quel1"):
        scaffolder.scaffold(chip_id="64Qv4", n_qubits=64, source_system_id="64Qv3", backend="quel3")


def test_scaffold_rejects_path_like_chip_id(scaffolder):
    with pytest.raises(ChipConfigError):
        scaffolder.scaffold(chip_id="../escape", n_qubits=64)


def test_remove_rolls_back(scaffolder, tree):
    scaffolder.scaffold(chip_id="64Qv4", n_qubits=64)
    scaffolder.remove("64Qv4")

    assert not (tree / "64Qv4").exists()


@pytest.mark.parametrize("backend", ["quel1", "quel3"])
@pytest.mark.parametrize("chip_id", ["64Qv4", "123", "true"])
def test_config_templates_preserve_examples_and_string_ids(scaffolder, tree, backend, chip_id):
    result = scaffolder.scaffold(chip_id=chip_id, n_qubits=64, backend=backend)
    config = tree / chip_id / "config"
    assert result.backend == backend
    assert _load(config / "system.yaml") == {chip_id: {"chip_id": chip_id, "backend": backend}}
    assert _load(config / "wiring.yaml") == {chip_id: []}
    assert _load(config / "box.yaml") == {}
    for name in ("system.yaml", "wiring.yaml", "box.yaml"):
        text = (config / name).read_text()
        assert "TODO:" in text
        assert "$chip_id" not in text
        assert f"{chip_id}/config/{name}" in result.files
    connection_key = "clock_master" if backend == "quel1" else "endpoint"
    assert connection_key in (config / "system.yaml").read_text()
    assert "read_out:" in (config / "wiring.yaml").read_text()
    assert (tree / chip_id / "params/qubit_frequency.yaml").is_file()


def test_missing_config_template_rolls_back(tree, tmp_path):
    scaffolder = ChipConfigScaffolder(
        config_base=tree, templates_dir=TEMPLATES, config_templates_dir=tmp_path / "missing"
    )
    with pytest.raises(ChipConfigError, match="Missing configuration template"):
        scaffolder.scaffold(chip_id="64Qv4", n_qubits=64)
    assert not (tree / "64Qv4").exists()
    assert not list(tree.glob(".64Qv4.*"))


def test_copy_does_not_require_config_templates(tree, tmp_path):
    scaffolder = ChipConfigScaffolder(
        config_base=tree, templates_dir=TEMPLATES, config_templates_dir=tmp_path / "missing"
    )
    result = scaffolder.scaffold(chip_id="64Qv4", n_qubits=64, source_system_id="64Qv3")
    assert result.status == "created"
    assert (tree / "64Qv4/config/box.yaml").read_bytes() == (
        tree / "64Qv3/config/box.yaml"
    ).read_bytes()


@pytest.mark.parametrize("backend", ["quel1", "quel3"])
def test_skew_template_is_only_created_for_quel1(scaffolder, tree, backend):
    result = scaffolder.scaffold(chip_id="new-chip", n_qubits=64, backend=backend)
    skew = tree / "new-chip/config/skew.yaml"
    if backend == "quel3":
        assert not skew.exists()
        assert "new-chip/config/skew.yaml" not in result.files
        return
    assert "new-chip/config/skew.yaml" in result.files
    assert _load(skew) == {"box_setting": {}}
    # Follow the template instructions to verify the commented example is usable YAML.
    example = skew.read_text().replace("box_setting: {}", "box_setting:")
    example = "\n".join(
        line[2:] if line.startswith("# ") else line
        for line in example.splitlines()
        if not line.startswith("# ")
        or line.startswith(
            (
                "#   ",
                "# monitor_port:",
                "# reference_port:",
                "# scale:",
                "# target_port:",
                "# time_to_start:",
                "# trigger_nport:",
            )
        )
    )
    settings = yaml.safe_load(example)
    assert settings["box_setting"]["BOX_A"]["port_wait"] == {1: 0}
    assert settings["target_port"] == {"BOX_A-1", "BOX_B-8"}
    assert settings["reference_port"] == "BOX_A-1"
