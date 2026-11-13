"""Real official protocols through the orchestrator, with qibocal_bound simulation storage."""

from __future__ import annotations

import os
import shutil
from dataclasses import replace

import pytest

from qdash.common.qibocal_platform import structural_fingerprint
from qdash.dbmodel.chip import ChipDocument
from qdash.workflow.calibtasks.qibocal import QibocalBringUp, QibocalRabiAmplitude
from qdash.workflow.engine.backend.qibocal import QibocalPlatformRejectedError
from tests.qdash.workflow.calibtasks.test_qibocal_database import (
    execute,
    values,
)

pytestmark = [
    pytest.mark.qibocal_emulator,
    pytest.mark.skipif(os.getenv("QDASH_QIBOCAL_INTEGRATION") != "1", reason="real runner opt-in"),
]


def test_dummy_instrument_rejected_before_acquisition(qibocal_bound, tmp_path):
    directory = tmp_path / "platforms" / "dummy"
    shutil.copytree(qibocal_bound.settings.platform_dir, directory)
    (directory / "platform.py").write_text(
        "from qibolab._core.dummy.platform import create_dummy\n\ndef create():\n    return create_dummy()\n"
    )
    chip = ChipDocument.find_one({"chip_id": "emulator"}).run()
    assert chip is not None and chip.simulation_binding is not None
    chip.simulation_binding = chip.simulation_binding.model_copy(
        update={"platform": "dummy", "template_fingerprint": structural_fingerprint(directory)}
    )
    chip.save()
    qibocal_bound._settings = replace(
        qibocal_bound.settings, platforms_dir=directory.parent, platform="dummy"
    )
    execute(QibocalBringUp(), qibocal_bound, tmp_path)
    task = QibocalRabiAmplitude()
    task.preprocess(qibocal_bound, "0")
    with pytest.raises(QibocalPlatformRejectedError, match="DummyInstrument"):
        qibocal_bound.run_protocol(task.build_request("0"), label="rejected")


def test_orchestrator_chain_twice_reads_adopted_values(qibocal_bound, tmp_path, monkeypatch):
    from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
    from qdash.workflow.engine import orchestrator as module
    from qdash.workflow.engine import task_runner
    from qdash.workflow.engine.backend.factory import create_backend
    from qdash.workflow.engine.config import CalibConfig

    monkeypatch.setattr(
        module,
        "create_backend",
        lambda backend, config: create_backend(backend, {**config, **qibocal_bound.config}),
    )
    wrapped = task_runner.execute_dynamic_task_by_qid_service
    monkeypatch.setattr(
        task_runner,
        "execute_dynamic_task_by_qid_service",
        type("TaskStub", (), {"with_options": staticmethod(lambda **_: wrapped)}),
    )
    previous = None
    for index in range(2):
        config = CalibConfig(
            username="alice",
            chip_id="emulator",
            qids=["0"],
            execution_id=f"20261113-00{index}",
            project_id="proj-1",
            backend_name="qibocal",
            enable_github_pull=False,
        )
        config.calib_data_path = str(tmp_path / f"run{index}")
        config.classifier_dir = str(tmp_path / "classifier")
        orchestrator = module.CalibOrchestrator(config)
        orchestrator.initialize()
        orchestrator.run_task("QibocalBringUp", "0")
        if previous is not None:
            assert values() == previous
        for name in ("QibocalRabiAmplitude", "QibocalFlipping"):
            before = values()["qibocal_pi_amplitude"]["value"]
            orchestrator.run_task(name, "0")
            record = TaskResultHistoryDocument.find_one(
                {"execution_id": config.execution_id, "name": name}
            ).run()
            assert record is not None
            assert record.input_parameters["qibocal_pi_amplitude"]["value"] == before
            assert record.note["provenance"]["calibration"]["qibocal_pi_amplitude"] == before
        previous = values()
        orchestrator.complete()
