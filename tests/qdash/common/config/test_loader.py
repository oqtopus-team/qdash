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
