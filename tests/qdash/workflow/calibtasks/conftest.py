"""Fixtures for calibration task tests."""

import pytest

from qdash.api.services.chip.config_scaffold import QIBOCAL_PRESET, simulation_binding_for_preset
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.workflow.engine.backend.qibocal import QibocalBackend


@pytest.fixture
def qibocal_bound(init_db, tmp_path):
    binding = simulation_binding_for_preset(QIBOCAL_PRESET)
    ChipDocument(
        project_id="proj-1",
        chip_id="emulator",
        username="alice",
        size=1,
        system_info={},
        simulation_binding=binding,
    ).insert()
    QubitDocument(
        project_id="proj-1", chip_id="emulator", qid="0", username="alice", data={}, system_info={}
    ).insert()
    return QibocalBackend(
        {"project_id": "proj-1", "chip_id": "emulator", "calib_data_path": str(tmp_path)}
    )
