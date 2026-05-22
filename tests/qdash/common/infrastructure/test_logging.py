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


def test_prefect_logging_yaml_path_prefers_app_logging(monkeypatch, tmp_path):
    app_path = tmp_path / "app" / "logging" / "prefect.yaml"
    app_path.parent.mkdir(parents=True)
    app_path.write_text("version: 1\n")

    paths = {
        "/app/config/app/logging/prefect.yaml": app_path,
    }
    monkeypatch.setattr("qdash.workflow.start_worker.Path", lambda value: paths[str(value)])

    assert _prefect_logging_yaml_path() == app_path
