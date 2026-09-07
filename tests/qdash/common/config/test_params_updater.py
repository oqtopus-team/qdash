"""Verified YAML application, rollback, and exclusion of concurrent writers."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from filelock import FileLock, Timeout
from ruamel.yaml import YAML

from qdash.common.config.params_updater import YamlParamsUpdater


@pytest.fixture
def updater(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "qdash.common.config.params_updater.ConfigLoader.load_workflow",
        lambda: {
            "params_updater": {
                "parameter_file_map": {"frequency": "frequency.yaml"},
                "extra_file_map": {"frequency": ["control.yaml"]},
            }
        },
    )
    for name in ("frequency.yaml", "control.yaml"):
        (tmp_path / name).write_text("# preserve me\ndata:\n  Q04: 4.0 # measured\n  Q05: null\n")
    return YamlParamsUpdater(tmp_path, "Q04")


def test_apply_uses_both_maps_and_preserves_yaml(updater, tmp_path):
    with updater.applied("4", {"frequency": {"value": 5.0}, "quality": {"value": 3}}):
        for name in ("frequency.yaml", "control.yaml"):
            content = (tmp_path / name).read_text()
            assert "# preserve me" in content
            assert "# measured" in content
            assert YAML().load(content)["data"] == {"Q04": 5.0, "Q05": None}


def test_db_failure_restores_all_files_byte_for_byte(updater, tmp_path):
    before = {p.name: p.read_bytes() for p in tmp_path.glob("*.yaml")}
    with (
        pytest.raises(RuntimeError, match="DB failed"),
        updater.applied("4", {"frequency": {"value": 5.0}}),
    ):
        raise RuntimeError("DB failed")
    assert {p.name: p.read_bytes() for p in tmp_path.glob("*.yaml")} == before


def test_partial_write_failure_restores_all_files(updater, tmp_path, monkeypatch):
    before = {p.name: p.read_bytes() for p in tmp_path.glob("*.yaml")}
    original = updater._update_yaml

    def fail_second(path, label, value):
        if path.name == "frequency.yaml":
            raise OSError("disk full")
        return original(path, label, value)

    monkeypatch.setattr(updater, "_update_yaml", fail_second)
    with (
        pytest.raises(OSError, match="disk full"),
        updater.applied("4", {"frequency": {"value": 5.0}}),
    ):
        pytest.fail("DB commit must not be reached")
    assert {p.name: p.read_bytes() for p in tmp_path.glob("*.yaml")} == before


def test_verification_failure_rolls_back(updater, tmp_path, monkeypatch):
    before = (tmp_path / "frequency.yaml").read_bytes()
    monkeypatch.setattr(updater, "_update_yaml", lambda *args: False)
    with (
        pytest.raises(ValueError, match="verification failed"),
        updater.applied("4", {"frequency": {"value": 5.0}}),
    ):
        pytest.fail("DB commit must not be reached")
    assert (tmp_path / "frequency.yaml").read_bytes() == before


def test_missing_extra_file_blocks_commit(updater, tmp_path):
    (tmp_path / "control.yaml").unlink()
    before = (tmp_path / "frequency.yaml").read_bytes()
    with (
        pytest.raises(ValueError, match="does not exist"),
        updater.applied("4", {"frequency": {"value": 5.0}}),
    ):
        pytest.fail("DB commit must not be reached")
    assert (tmp_path / "frequency.yaml").read_bytes() == before


def test_unchanged_yaml_is_still_verified(updater):
    with updater.applied("4", {"frequency": {"value": 4.0}}):
        pass


def test_unmapped_values_do_not_need_files():
    with YamlParamsUpdater().applied("4", {"unmapped_diagnostic": {"value": 3}}):
        pass


@pytest.mark.parametrize("value", [None, float("nan"), float("inf")])
def test_invalid_mapped_values_cannot_commit(updater, value):
    with (
        pytest.raises(ValueError, match="finite YAML value"),
        updater.applied("4", {"frequency": {"value": value}}),
    ):
        pytest.fail("DB commit must not be reached")


def test_all_file_locks_held_until_db_commit_finishes(updater, tmp_path):
    def try_lock(path: Path) -> None:
        with pytest.raises(Timeout), FileLock(path, timeout=0):
            pytest.fail("Another writer entered during DB commit")

    with ThreadPoolExecutor() as executor, updater.applied("4", {"frequency": {"value": 5.0}}):
        for name in ("frequency.yaml.lock", "control.yaml.lock"):
            executor.submit(try_lock, tmp_path / name).result(timeout=2)
    with FileLock(tmp_path / "frequency.yaml.lock", timeout=0):
        pass


def test_extra_only_mapping_is_updated(updater, tmp_path):
    updater._param_file_map = {}
    with updater.applied("4", {"frequency": {"value": 5.0}}):
        assert YAML().load((tmp_path / "control.yaml").read_text())["data"]["Q04"] == 5.0
        assert YAML().load((tmp_path / "frequency.yaml").read_text())["data"]["Q04"] == 4.0


def test_rollback_failure_is_explicit(updater, monkeypatch):
    def fail_restore(snapshot):
        raise OSError("read-only filesystem")

    monkeypatch.setattr(updater, "restore", fail_restore)
    with (
        pytest.raises(RuntimeError, match="YAML rollback failed"),
        updater.applied("4", {"frequency": {"value": 5.0}}),
    ):
        raise RuntimeError("DB failed")
