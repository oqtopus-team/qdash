from pathlib import Path

from qdash.api.services.task_file_service import TaskFileService


def test_uses_caltasks_path_from_environment(monkeypatch, tmp_path: Path) -> None:
    calibtasks_dir = tmp_path / "calibtasks"
    (calibtasks_dir / "fake").mkdir(parents=True)
    (calibtasks_dir / "qubex").mkdir()
    monkeypatch.setenv("CALTASKS_PATH", str(calibtasks_dir))

    service = TaskFileService()

    assert service._base_path == calibtasks_dir.resolve()
    assert [backend.name for backend in service.list_backends().backends] == ["fake", "qubex"]


def test_falls_back_to_container_calibtasks_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("CALTASKS_PATH", raising=False)
    calibtasks_dir = tmp_path / "calibtasks"
    calibtasks_dir.mkdir()
    monkeypatch.setattr(
        "qdash.common.config.path_resolver.CALIBTASKS_DIR",
        calibtasks_dir,
    )

    service = TaskFileService()

    assert service._base_path == calibtasks_dir


def test_falls_back_to_repo_local_calibtasks_path_when_container_path_is_missing(
    monkeypatch,
) -> None:
    monkeypatch.delenv("CALTASKS_PATH", raising=False)
    monkeypatch.chdir(Path(__file__).parents[4])
    monkeypatch.setattr(
        "qdash.common.config.path_resolver.CALIBTASKS_DIR",
        Path("/missing/calibtasks"),
    )

    service = TaskFileService()

    assert service._base_path == (Path.cwd() / "src/qdash/workflow/calibtasks").resolve()


def test_explicit_calibtasks_base_path_takes_precedence(monkeypatch, tmp_path: Path) -> None:
    explicit_dir = tmp_path / "explicit"
    explicit_dir.mkdir()
    monkeypatch.setenv("CALTASKS_PATH", str(tmp_path / "from-env"))

    service = TaskFileService(calibtasks_base_path=explicit_dir)

    assert service._base_path == explicit_dir
