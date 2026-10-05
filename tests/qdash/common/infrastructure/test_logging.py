import atexit
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from qdash.common.infrastructure import logging as logging_config
from qdash.workflow.start_worker import _prefect_logging_yaml_path


def test_resolve_config_dir_prefers_app_logging(monkeypatch, tmp_path):
    app_dir = tmp_path / "app" / "logging"
    app_dir.mkdir(parents=True)

    monkeypatch.setattr(logging_config, "_CONFIG_DIR", app_dir)

    assert logging_config._resolve_config_dir(app_dir) == app_dir


def test_resolve_config_dir_falls_back_to_repo_app_logging(monkeypatch, tmp_path):
    app_dir = tmp_path / "missing" / "app" / "logging"
    repo_app_dir = tmp_path / "repo" / "config" / "app" / "logging"
    repo_app_dir.mkdir(parents=True)

    monkeypatch.setattr(logging_config, "_CONFIG_DIR", app_dir)
    monkeypatch.setattr(logging_config, "_LOCAL_CONFIG_DIR", repo_app_dir)

    assert logging_config._resolve_config_dir(app_dir) == repo_app_dir


def test_resolve_log_file_uses_temp_dir_when_log_dirs_are_unwritable(monkeypatch, tmp_path):
    state_dir = tmp_path / "state"
    monkeypatch.setenv("XDG_STATE_HOME", str(state_dir))
    temp_dir = tmp_path / "temporary"
    monkeypatch.setattr(tempfile, "mkdtemp", lambda prefix: str(temp_dir))
    register = MagicMock()
    monkeypatch.setattr(atexit, "register", register)

    original_open = Path.open

    def open_unwritable(path, *args, **kwargs):
        if path.is_relative_to("/app/logs") or path.is_relative_to(state_dir):
            raise PermissionError("log directory is not writable")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_unwritable)

    fallback_file = temp_dir / "deployment.log"
    assert logging_config._resolve_log_file("/app/logs/deployment.log") == str(fallback_file)
    assert fallback_file.exists()
    register.assert_called_once_with(shutil.rmtree, temp_dir, ignore_errors=True)


def test_resolve_log_file_uses_state_dir_outside_container(monkeypatch, tmp_path):
    state_dir = tmp_path / "state"
    monkeypatch.setenv("XDG_STATE_HOME", str(state_dir))
    original_open = Path.open

    def open_outside_container(path, *args, **kwargs):
        if path.is_relative_to("/app/logs"):
            raise PermissionError("container log directory is not writable")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_outside_container)

    assert logging_config._resolve_log_file("/app/logs/worker.log") == str(
        state_dir / "qdash" / "logs" / "worker.log"
    )


def test_prefect_logging_yaml_path_prefers_app_logging(monkeypatch, tmp_path):
    app_path = tmp_path / "app" / "logging" / "prefect.yaml"
    app_path.parent.mkdir(parents=True)
    app_path.write_text("version: 1\n")

    paths = {
        "/app/config/app/logging/prefect.yaml": app_path,
    }
    monkeypatch.setattr("qdash.workflow.start_worker.Path", lambda value: paths[str(value)])

    assert _prefect_logging_yaml_path() == app_path
