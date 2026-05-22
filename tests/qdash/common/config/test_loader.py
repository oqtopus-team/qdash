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

    assert ConfigLoader.load_metrics() == {
        "qubit_metrics": {"t2_echo": {"title": "T2 Echo"}}
    }

    ConfigLoader.clear_cache()


def test_load_policy_reads_domain_yaml(monkeypatch, tmp_path):
    domain_dir = tmp_path / "domain"
    domain_dir.mkdir()
    (domain_dir / "policy.yaml").write_text("version: 1\nrules: []\n")
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", tmp_path)
    ConfigLoader.clear_cache()

    assert ConfigLoader.load_policy() == {"version": 1, "rules": []}

    ConfigLoader.clear_cache()
