from qdash.common.infrastructure import logging as logging_config
from qdash.workflow.start_worker import _prefect_logging_yaml_path


def test_resolve_config_dir_prefers_app_logging(monkeypatch, tmp_path):
    app_dir = tmp_path / "app" / "logging"
    legacy_dir = tmp_path / "logging"
    app_dir.mkdir(parents=True)
    legacy_dir.mkdir()

    monkeypatch.setattr(logging_config, "_CONFIG_DIR", app_dir)
    monkeypatch.setattr(logging_config, "_LEGACY_CONFIG_DIR", legacy_dir)

    assert logging_config._resolve_config_dir(app_dir) == app_dir


def test_resolve_config_dir_falls_back_to_legacy_container_path(monkeypatch, tmp_path):
    app_dir = tmp_path / "missing" / "app" / "logging"
    legacy_dir = tmp_path / "logging"
    legacy_dir.mkdir()

    monkeypatch.setattr(logging_config, "_CONFIG_DIR", app_dir)
    monkeypatch.setattr(logging_config, "_LEGACY_CONFIG_DIR", legacy_dir)

    assert logging_config._resolve_config_dir(app_dir) == legacy_dir


def test_prefect_logging_yaml_path_prefers_app_logging(monkeypatch, tmp_path):
    app_path = tmp_path / "app" / "logging" / "prefect.yaml"
    legacy_path = tmp_path / "logging" / "prefect.yaml"
    app_path.parent.mkdir(parents=True)
    legacy_path.parent.mkdir()
    app_path.write_text("version: 1\n")
    legacy_path.write_text("version: 1\n")

    paths = {
        "/app/config/app/logging/prefect.yaml": app_path,
        "/app/config/logging/prefect.yaml": legacy_path,
    }
    monkeypatch.setattr("qdash.workflow.start_worker.Path", lambda value: paths[str(value)])

    assert _prefect_logging_yaml_path() == app_path


def test_prefect_logging_yaml_path_falls_back_to_legacy(monkeypatch, tmp_path):
    app_path = tmp_path / "missing" / "app" / "logging" / "prefect.yaml"
    legacy_path = tmp_path / "logging" / "prefect.yaml"
    legacy_path.parent.mkdir()
    legacy_path.write_text("version: 1\n")

    paths = {
        "/app/config/app/logging/prefect.yaml": app_path,
        "/app/config/logging/prefect.yaml": legacy_path,
    }
    monkeypatch.setattr("qdash.workflow.start_worker.Path", lambda value: paths[str(value)])

    assert _prefect_logging_yaml_path() == legacy_path
