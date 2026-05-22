from qdash.common.config.loader import ConfigLoader


def test_load_workflow_reads_workflow_yaml(monkeypatch, tmp_path):
    (tmp_path / "workflow.yaml").write_text("github:\n  params_file_names:\n    - params.yaml\n")
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", tmp_path)
    ConfigLoader.clear_cache()

    assert ConfigLoader.load_workflow() == {"github": {"params_file_names": ["params.yaml"]}}

    ConfigLoader.clear_cache()


def test_load_workflow_falls_back_to_settings_yaml_workflow(monkeypatch, tmp_path):
    (tmp_path / "settings.yaml").write_text("workflow:\n  github:\n    params_file_names: []\n")
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", tmp_path)
    ConfigLoader.clear_cache()

    assert ConfigLoader.load_workflow() == {"github": {"params_file_names": []}}

    ConfigLoader.clear_cache()


def test_load_metrics_reads_domain_yaml(monkeypatch, tmp_path):
    domain_dir = tmp_path / "domain"
    domain_dir.mkdir()
    (domain_dir / "metrics.yaml").write_text("qubit_metrics:\n  t1:\n    title: T1\n")
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", tmp_path)
    ConfigLoader.clear_cache()

    assert ConfigLoader.load_metrics() == {"qubit_metrics": {"t1": {"title": "T1"}}}

    ConfigLoader.clear_cache()


def test_load_metrics_falls_back_to_legacy_root_yaml(monkeypatch, tmp_path):
    (tmp_path / "metrics.yaml").write_text("qubit_metrics:\n  t2_echo:\n    title: T2 Echo\n")
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", tmp_path)
    ConfigLoader.clear_cache()

    assert ConfigLoader.load_metrics() == {"qubit_metrics": {"t2_echo": {"title": "T2 Echo"}}}

    ConfigLoader.clear_cache()


def test_load_policy_reads_domain_yaml(monkeypatch, tmp_path):
    domain_dir = tmp_path / "domain"
    domain_dir.mkdir()
    (domain_dir / "policy.yaml").write_text("version: 1\nrules: []\n")
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", tmp_path)
    ConfigLoader.clear_cache()

    assert ConfigLoader.load_policy() == {"version": 1, "rules": []}

    ConfigLoader.clear_cache()


def test_load_copilot_reads_copilot_config_yaml(monkeypatch, tmp_path):
    copilot_dir = tmp_path / "copilot"
    copilot_dir.mkdir()
    (copilot_dir / "config.yaml").write_text("enabled: true\n")
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", tmp_path)
    ConfigLoader.clear_cache()

    assert ConfigLoader.load_copilot() == {"enabled": True}

    ConfigLoader.clear_cache()


def test_load_copilot_merges_chat_and_review_yaml(monkeypatch, tmp_path):
    copilot_dir = tmp_path / "copilot"
    copilot_dir.mkdir()
    (copilot_dir / "config.yaml").write_text("enabled: true\n")
    (copilot_dir / "chat.yaml").write_text("chat_models:\n  - provider: openai\n    name: gpt-5.4\n")
    (copilot_dir / "review.yaml").write_text(
        "analysis:\n  ai_review_tasks:\n    - CheckQubitSpectroscopy\n"
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
    (tmp_path / "copilot.yaml").write_text("enabled: false\n")
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", tmp_path)
    ConfigLoader.clear_cache()

    assert ConfigLoader.load_copilot() == {"enabled": False}

    ConfigLoader.clear_cache()
