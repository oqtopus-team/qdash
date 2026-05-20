from pathlib import Path

from qdash.api.dependencies import get_task_file_service
from qdash.api.services.chip_service import _get_task_names_cached, get_task_names
from qdash.api.services.task_file_service import TaskFileService
from qdash.common.config.backend import clear_cache as clear_backend_config_cache


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


def test_ignores_nonexistent_caltasks_path_from_environment(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CALTASKS_PATH", str(tmp_path / "missing"))
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


def test_get_settings_uses_effective_default_backend_from_environment(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DEFAULT_BACKEND", "fake")
    monkeypatch.setenv("CALTASKS_PATH", str(tmp_path))
    clear_backend_config_cache()

    service = TaskFileService()

    assert service.get_settings().default_backend == "fake"


def test_get_task_names_uses_effective_default_backend_and_resolved_calibtasks_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calibtasks_dir = tmp_path / "calibtasks"
    fake_dir = calibtasks_dir / "fake"
    qubex_dir = calibtasks_dir / "qubex"
    fake_dir.mkdir(parents=True)
    qubex_dir.mkdir()
    (fake_dir / "fake_task.py").write_text(
        "class FakeTask:\n"
        "    name: str = \"FakeOnlyTask\"\n"
        "    task_type: str = \"qubit\"\n",
        encoding="utf-8",
    )
    (qubex_dir / "qubex_task.py").write_text(
        "class QubexTask:\n"
        "    name: str = \"QubexOnlyTask\"\n"
        "    task_type: str = \"qubit\"\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CALTASKS_PATH", str(calibtasks_dir))
    monkeypatch.setenv("DEFAULT_BACKEND", "fake")
    clear_backend_config_cache()
    get_task_file_service.cache_clear()
    _get_task_names_cached.cache_clear()

    assert get_task_names() == ["FakeOnlyTask"]

    get_task_file_service.cache_clear()
    _get_task_names_cached.cache_clear()
