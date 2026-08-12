import shutil
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException
from git import Repo

from qdash.api.services.file_service import FileService


def test_get_file_content_includes_saved_git_diff_base(tmp_path: Path) -> None:
    config_dir = tmp_path / "qubex-config"
    config_dir.mkdir()
    file_path = config_dir / "settings.yaml"
    file_path.write_text("name: before\n", encoding="utf-8")
    repo = Repo.init(config_dir)
    repo.index.add(["settings.yaml"])
    repo.index.commit("Initial config")
    file_path.write_text("name: after\n", encoding="utf-8")

    result = FileService(config_base_path=config_dir).get_file_content("settings.yaml")

    assert result["content"] == "name: after\n"
    assert result["base_content"] == "name: before\n"
    assert result["is_saved_change"] is True


def test_get_file_content_marks_untracked_file_as_saved_change(tmp_path: Path) -> None:
    config_dir = tmp_path / "qubex-config"
    config_dir.mkdir()
    repo = Repo.init(config_dir)
    tracked_file = config_dir / "tracked.yaml"
    tracked_file.write_text("tracked: true\n", encoding="utf-8")
    repo.index.add(["tracked.yaml"])
    repo.index.commit("Initial config")
    (config_dir / "new.yaml").write_text("new: true\n", encoding="utf-8")

    result = FileService(config_base_path=config_dir).get_file_content("new.yaml")

    assert result["base_content"] == ""
    assert result["is_saved_change"] is True


def test_uses_config_path_from_environment(monkeypatch, tmp_path: Path) -> None:
    config_dir = tmp_path / "qubex-config"
    config_dir.mkdir()
    (config_dir / "settings.yaml").write_text("name: test\n", encoding="utf-8")
    monkeypatch.setenv("CONFIG_PATH", str(config_dir))

    service = FileService()

    assert service._base_path == config_dir.resolve()
    assert [node.name for node in service.get_file_tree()] == ["settings.yaml"]


def test_falls_back_to_container_qubex_config_path(monkeypatch) -> None:
    monkeypatch.delenv("CONFIG_PATH", raising=False)
    monkeypatch.setattr("qdash.common.config.path_resolver.QUBEX_CONFIG_BASE", Path("/tmp"))

    service = FileService()

    assert service._base_path == Path("/tmp")


def test_falls_back_to_repo_local_config_path_when_container_path_is_missing(
    monkeypatch,
) -> None:
    monkeypatch.delenv("CONFIG_PATH", raising=False)
    monkeypatch.chdir(Path(__file__).parents[4])
    monkeypatch.setattr(
        "qdash.common.config.path_resolver.QUBEX_CONFIG_BASE", Path("/missing/qubex-config")
    )

    service = FileService()

    assert service._base_path == (Path.cwd() / "config/qubex-config").resolve()


def test_explicit_config_base_path_takes_precedence(monkeypatch, tmp_path: Path) -> None:
    explicit_dir = tmp_path / "explicit"
    explicit_dir.mkdir()
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "from-env"))

    service = FileService(config_base_path=explicit_dir)

    assert service._base_path == explicit_dir


def test_download_zip_file_maps_config_parent_to_qubex_config(tmp_path: Path) -> None:
    config_parent = tmp_path / "config"
    config_dir = config_parent / "qubex-config"
    sibling_dir = config_parent / "other-config"
    target_file = config_dir / "64Qv3" / "config" / "wiring.yaml"
    sibling_file = sibling_dir / "secret.yaml"
    target_file.parent.mkdir(parents=True)
    sibling_file.parent.mkdir(parents=True)
    target_file.write_text("wiring: test\n", encoding="utf-8")
    sibling_file.write_text("secret: true\n", encoding="utf-8")

    service = FileService(config_base_path=config_dir)

    response = service.download_zip_file(str(config_parent))

    try:
        assert response.filename is not None
        assert response.filename.startswith("qubex-config_")
        with zipfile.ZipFile(response.path) as archive:
            file_names = [name for name in archive.namelist() if not name.endswith("/")]
            assert file_names == ["64Qv3/config/wiring.yaml"]
            assert archive.read("64Qv3/config/wiring.yaml").decode() == "wiring: test\n"
    finally:
        shutil.rmtree(Path(response.path).parent, ignore_errors=True)


def test_download_zip_file_rejects_paths_outside_qubex_config(tmp_path: Path) -> None:
    config_dir = tmp_path / "config" / "qubex-config"
    outside_dir = tmp_path / "outside"
    config_dir.mkdir(parents=True)
    outside_dir.mkdir()

    service = FileService(config_base_path=config_dir)

    with pytest.raises(HTTPException) as exc_info:
        service.download_zip_file(str(outside_dir))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Path outside config directory"
