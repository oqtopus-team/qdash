# ruff: noqa: RUF001
"""Tests for frequency collision analysis router endpoints."""

from __future__ import annotations

import math
from typing import Any

import pytest

from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.coupling import CouplingDocument
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.user import UserDocument

PROJECT = "collision_project"
TOPOLOGY = "square-lattice-mux-16"
ADIABATIC_LIMIT = math.sqrt(0.05 / 2.474)


def _param(value: float, unit: str) -> dict[str, Any]:
    return {"value": value, "unit": unit, "error": None, "calibrated_at": None}


def _create_project(project_id: str = PROJECT, username: str = "collision_user") -> dict[str, str]:
    token = f"{username}_token"
    user = UserDocument(
        username=username,
        hashed_password="hashed",
        access_token=token,
        default_project_id=project_id,
        system_info=SystemInfoModel(),
    )
    user.insert()
    ProjectDocument(
        project_id=project_id,
        name="Collision Project",
        owner_user_id=user.user_id,
        owner_username=user.username,
    ).insert()
    ProjectMembershipDocument(
        project_id=project_id,
        user_id=user.user_id,
        username=user.username,
        role=ProjectRole.VIEWER,
        status="active",
        invited_by_user_id=user.user_id,
        invited_by=user.username,
    ).insert()
    return {"Authorization": f"Bearer {token}", "X-Project-Id": project_id}


def _seed_chip(*, topology_id: str | None = TOPOLOGY, chip_id: str = "chip-1") -> None:
    ChipDocument(
        project_id=PROJECT,
        chip_id=chip_id,
        username="collision_user",
        size=16,
        topology_id=topology_id,
        system_info=SystemInfoModel(),
    ).insert()
    frequencies = {"0": 7.0, "1": 6.0, "2": 9.0, "3": 0.0}
    for qid, frequency in frequencies.items():
        QubitDocument(
            project_id=PROJECT,
            chip_id=chip_id,
            username="collision_user",
            qid=qid,
            data={
                "qubit_frequency": _param(frequency, "GHz"),
                # Legacy key with an explicit MHz unit.
                "anharmonicity": _param(-300.0, "MHz"),
                "t1": _param(50.0, "us"),
                "t2_echo": _param(40.0, "μs"),
            },
            system_info=SystemInfoModel(),
        ).insert()
    # Stored in reverse order and in MHz; must be found for pair 0-1.
    CouplingDocument(
        project_id=PROJECT,
        chip_id=chip_id,
        username="collision_user",
        qid="1-0",
        data={"qubit_qubit_coupling_strength": _param(8.0, "MHz")},
        system_info=SystemInfoModel(),
    ).insert()


@pytest.fixture
def headers(init_db: None) -> dict[str, str]:
    return _create_project()


def _evaluate(client, headers, body, chip_id: str = "chip-1"):
    return client.post(f"/collision-analysis/chips/{chip_id}/evaluate", json=body, headers=headers)


def test_list_checks(test_client, headers):
    response = test_client.get("/collision-analysis/checks", headers=headers)
    assert response.status_code == 200
    checks = response.json()["checks"]
    assert len(checks) == 13
    assert checks[0]["kind"] == "Type0A"
    assert checks[0]["title"] == "Type0A — Qubit quality"
    assert checks[0]["target"] == "qubit"
    type2c = next(c for c in checks if c["kind"] == "Type2C")
    assert type2c["unit"] == "MHz"
    assert type2c["parameters"] == [
        {
            "name": "two_photon_window",
            "default": 10.0,
            "min": 0.000001,
            "unit": "MHz",
            "label": "Type2C |δ₂γ| window (screening only)",
        }
    ]
    assert [e["color"] for e in checks[0]["legend"]] == [
        "#2563eb",
        "#d97706",
        "#dc2626",
        "#737373",
    ]


def test_qubit_check_cells_and_colors(test_client, headers):
    _seed_chip()
    response = _evaluate(test_client, headers, {"check": "Type0A"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["chip_id"] == "chip-1"
    assert body["target"] == "qubit"
    assert body["parameters"]["min_frequency"] == 6.5
    cells = {cell["key"]: cell for cell in body["cells"]}
    assert len(cells) == 16

    q0 = cells["Q0"]
    assert q0["qid"] == "0"
    assert q0["source"] is None and q0["hops"] is None
    assert q0["value"] == pytest.approx(6.5 / 7.0)
    assert q0["color"] == "#2563eb"
    assert q0["label"] == "0.93× within limit"
    assert [c["label"] for c in q0["checks"]] == ["min frequency", "max frequency", "T1", "T2"]
    assert q0["checks"][2]["value"] == pytest.approx(3000 / 50000)
    assert q0["checks"][3]["value"] == pytest.approx(3000 / 40000)
    assert q0["estimates"] == []

    assert cells["Q1"]["color"] == "#dc2626"
    assert cells["Q1"]["value"] == pytest.approx(6.5 / 6.0)
    # Zero is treated as a missing measurement.
    assert cells["Q3"]["value"] is None
    assert cells["Q3"]["color"] == "#737373"
    assert cells["Q3"]["label"] == "Not evaluated: qubit_frequency[Q3] is missing"
    assert cells["Q4"]["color"] == "#737373"


def test_pair_check_cells_colors_and_coupling_lookup(test_client, headers):
    _seed_chip()
    response = _evaluate(test_client, headers, {"check": "Type1A", "hops": [1]})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["target"] == "pair"
    cells = {cell["key"]: cell for cell in body["cells"]}
    assert all(cell["hops"] == 1 for cell in body["cells"])

    forward = cells["0-1"]
    assert forward["source"] == "0" and forward["target"] == "1"
    # g = 8 MHz from the reverse-keyed coupling, Δ = 1 GHz.
    assert forward["value"] == pytest.approx(2 * 0.008 / 1.0 / ADIABATIC_LIMIT)
    assert forward["color"] == "#2563eb"
    assert forward["estimates"] == []
    assert "1-0" in cells

    # Pair 0-2 has no measured coupling: default coupling is used and noted.
    pair_02 = cells["0-2"]
    assert pair_02["value"] == pytest.approx(2 * 0.008 / 2.0 / ADIABATIC_LIMIT)
    assert pair_02["estimates"] == [
        "Default coupling Q0–Q2: 0.008 GHz (default_coupling; measured coupling unavailable)"
    ]

    # Pair 1-3: control frequency 0 is missing.
    assert cells["3-1"]["color"] == "#737373"
    assert cells["3-1"]["value"] is None

    # Parameter overrides change the score.
    response = _evaluate(
        test_client,
        headers,
        {"check": "Type1A", "hops": [1], "params": {"adiabatic_limit": 0.0016}},
    )
    cells = {cell["key"]: cell for cell in response.json()["cells"]}
    assert cells["0-1"]["value"] == pytest.approx(10.0)
    assert cells["0-1"]["color"] == "#dc2626"
    assert response.json()["parameters"]["adiabatic_limit"] == 0.0016


def test_hops_two_pairs_only_within_mux(test_client, headers):
    _seed_chip()
    response = _evaluate(test_client, headers, {"check": "Type1A", "hops": [2]})
    assert response.status_code == 200
    keys = {cell["key"] for cell in response.json()["cells"]}
    # MUX 0 = [0, 1, 2, 3]: 0-3 and 1-2 are the hops-2 pairs inside it.
    assert {"0-3", "3-0", "1-2", "2-1"} <= keys
    assert all(cell["hops"] == 2 for cell in response.json()["cells"])
    # 1-5 is a hops-2 pair across MUXes and is not evaluated.
    assert "1-5" not in keys


def test_legacy_anharmonicity_with_mhz_unit(test_client, headers):
    _seed_chip()
    response = _evaluate(test_client, headers, {"check": "Type2C", "hops": [1]})
    assert response.status_code == 200
    cells = {cell["key"]: cell for cell in response.json()["cells"]}
    cell = cells["0-1"]
    # No resonator_frequency seeded: not evaluated, and α was read without estimate.
    assert cell["value"] is None
    assert cell["label"] == "Not evaluated: resonator_frequency[Q0] is missing"
    assert not any("Estimated qubit_anharmonicity" in note for note in cell["estimates"])


def test_invalid_requests(test_client, headers):
    _seed_chip()
    assert _evaluate(test_client, headers, {"check": "Type99"}).status_code == 422
    response = _evaluate(test_client, headers, {"check": "Type2C", "params": {"cnot_time": 1}})
    assert response.status_code == 422
    assert "cnot_time" in response.json()["detail"]
    assert _evaluate(test_client, headers, {"check": "Type1A", "hops": [3]}).status_code == 422
    response = _evaluate(test_client, headers, {"check": "Type1A", "params": {"cnot_time": 0}})
    assert response.status_code == 422


def test_missing_topology_returns_409(test_client, headers):
    _seed_chip(topology_id=None, chip_id="no-topology")
    response = _evaluate(test_client, headers, {"check": "Type0A"}, chip_id="no-topology")
    assert response.status_code == 409
    assert "topology" in response.json()["detail"]

    _seed_chip(topology_id="does-not-exist", chip_id="bad-topology")
    response = _evaluate(test_client, headers, {"check": "Type0A"}, chip_id="bad-topology")
    assert response.status_code == 409


def test_chip_from_other_project_returns_404(test_client, headers):
    _seed_chip()
    other = _create_project(project_id="other_collision", username="other_user")
    response = _evaluate(test_client, other, {"check": "Type0A"})
    assert response.status_code == 404
    assert _evaluate(test_client, headers, {"check": "Type0A"}, chip_id="nope").status_code == 404
