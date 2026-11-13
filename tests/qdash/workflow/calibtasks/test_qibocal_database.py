"""Database projection and adoption on a qibocal_bound emulator chip."""

import os
from typing import Any, cast

import pytest

from qdash.common.qibocal_platform import load_platform_template, template_values
from qdash.common.simulation_binding import (
    SimulationBindingError,
    check_backend_for_chip,
    check_hardware_export,
)
from qdash.dbmodel.qubit import QubitDocument
from qdash.repository.inmemory.execution import InMemoryExecutionRepository
from qdash.workflow.calibtasks.qibocal import QibocalBringUp, QibocalFlipping, QibocalRabiAmplitude
from qdash.workflow.engine.backend.qibocal import hash_tree
from qdash.workflow.engine.execution.service import ExecutionService
from qdash.workflow.engine.task.context import TaskContext


def values():
    record = QubitDocument.find_one(
        {"project_id": "proj-1", "chip_id": "emulator", "qid": "0"}
    ).run()
    assert record is not None
    return record.data


def execute(task, backend, tmp_path, update=True, snapshot=None):
    context = TaskContext(
        username="alice",
        execution_id="20261113-001",
        qids=["0"],
        calib_dir=str(tmp_path),
        update_calibration_parameters=update,
    )
    if snapshot is not None:
        from types import SimpleNamespace

        context.executor._snapshot_loader = cast(
            "Any",
            SimpleNamespace(
                get_snapshot=lambda *_: (snapshot, {}),
                requires_snapshot=lambda *_: True,
            ),
        )
    execution = ExecutionService.create(
        username="alice",
        execution_id="20261113-001",
        calib_data_path=str(tmp_path),
        chip_id="emulator",
        project_id="proj-1",
        repository=InMemoryExecutionRepository(),
    )
    execution.save()
    _, result = context.executor.execute(task, backend, "0", execution)
    return result, context.state.get_task(task.name, "qubit", "0")


def test_bringup_idempotent_and_update_false(qibocal_bound, tmp_path):
    execute(QibocalBringUp(), qibocal_bound, tmp_path, False)
    assert values() == {}
    execute(QibocalBringUp(), qibocal_bound, tmp_path)
    initial = values()
    execute(QibocalBringUp(), qibocal_bound, tmp_path)
    assert values() == initial
    assert initial["qibocal_pi_duration"]["value"] == 40


def test_missing_binding_and_model_rejected(qibocal_bound):
    check_backend_for_chip(qibocal_bound.binding(), "qibocal", "emulator")
    with pytest.raises(SimulationBindingError):
        check_backend_for_chip(qibocal_bound.binding(), "qubex", "emulator")
    with pytest.raises(SimulationBindingError):
        check_backend_for_chip(None, "qibocal", "emulator")
    with pytest.raises(SimulationBindingError):
        check_hardware_export(qibocal_bound.binding(), "emulator", "export")
    with pytest.raises(ValueError, match="Required input"):
        QibocalRabiAmplitude().preprocess(qibocal_bound, "0")


@pytest.mark.qibocal_emulator
@pytest.mark.skipif(os.getenv("QDASH_QIBOCAL_INTEGRATION") != "1", reason="real runner opt-in")
def test_real_chain(qibocal_bound, tmp_path):
    before = hash_tree(qibocal_bound.settings.platform_dir)
    execute(QibocalBringUp(), qibocal_bound, tmp_path)
    _, entry = execute(QibocalRabiAmplitude(), qibocal_bound, tmp_path)
    amplitude = values()["qibocal_pi_amplitude"]["value"]
    assert amplitude == pytest.approx(0.127, abs=0.005)
    flipping = QibocalFlipping()
    _, entry = execute(flipping, qibocal_bound, tmp_path)
    assert flipping.input_parameters["qibocal_pi_amplitude"].value == amplitude
    assert entry.note["provenance"]["calibration"]["qibocal_pi_amplitude"] == amplitude
    assert hash_tree(qibocal_bound.settings.platform_dir) == before
    print(
        "REAL_CHAIN",
        amplitude,
        values()["qibocal_pi_amplitude"]["value"],
        entry.note["provenance"]["run_dir"],
    )


def test_legacy_and_cross_chip_adoption_rejected(qibocal_bound, tmp_path):
    from qdash.common.simulation_binding import check_calibration_write

    execute(QibocalBringUp(), qibocal_bound, tmp_path)
    before = values()
    raw = dict(before["qibocal_pi_amplitude"])
    raw["measurement_only_reason"] = "Legacy emulator measurement"
    with pytest.raises(SimulationBindingError):
        check_calibration_write("proj-1", "emulator", {"qibocal_pi_amplitude": raw})
    raw.pop("measurement_only_reason")
    with pytest.raises(SimulationBindingError):
        check_calibration_write("proj-1", "other", {"qibocal_pi_amplitude": raw})
    assert values() == before


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, 0, True])
def test_invalid_projection_rejected(value):
    from qdash.common.qibocal_platform import native_assignments

    data = template_values(load_platform_template().parameters(), 0)
    data["qibocal_pi_duration"] = value
    with pytest.raises(ValueError):
        native_assignments(0, data)


@pytest.mark.qibocal_emulator
@pytest.mark.skipif(os.getenv("QDASH_QIBOCAL_INTEGRATION") != "1", reason="real runner opt-in")
def test_real_database_override_and_template_independence(qibocal_bound, tmp_path):
    import json
    import shutil
    from dataclasses import replace

    from qdash.common.qibocal_platform import CALIBRATION_FIELDS, set_path, structural_fingerprint

    execute(QibocalBringUp(), qibocal_bound, tmp_path)
    task = QibocalRabiAmplitude()
    execute(task, qibocal_bound, tmp_path)
    initial = values()
    second = QibocalRabiAmplitude({"input": {"qibocal_pi_duration": 80.0}})
    _, entry = execute(second, qibocal_bound, tmp_path, update=False)
    fitted = entry.output_parameters["qibocal_pi_amplitude"]["value"]
    assert fitted < initial["qibocal_pi_amplitude"]["value"]
    assert entry.note["provenance"]["calibration"]["qibocal_pi_duration"] == 80.0
    assert values() == initial
    next_task = QibocalRabiAmplitude()
    next_task.preprocess(qibocal_bound, "0")
    assert next_task.input_parameters["qibocal_pi_duration"].value == 40.0
    assert (
        next_task.input_parameters["qibocal_pi_amplitude"].value
        == initial["qibocal_pi_amplitude"]["value"]
    )

    source = qibocal_bound.settings.platform_dir
    copied = tmp_path / "changed" / qibocal_bound.settings.platform
    shutil.copytree(source, copied)
    params_path = copied / "parameters.json"
    params = json.loads(params_path.read_text())
    for field in CALIBRATION_FIELDS:
        for target in field.targets:
            set_path(params, target.resolve(0), 0.2 if field.name.endswith("amplitude") else 90.0)
    params_path.write_text(json.dumps(params))
    assert structural_fingerprint(source) == structural_fingerprint(copied)
    qibocal_bound._settings = replace(qibocal_bound.settings, platforms_dir=copied.parent)
    repeated = QibocalRabiAmplitude({"input": {"qibocal_pi_duration": 80.0}})
    _, repeated_entry = execute(repeated, qibocal_bound, tmp_path, update=False)
    assert repeated_entry.output_parameters["qibocal_pi_amplitude"]["value"] == fitted
    from pathlib import Path

    original_result = json.loads(
        (Path(entry.note["provenance"]["run_dir"]) / "result.json").read_text()
    )
    repeated_result = json.loads(
        (Path(repeated_entry.note["provenance"]["run_dir"]) / "result.json").read_text()
    )
    assert repeated_result["data"] == original_result["data"]
    assert repeated_result["fit"] == original_result["fit"]
    (copied / "platform.py").write_text(
        (copied / "platform.py").read_text() + "\n# model revision\n"
    )
    with pytest.raises(SimulationBindingError, match="model"):
        qibocal_bound.binding()
    assert values() == initial
    print("DURATION_AND_DEFAULTS", initial["qibocal_pi_amplitude"]["value"], fitted)


def test_database_snapshot_and_explicit_override_precedence(qibocal_bound, tmp_path):
    import sys

    from tests.qdash.workflow.qibocal_helpers import write_fake_runner

    qibocal_bound._config.update(
        runner_python=sys.executable, runner_script=str(write_fake_runner(tmp_path))
    )
    execute(QibocalBringUp(), qibocal_bound, tmp_path)
    snapshot = {
        name: model.model_dump() for name, model in QibocalRabiAmplitude().input_parameters.items()
    }
    for name, value in template_values(load_platform_template().parameters(), 0).items():
        snapshot[name]["value"] = value
    snapshot["qibocal_pi_duration"]["value"] = 60.0
    for snap, override, expected in [
        (None, {}, 40.0),
        (snapshot, {}, 60.0),
        (snapshot, {"qibocal_pi_duration": 80.0}, 80.0),
    ]:
        task = QibocalRabiAmplitude({"input": override})
        _, entry = execute(task, qibocal_bound, tmp_path, update=False, snapshot=snap)
        assert entry.input_parameters["qibocal_pi_duration"].value == expected
        import json

        request = json.loads((qibocal_bound.last_run_dir / "request.json").read_text())
        assert request["calibration"]["qibocal_pi_duration"] == expected
    assert values()["qibocal_pi_duration"]["value"] == 40.0


@pytest.mark.parametrize(
    "fit",
    [
        {"status": "failed", "errors": ["official fit failed"]},
        {"pi_amplitude": float("nan")},
        {"fitted_parameters": [float("inf")]},
    ],
)
def test_failed_fit_leaves_database_and_task_provenance(qibocal_bound, tmp_path, fit):
    import sys

    from tests.qdash.workflow.qibocal_helpers import write_fake_runner

    qibocal_bound._config.update(
        runner_python=sys.executable,
        runner_script=str(write_fake_runner(tmp_path, overrides={"fit": fit})),
    )
    execute(QibocalBringUp(), qibocal_bound, tmp_path)
    before = values()
    with pytest.raises(ValueError):
        execute(QibocalRabiAmplitude(), qibocal_bound, tmp_path)
    assert values() == before
    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

    record = TaskResultHistoryDocument.find_one({"name": "QibocalRabiAmplitude"}).run()
    assert record is not None
    assert record.status == "failed"
    assert record.note["provenance"]["run_dir"]
    assert not record.output_parameters


def test_unknown_backend_save_is_an_error(qibocal_bound, tmp_path):
    from types import SimpleNamespace

    from qdash.workflow.engine.task.backend_saver import BackendSaver

    task = SimpleNamespace(backend="unknown")
    saver = BackendSaver(
        state_manager=cast("Any", None),
        username="alice",
        calib_dir=str(tmp_path),
        task_manager_id="unknown",
    )
    with pytest.raises(ValueError, match="persistence policy"):
        saver.save(task, cast("Any", None), "0", qibocal_bound, True)


def test_hardware_write_entry_points_reject_bound_chip(qibocal_bound, tmp_path):
    from types import SimpleNamespace

    from qdash.api.services.calibration_github_service import CalibrationGitHubService
    from qdash.api.services.manual_update_service import ManualUpdateService
    from qdash.api.services.seed_import_service import SeedImportService
    from qdash.workflow.service.github import GitHubIntegration, GitHubPushConfig
    from qdash.workflow.worker.flows.push_props.create_props import create_chip_properties

    request: Any = SimpleNamespace(
        chip_id="emulator", qid="0", parameters={"control_amplitude": {"value": 0.3}}
    )
    for action in [
        lambda: ManualUpdateService().update_parameters(request, "proj-1", "alice"),
        lambda: SeedImportService().import_seeds(request, "proj-1", "alice"),
        lambda: CalibrationGitHubService().sync(
            cast("Any", SimpleNamespace(chip_id="emulator", project_id="proj-1"))
        ),
        lambda: GitHubIntegration("alice", "emulator", "exec", project_id="proj-1").push_files(
            GitHubPushConfig()
        ),
        lambda: create_chip_properties(
            "alice", str(tmp_path / "source"), str(tmp_path / "target"), "emulator", "proj-1"
        ),
    ]:
        with pytest.raises(SimulationBindingError):
            action()
    assert values() == {}
    assert not (tmp_path / "target").exists()


def test_apply_readback_failure_does_not_adopt(qibocal_bound, tmp_path):
    import sys

    from qdash.workflow.engine.task.types import TaskExecutionError
    from tests.qdash.workflow.qibocal_helpers import write_fake_runner

    qibocal_bound._config.update(
        runner_python=sys.executable,
        runner_script=str(
            write_fake_runner(tmp_path, overrides={"provenance": {"applied_parameters": {}}})
        ),
    )
    execute(QibocalBringUp(), qibocal_bound, tmp_path)
    before = values()
    with pytest.raises(TaskExecutionError, match="readback mismatch"):
        execute(QibocalRabiAmplitude(), qibocal_bound, tmp_path)
    assert values() == before


def test_catalog_exposes_the_runtime_input_and_output_contract():
    import json

    from tests.qdash.workflow.qibocal_helpers import REPO_ROOT

    catalog = json.loads(
        (REPO_ROOT / "src/qdash/workflow/calibtasks/task_catalog.json").read_text()
    )["backends"]["qibocal"]
    for task_class in (QibocalBringUp, QibocalRabiAmplitude, QibocalFlipping):
        metadata = next(task for task in catalog if task["name"] == task_class.name)
        assert metadata["task_type"] == task_class.task_type
        assert set(metadata["input_parameters"]) == set(task_class.input_spec)
        assert set(metadata["output_parameters"]) == set(task_class.output_spec)
        assert set(metadata["run_parameters"]) == set(task_class.run_spec)
