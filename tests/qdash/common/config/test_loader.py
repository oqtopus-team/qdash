from pathlib import Path

from qdash.common.config.loader import ConfigLoader


def _write_yaml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_load_settings_reads_app_yaml(monkeypatch, tmp_path):
    _write_yaml(tmp_path / "app" / "settings.yaml", "ui:\n  task_files:\n    sort_order: name\n")
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", tmp_path)
    ConfigLoader.clear_cache()

    assert ConfigLoader.load_settings() == {"ui": {"task_files": {"sort_order": "name"}}}

    ConfigLoader.clear_cache()


def test_load_settings_falls_back_to_legacy_root_yaml(monkeypatch, tmp_path):
    _write_yaml(tmp_path / "settings.yaml", "ui:\n  task_files:\n    sort_order: name\n")
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", tmp_path)
    ConfigLoader.clear_cache()

    assert ConfigLoader.load_settings() == {"ui": {"task_files": {"sort_order": "name"}}}

    ConfigLoader.clear_cache()


def test_load_settings_expands_environment_variables(monkeypatch, tmp_path):
    monkeypatch.setenv("QDASH_TASK_FILE_SORT_ORDER", "updated_at")
    _write_yaml(
        tmp_path / "app" / "settings.yaml",
        "ui:\n  task_files:\n    sort_order: ${QDASH_TASK_FILE_SORT_ORDER}\n",
    )
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", tmp_path)
    ConfigLoader.clear_cache()

    assert ConfigLoader.load_settings() == {"ui": {"task_files": {"sort_order": "updated_at"}}}

    ConfigLoader.clear_cache()


def test_load_backend_reads_app_yaml(monkeypatch, tmp_path):
    _write_yaml(tmp_path / "app" / "backend.yaml", "default_backend: fake\n")
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", tmp_path)
    ConfigLoader.clear_cache()

    assert ConfigLoader.load_backend() == {"default_backend": "fake"}

    ConfigLoader.clear_cache()


def test_load_workflow_reads_workflow_yaml(monkeypatch, tmp_path):
    _write_yaml(
        tmp_path / "app" / "workflow.yaml",
        "github:\n  params_file_names:\n    - params.yaml\n",
    )
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", tmp_path)
    ConfigLoader.clear_cache()

    assert ConfigLoader.load_workflow() == {"github": {"params_file_names": ["params.yaml"]}}

    ConfigLoader.clear_cache()


def test_load_workflow_falls_back_to_legacy_root_yaml(monkeypatch, tmp_path):
    _write_yaml(tmp_path / "workflow.yaml", "github:\n  params_file_names:\n    - params.yaml\n")
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", tmp_path)
    ConfigLoader.clear_cache()

    assert ConfigLoader.load_workflow() == {"github": {"params_file_names": ["params.yaml"]}}

    ConfigLoader.clear_cache()


def test_load_workflow_falls_back_to_settings_yaml_workflow(monkeypatch, tmp_path):
    _write_yaml(tmp_path / "settings.yaml", "workflow:\n  github:\n    params_file_names: []\n")
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", tmp_path)
    ConfigLoader.clear_cache()

    assert ConfigLoader.load_workflow() == {"github": {"params_file_names": []}}

    ConfigLoader.clear_cache()


def test_load_metrics_reads_domain_yaml(monkeypatch, tmp_path):
    _write_yaml(tmp_path / "domain" / "metrics.yaml", "qubit_metrics:\n  t1:\n    title: T1\n")
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", tmp_path)
    ConfigLoader.clear_cache()

    assert ConfigLoader.load_metrics() == {"qubit_metrics": {"t1": {"title": "T1"}}}

    ConfigLoader.clear_cache()


def test_load_metrics_falls_back_to_legacy_root_yaml(monkeypatch, tmp_path):
    _write_yaml(tmp_path / "metrics.yaml", "qubit_metrics:\n  t2_echo:\n    title: T2 Echo\n")
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", tmp_path)
    ConfigLoader.clear_cache()

    assert ConfigLoader.load_metrics() == {"qubit_metrics": {"t2_echo": {"title": "T2 Echo"}}}

    ConfigLoader.clear_cache()


def test_load_policy_reads_domain_yaml(monkeypatch, tmp_path):
    _write_yaml(tmp_path / "domain" / "policy.yaml", "version: 1\nrules: []\n")
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", tmp_path)
    ConfigLoader.clear_cache()

    assert ConfigLoader.load_policy() == {"version": 1, "rules": []}

    ConfigLoader.clear_cache()


def test_load_copilot_reads_copilot_config_yaml(monkeypatch, tmp_path):
    _write_yaml(tmp_path / "copilot" / "config.yaml", "enabled: true\n")
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", tmp_path)
    ConfigLoader.clear_cache()

    assert ConfigLoader.load_copilot() == {"enabled": True}

    ConfigLoader.clear_cache()


def test_load_copilot_merges_chat_and_review_yaml(monkeypatch, tmp_path):
    _write_yaml(tmp_path / "copilot" / "config.yaml", "enabled: true\n")
    _write_yaml(
        tmp_path / "copilot" / "chat.yaml",
        "chat_models:\n  - provider: openai\n    name: gpt-5.4\n",
    )
    _write_yaml(
        tmp_path / "copilot" / "review.yaml",
        "analysis:\n  ai_review_tasks:\n    - CheckQubitSpectroscopy\n",
    )
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", tmp_path)
    ConfigLoader.clear_cache()

    assert ConfigLoader.load_copilot() == {
        "enabled": True,
        "chat_models": [{"provider": "openai", "name": "gpt-5.4"}],
        "analysis": {"ai_review_tasks": ["CheckQubitSpectroscopy"]},
    }

    ConfigLoader.clear_cache()


def test_load_copilot_falls_back_to_legacy_root_yaml(monkeypatch, tmp_path):
    _write_yaml(tmp_path / "copilot.yaml", "enabled: false\n")
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", tmp_path)
    ConfigLoader.clear_cache()

    assert ConfigLoader.load_copilot() == {"enabled": False}

    ConfigLoader.clear_cache()
