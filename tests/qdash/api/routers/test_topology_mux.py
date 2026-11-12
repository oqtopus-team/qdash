"""The topology and chip MUX APIs return the topology's normalized MUXes."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from qdash.common.config.loader import ConfigLoader
from qdash.common.config.topology import load_topology
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.user import UserDocument


@pytest.fixture(autouse=True)
def bundled_topologies(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", ConfigLoader.LOCAL_CONFIG_DIR)
    load_topology.cache_clear()
    yield
    load_topology.cache_clear()


@pytest.fixture
def test_project(init_db):
    user = UserDocument(
        username="test_user",
        hashed_password="hashed",  # betterleaks:allow -- dummy hash for token-auth tests
        access_token="test_token",
        default_project_id="test_project",
        system_info=SystemInfoModel(),
    )
    user.insert()
    project = ProjectDocument(
        project_id="test_project",
        name="Test Project",
        owner_user_id=user.user_id,
        owner_username="test_user",
    )
    project.insert()
    ProjectMembershipDocument(
        project_id="test_project",
        user_id=user.user_id,
        username="test_user",
        role=ProjectRole.OWNER,
        status="active",
        invited_by_user_id=user.user_id,
        invited_by="test_user",
    ).insert()
    return project


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test_token", "X-Project-Id": "test_project"}


def _chip(chip_id: str, size: int, topology_id: str | None) -> None:
    ChipDocument(
        chip_id=chip_id,
        username="test_user",
        project_id="test_project",
        size=size,
        topology_id=topology_id,
        system_info=SystemInfoModel(),
    ).insert()


def test_topology_api_returns_canonical_muxes(test_client, test_project, auth_headers) -> None:
    response = test_client.get("/topology/square-lattice-mux-64", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert "mux" not in data
    assert data["muxes_source"] == "muxes"
    assert sorted(data["muxes"], key=int) == [str(m) for m in range(16)]
    assert data["muxes"]["0"] == [0, 1, 2, 3]
    assert data["standalone_qubits"] == []
    assert data["visualization"]["show_mux_boundaries"] is True


def test_topology_list_contains_only_the_public_templates(
    test_client, test_project, auth_headers
) -> None:
    response = test_client.get("/topology/list", headers=auth_headers)

    assert response.status_code == 200
    assert [t["id"] for t in response.json()["topologies"]] == [
        "heavy-hex-27",
        "linear-16",
        "square-lattice-mux-1024",
        "square-lattice-mux-144",
        "square-lattice-mux-16",
        "square-lattice-mux-256",
        "square-lattice-mux-64",
    ]


def test_topology_api_without_mux_lists_standalone_qubits(
    test_client, test_project, auth_headers
) -> None:
    response = test_client.get("/topology/linear-16", headers=auth_headers)

    data = response.json()["data"]
    assert data["muxes"] == {}
    assert data["standalone_qubits"] == list(range(16))


def test_topology_api_normalizes_partial_and_legacy_templates(
    test_client, test_project, auth_headers, monkeypatch, tmp_path
) -> None:
    topologies = tmp_path / "domain" / "topologies"
    topologies.mkdir(parents=True)
    qubits = "qubits: {0: {row: 0, col: 0}, 1: {row: 0, col: 1}, 2: {row: 1, col: 0}}\n"
    (topologies / "partial.yaml").write_text(
        "id: partial\nname: P\ngrid_size: 2\nnum_qubits: 3\nmuxes: {5: [1, 0]}\n"
        + qubits
        + "couplings: []\n"
    )
    (topologies / "old-off.yaml").write_text(
        "id: old-off\nname: O\ngrid_size: 2\nnum_qubits: 3\nmux: {enabled: false}\n"
        + qubits
        + "couplings: []\n"
    )
    (topologies / "ambiguous.yaml").write_text(
        "id: ambiguous\nname: A\ngrid_size: 2\nnum_qubits: 3\nmux: {enabled: true}\n"
        "muxes: {}\n" + qubits + "couplings: []\n"
    )
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", tmp_path)
    load_topology.cache_clear()

    partial = test_client.get("/topology/partial", headers=auth_headers).json()["data"]
    old_off = test_client.get("/topology/old-off", headers=auth_headers).json()["data"]
    ambiguous = test_client.get("/topology/ambiguous", headers=auth_headers)

    assert partial["muxes"] == {"5": [1, 0]}
    assert partial["mux_slots"] == {"1": 0, "0": 1}
    assert partial["standalone_qubits"] == [2]
    assert old_off["muxes"] == {}
    assert old_off["mux_slots"] == {}
    assert old_off["muxes_source"] == "legacy_disabled"
    assert old_off["standalone_qubits"] == [0, 1, 2]
    assert ambiguous.status_code == 422
    assert "both 'mux'" in ambiguous.json()["detail"]


def test_topology_api_preserves_legacy_slot_gaps(
    test_client, test_project, auth_headers, monkeypatch, tmp_path
) -> None:
    topologies = tmp_path / "domain" / "topologies"
    topologies.mkdir(parents=True)
    (topologies / "slot-gap.yaml").write_text(
        "id: slot-gap\nname: Gap\ngrid_size: 2\nnum_qubits: 2\n"
        "mux: {enabled: true, size: 2}\n"
        "qubits: {0: {row: 0, col: 0}, 2: {row: 1, col: 0}}\ncouplings: []\n"
    )
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", tmp_path)
    load_topology.cache_clear()

    response = test_client.get("/topology/slot-gap", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["muxes_source"] == "legacy_qid_div_4"
    assert data["muxes"] == {"0": [0, 2]}
    assert data["mux_slots"] == {"0": 0, "2": 2}


def test_chip_mux_list_uses_topology_membership(test_client, test_project, auth_headers) -> None:
    _chip("chip-16", 16, "square-lattice-mux-16")

    with patch("qdash.api.services.chip.service.get_task_names", return_value=["CheckRabi"]):
        listed = test_client.get("/chips/chip-16/muxes", headers=auth_headers)
        single = test_client.get("/chips/chip-16/muxes/3", headers=auth_headers)
        missing = test_client.get("/chips/chip-16/muxes/4", headers=auth_headers)

    assert listed.status_code == 200
    muxes = listed.json()["muxes"]
    assert sorted(muxes, key=int) == [str(m) for m in range(4)]
    assert muxes["2"]["qids"] == ["8", "9", "10", "11"]
    assert single.json()["qids"] == ["12", "13", "14", "15"]
    assert missing.status_code == 404


def test_chip_mux_list_keeps_legacy_chips(test_client, test_project, auth_headers) -> None:
    _chip("chip-legacy", 6, None)

    with patch("qdash.api.services.chip.service.get_task_names", return_value=["CheckRabi"]):
        listed = test_client.get("/chips/chip-legacy/muxes", headers=auth_headers)

    muxes = listed.json()["muxes"]
    assert {mux: detail["qids"] for mux, detail in muxes.items()} == {
        "0": ["0", "1", "2", "3"],
        "1": ["4", "5"],
    }


def test_chip_mux_list_rejects_missing_configured_topology(
    test_client, test_project, auth_headers
) -> None:
    _chip("chip-gone", 16, "deleted-template")

    with patch("qdash.api.services.chip.service.get_task_names", return_value=["CheckRabi"]):
        response = test_client.get("/chips/chip-gone/muxes", headers=auth_headers)

    assert response.status_code == 422
    assert "not found" in response.json()["detail"]


def test_chip_mux_list_omits_standalone_qubits(test_client, test_project, auth_headers) -> None:
    _chip("chip-linear", 16, "linear-16")

    with patch("qdash.api.services.chip.service.get_task_names", return_value=["CheckRabi"]):
        listed = test_client.get("/chips/chip-linear/muxes", headers=auth_headers)
        single = test_client.get("/chips/chip-linear/muxes/0", headers=auth_headers)

    assert listed.status_code == 200
    assert listed.json()["muxes"] == {}
    assert single.status_code == 404
