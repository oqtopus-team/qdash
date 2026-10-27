"""QubexLayout resolves both directory layouts and the repository-relative paths."""

from pathlib import Path, PurePosixPath

import pytest

from qdash.common.config.qubex_layout import LayoutKind, QubexLayout, detect_layout_kind


def test_legacy_layout_is_detected_without_shared_chip_catalog(tmp_path: Path) -> None:
    (tmp_path / "64Qv3" / "config").mkdir(parents=True)

    layout = QubexLayout.detect(tmp_path)

    assert layout.kind is LayoutKind.LEGACY
    assert layout.config_dir("64Qv3") == tmp_path / "64Qv3" / "config"
    assert layout.wiring_yaml("64Qv3") == tmp_path / "64Qv3" / "config" / "wiring.yaml"
    assert layout.params_dir("64Qv3") == tmp_path / "64Qv3" / "params"
    assert layout.calib_note_path("64Qv3") == tmp_path / "64Qv3" / "calibration" / "calib_note.json"


def test_legacy_layout_requires_a_chip_for_shared_files(tmp_path: Path) -> None:
    layout = QubexLayout(tmp_path, LayoutKind.LEGACY)

    with pytest.raises(ValueError, match="chip_id is required"):
        layout.wiring_yaml()


def test_shared_layout_is_detected_from_the_shared_chip_catalog(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "chip.yaml").write_text("64Qv3: {n_qubits: 64}\n")

    layout = QubexLayout.detect(tmp_path)

    assert layout.kind is LayoutKind.SHARED
    assert layout.config_dir() == tmp_path / "config"
    assert layout.config_dir("64Qv3") == tmp_path / "config"
    assert layout.params_dir("64Qv3-quel3") == tmp_path / "params" / "64Qv3-quel3"
    assert layout.calibration_dir("64Qv3") == tmp_path / "calibration" / "64Qv3"


@pytest.mark.parametrize(
    ("forced", "expected"), [("shared", LayoutKind.SHARED), ("legacy", LayoutKind.LEGACY)]
)
def test_environment_variable_forces_the_layout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, forced: str, expected: LayoutKind
) -> None:
    monkeypatch.setenv("QUBEX_LAYOUT", forced)

    assert detect_layout_kind(tmp_path) is expected


def test_unknown_layout_override_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("QUBEX_LAYOUT", "flat")

    with pytest.raises(ValueError, match="QUBEX_LAYOUT"):
        detect_layout_kind(tmp_path)


def test_repo_relpath_matches_each_layout(tmp_path: Path) -> None:
    legacy = QubexLayout(tmp_path, LayoutKind.LEGACY)
    shared = QubexLayout(tmp_path, LayoutKind.SHARED)

    assert legacy.repo_relpath(legacy.params_dir("64Qv3") / "t1.yaml") == PurePosixPath(
        "64Qv3/params/t1.yaml"
    )
    assert shared.repo_relpath(shared.params_dir("64Qv3") / "t1.yaml") == PurePosixPath(
        "params/64Qv3/t1.yaml"
    )
    with pytest.raises(ValueError):
        shared.repo_relpath(Path("/elsewhere/t1.yaml"))


@pytest.mark.parametrize("system_id", ["", "../other", "a/b"])
def test_owned_directories_reject_unsafe_ids(tmp_path: Path, system_id: str) -> None:
    layout = QubexLayout(tmp_path, LayoutKind.SHARED)

    with pytest.raises(ValueError):
        layout.params_dir(system_id)


def test_manifest_declares_the_layout_version(tmp_path: Path) -> None:
    (tmp_path / "qubex-config.json").write_text('{"layout_version": "2.0"}')

    layout = QubexLayout.detect(tmp_path)

    assert layout.kind is LayoutKind.SHARED
    assert layout.version == "2.0"
    assert layout.manifest() == {"layout_version": "2.0"}


def test_manifest_wins_over_the_directory_probe(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "chip.yaml").write_text("64Qv3: {n_qubits: 64}\n")
    (tmp_path / "qubex-config.json").write_text('{"layout_version": "1.0"}')

    assert detect_layout_kind(tmp_path) is LayoutKind.LEGACY
    assert QubexLayout(tmp_path, LayoutKind.LEGACY).version == "1.0"


def test_tree_without_manifest_has_no_manifest_but_a_version(tmp_path: Path) -> None:
    layout = QubexLayout.detect(tmp_path)

    assert layout.manifest() is None
    assert layout.version == "1.0"
    assert layout.manifest_path == tmp_path / "qubex-config.json"


@pytest.mark.parametrize(
    "content", ['{"layout_version": "3.0"}', '{"layout_version": 2}', "[]", "{"]
)
def test_malformed_manifest_is_rejected(tmp_path: Path, content: str) -> None:
    (tmp_path / "qubex-config.json").write_text(content)

    with pytest.raises(ValueError, match=r"qubex-config\.json|layout_version"):
        detect_layout_kind(tmp_path)


def test_environment_override_beats_the_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "qubex-config.json").write_text('{"layout_version": "2.0"}')
    monkeypatch.setenv("QUBEX_LAYOUT", "legacy")

    assert detect_layout_kind(tmp_path) is LayoutKind.LEGACY
