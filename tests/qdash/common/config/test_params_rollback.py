"""Field-aware rollback of an apply that other params writers interleave with."""

import multiprocessing
import os
import threading
import time

import pytest
from filelock import FileLock
from ruamel.yaml import YAML

from qdash.common.config.params_updater import ParamsApplyRecord, YamlParamsUpdater

ORIGINAL = "# preserve me\ndata:\n  Q04: 4.0 # measured\n  Q05: null\n"


@pytest.fixture(autouse=True)
def _mapping(monkeypatch):
    monkeypatch.setattr(
        "qdash.common.config.params_updater.ConfigLoader.load_workflow",
        lambda: {
            "params_updater": {
                "parameter_file_map": {
                    "frequency": "frequency.yaml",
                    "capture_delay_word": "capture_delay_word.yaml",
                },
                "extra_file_map": {"frequency": ["control.yaml"]},
                "mux_file_names": ["capture_delay_word.yaml"],
            }
        },
    )


@pytest.fixture
def params_dir(tmp_path):
    for name in ("frequency.yaml", "control.yaml"):
        (tmp_path / name).write_text(ORIGINAL)
    return tmp_path


def _data(path):
    return dict(YAML().load(path.read_text())["data"])


def _apply(params_dir, label="Q04", value=5.0):
    updater = YamlParamsUpdater(params_dir, label)
    record = ParamsApplyRecord()
    changed = updater.apply("4", {"frequency": {"value": value}}, record)
    return updater, record, changed


def _ordinary_write(params_dir, label, value):
    """An unrelated workflow writer with its own updater instance and lock handles."""
    return YamlParamsUpdater(params_dir, label).update("x", {"frequency": {"value": value}})


def test_rollback_without_interleaving_restores_files_byte_for_byte(params_dir):
    updater, record, changed = _apply(params_dir)
    assert changed == {"frequency.yaml", "control.yaml"}

    result = updater.rollback(record)

    assert result.conflicts == ()
    assert set(result.restored) == {"frequency.yaml:Q04", "control.yaml:Q04"}
    for name in ("frequency.yaml", "control.yaml"):
        assert (params_dir / name).read_text() == ORIGINAL


def test_rollback_keeps_an_unrelated_value_written_to_the_same_file(params_dir):
    updater, record, _ = _apply(params_dir)
    _ordinary_write(params_dir, "Q05", 7.0)

    result = updater.rollback(record)

    assert result.conflicts == ()
    for name in ("frequency.yaml", "control.yaml"):
        assert _data(params_dir / name) == {"Q04": 4.0, "Q05": 7.0}
        assert "# measured" in (params_dir / name).read_text()


def test_rollback_leaves_a_later_value_of_the_same_field_and_reports_it(params_dir):
    updater, record, _ = _apply(params_dir)
    _ordinary_write(params_dir, "Q04", 6.0)

    result = updater.rollback(record)

    assert result.restored == ()
    assert len(result.conflicts) == 2
    assert all("Q04 changed after the apply" in c for c in result.conflicts)
    for name in ("frequency.yaml", "control.yaml"):
        assert _data(params_dir / name) == {"Q04": 6.0, "Q05": None}


def test_rollback_restores_a_key_the_file_did_not_have(params_dir):
    updater, record, _ = _apply(params_dir, label="Q06")
    _ordinary_write(params_dir, "Q05", 7.0)

    assert updater.rollback(record).conflicts == ()

    for name in ("frequency.yaml", "control.yaml"):
        assert _data(params_dir / name) == {"Q04": 4.0, "Q05": 7.0}


def test_rollback_preserves_a_different_value_inside_numeric_tolerance(params_dir):
    updater, record, _ = _apply(params_dir)
    for name in ("frequency.yaml", "control.yaml"):
        path = params_dir / name
        with FileLock(str(path) + ".lock"):
            yaml = YAML()
            data = yaml.load(path.read_text())
            data["data"]["Q04"] = 5.0000000005
            with path.open("w") as stream:
                yaml.dump(data, stream)

    result = updater.rollback(record)

    assert result.restored == ()
    assert len(result.conflicts) == 2
    for name in ("frequency.yaml", "control.yaml"):
        assert _data(params_dir / name)["Q04"] == 5.0000000005


def test_serialization_failure_removes_temporary_file(params_dir, monkeypatch):
    updater = YamlParamsUpdater(params_dir, "Q04")

    def fail_dump(data, stream):
        stream.write("partial")
        raise OSError("synthetic serialization failure")

    monkeypatch.setattr(updater._yaml, "dump", fail_dump)
    with pytest.raises(OSError, match="synthetic serialization failure"):
        updater.apply("4", {"frequency": {"value": 5.0}}, ParamsApplyRecord())

    assert list(params_dir.glob("*.tmp")) == []
    assert (params_dir / "frequency.yaml").read_text() == ORIGINAL


def test_rollback_removes_a_file_the_apply_created(params_dir):
    (params_dir / "control.yaml").unlink()
    updater, record, _ = _apply(params_dir)

    result = updater.rollback(record)

    assert result.removed_files == ("control.yaml",)
    assert not (params_dir / "control.yaml").exists()
    assert (params_dir / "frequency.yaml").read_text() == ORIGINAL


def test_rollback_keeps_a_created_file_another_writer_added_to(params_dir):
    (params_dir / "control.yaml").unlink()
    updater, record, _ = _apply(params_dir)
    _ordinary_write(params_dir, "Q05", 7.0)

    result = updater.rollback(record)

    assert result.removed_files == ()
    assert result.conflicts == ()
    assert _data(params_dir / "control.yaml") == {"Q05": 7.0}


def test_rollback_removes_an_added_unit_only_when_nothing_else_changed(params_dir):
    updater = YamlParamsUpdater(params_dir, "Q05")
    record = ParamsApplyRecord()
    updater.apply("5", {"capture_delay_word": {"value": 4, "unit": "word"}}, record)

    assert updater.rollback(record).removed_files == ("capture_delay_word.yaml",)
    assert not (params_dir / "capture_delay_word.yaml").exists()

    record = ParamsApplyRecord()
    updater.apply("5", {"capture_delay_word": {"value": 4, "unit": "word"}}, record)
    # Another qubit's MUX lands in the file and relies on the unit the apply added.
    YamlParamsUpdater(params_dir, "Q09").update(
        "9", {"capture_delay_word": {"value": 6, "unit": "word"}}
    )

    result = updater.rollback(record)

    assert result.removed_files == ()
    assert any("meta.unit 'word' kept" in c for c in result.conflicts)
    loaded = YAML().load((params_dir / "capture_delay_word.yaml").read_text())
    assert dict(loaded["data"]) == {2: 6}
    assert loaded["meta"]["unit"] == "word"


def test_unit_only_write_is_not_undone_as_a_value(params_dir):
    (params_dir / "capture_delay_word.yaml").write_text("data:\n  1: 4\n")
    updater = YamlParamsUpdater(params_dir, "Q05")
    record = ParamsApplyRecord()
    updater.apply("5", {"capture_delay_word": {"value": 4, "unit": "word"}}, record)
    YamlParamsUpdater(params_dir, "Q05").update("5", {"capture_delay_word": {"value": 5}})

    result = updater.rollback(record)

    assert result.conflicts == (
        "capture_delay_word.yaml: meta.unit 'word' kept because the data changed after the apply",
    )
    assert dict(YAML().load((params_dir / "capture_delay_word.yaml").read_text())["data"]) == {1: 5}


def test_a_failed_apply_still_records_and_undoes_the_writes_that_landed(params_dir, monkeypatch):
    updater = YamlParamsUpdater(params_dir, "Q04")
    original = updater._update_yaml

    def fail_frequency(path, label, value, **kwargs):
        if path.name == "frequency.yaml":
            raise OSError("disk full")
        return original(path, label, value, **kwargs)

    monkeypatch.setattr(updater, "_update_yaml", fail_frequency)
    record = ParamsApplyRecord()
    with pytest.raises(OSError, match="disk full"):
        updater.apply("4", {"frequency": {"value": 5.0}}, record)
    assert set(record.files) == {"control.yaml"}
    _ordinary_write(params_dir, "Q05", 7.0)

    assert updater.rollback(record).conflicts == ()
    assert _data(params_dir / "control.yaml") == {"Q04": 4.0, "Q05": 7.0}


def test_rollback_of_a_deleted_file_reports_instead_of_recreating(params_dir):
    updater, record, _ = _apply(params_dir)
    (params_dir / "control.yaml").unlink()

    result = updater.rollback(record)

    assert "control.yaml: removed after the apply wrote it" in result.conflicts
    assert not (params_dir / "control.yaml").exists()
    assert (params_dir / "frequency.yaml").read_text() == ORIGINAL


def test_rollback_waits_for_a_writer_holding_the_file_lock_and_releases_it(params_dir):
    updater, record, _ = _apply(params_dir)
    finished = threading.Event()
    holder = FileLock(params_dir / "control.yaml.lock")

    def roll_back() -> None:
        updater.rollback(record)
        finished.set()

    with holder:
        thread = threading.Thread(target=roll_back)
        thread.start()
        time.sleep(0.3)
        assert not finished.is_set()
        # The writer saves a value while rollback waits; rollback must not erase it.
        (params_dir / "control.yaml").write_text("data:\n  Q04: 5.0\n  Q05: 7.0\n")
    thread.join(timeout=5)
    assert finished.is_set()
    assert _data(params_dir / "control.yaml") == {"Q04": 4.0, "Q05": 7.0}
    for name in ("frequency.yaml.lock", "control.yaml.lock"):
        with FileLock(params_dir / name, timeout=0):
            pass


def _acquire_and_crash(lock_path: str) -> None:
    FileLock(lock_path).acquire()
    os._exit(1)


def test_a_crashed_lock_holder_does_not_block_rollback(params_dir):
    updater, record, _ = _apply(params_dir)
    process = multiprocessing.get_context("spawn").Process(
        target=_acquire_and_crash, args=(str(params_dir / "control.yaml.lock"),)
    )
    process.start()
    process.join(timeout=30)
    assert process.exitcode == 1

    assert updater.rollback(record).conflicts == ()
    assert (params_dir / "control.yaml").read_text() == ORIGINAL
