"""Tests for chip repository entity model loaders."""

from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.coupling import CouplingDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.repository.chip import MongoChipRepository


def test_get_all_qubit_models_filters_by_username(init_db) -> None:
    """Optional username filter prevents duplicate qids from other users overwriting data."""
    QubitDocument(
        project_id="project-1",
        username="admin",
        qid="20",
        chip_id="64Qv3",
        data={"readout_fidelity_0": {"value": 0.95}},
        system_info=SystemInfoModel(),
    ).insert()
    QubitDocument(
        project_id="project-1",
        username="other",
        qid="20",
        chip_id="64Qv3",
        data={"seed_only": {"value": 1.0}},
        system_info=SystemInfoModel(),
    ).insert()

    result = MongoChipRepository().get_all_qubit_models("project-1", "64Qv3", username="admin")

    assert set(result) == {"20"}
    assert result["20"].username == "admin"
    assert "readout_fidelity_0" in result["20"].data


def test_get_all_coupling_models_filters_by_username(init_db) -> None:
    """Optional username filter prevents duplicate coupling ids from other users overwriting data."""
    CouplingDocument(
        project_id="project-1",
        username="admin",
        qid="20-21",
        chip_id="64Qv3",
        data={"zx90_gate_fidelity": {"value": 0.91}},
        system_info=SystemInfoModel(),
    ).insert()
    CouplingDocument(
        project_id="project-1",
        username="other",
        qid="20-21",
        chip_id="64Qv3",
        data={"seed_only": {"value": 1.0}},
        system_info=SystemInfoModel(),
    ).insert()

    result = MongoChipRepository().get_all_coupling_models("project-1", "64Qv3", username="admin")

    assert set(result) == {"20-21"}
    assert result["20-21"].username == "admin"
    assert "zx90_gate_fidelity" in result["20-21"].data
