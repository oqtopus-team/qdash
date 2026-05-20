from pathlib import Path

from qdash.api.services.file_service import FileService


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
