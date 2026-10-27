"""HTTP contract of chip provisioning, the Systems endpoints, and the box catalog."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from qdash.api.dependencies import (
    get_chip_provisioning_service,
    get_chip_systems_service,
    get_config_boxes_service,
)
from qdash.api.services.chip.provisioner import ChipProvisioningService
from qdash.api.services.chip.system_files import ChipValues
from qdash.api.services.chip.systems import ChipSystemsService
from qdash.api.services.config_boxes_service import ConfigBoxesService
from qdash.common.config.qubex_layout import QubexLayout
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.datamodel.user import SystemRole
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.user import UserDocument
from tests.qdash.api.services.chip._trees import FakeRepository, quel3_rows, write_shared_tree

if TYPE_CHECKING:
    from pathlib import Path

HEADERS = {"Authorization": "Bearer test_token", "X-Project-Id": "test_project"}
ADMIN_HEADERS = {"Authorization": "Bearer admin_token", "X-Project-Id": "test_project"}


@pytest.fixture
def project(init_db: Any) -> ProjectDocument:
    user = UserDocument(
        username="test_user",
        hashed_password="hashed",
        access_token="test_token",
        default_project_id="test_project",
        system_info=SystemInfoModel(),
    )
    user.insert()
    UserDocument(
        username="admin",
        hashed_password="hashed",
        access_token="admin_token",
        default_project_id=None,
        system_role=SystemRole.ADMIN,
        system_info=SystemInfoModel(),
    ).insert()
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
def tree(tmp_path: Path, project: Any) -> Path:
    """A shared tree with chip ``src16`` and the services pointed at it."""
    from qdash.api.main import app

    write_shared_tree(tmp_path)
    ChipDocument(
        chip_id="src16",
        username="test_user",
        project_id="test_project",
        size=16,
        system_info=SystemInfoModel(),
    ).insert()
    layout_factory = lambda: QubexLayout.detect(tmp_path)  # noqa: E731
    repository_factory = lambda layout, actor: FakeRepository()  # noqa: E731
    values = lambda project_id, chip_id: ChipValues(n_qubits=16)  # noqa: E731
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_chip_provisioning_service] = lambda: ChipProvisioningService(
        layout_factory=layout_factory,
        repository_factory=repository_factory,
        chip_values=values,
        previous_chip=lambda project_id, cooldown_id: None,
    )
    app.dependency_overrides[get_chip_systems_service] = lambda: ChipSystemsService(
        layout_factory=layout_factory,
        repository_factory=repository_factory,
        chip_values=values,
        master_note=lambda project_id, chip_id: {},
    )
    app.dependency_overrides[get_config_boxes_service] = lambda: ConfigBoxesService(
        layout_factory=layout_factory, repository_factory=repository_factory
    )
    yield tmp_path
    app.dependency_overrides = previous


def test_create_chip_returns_the_provisioning_result(test_client: Any, tree: Path) -> None:
    response = test_client.post(
        "/chips",
        json={
            "chip_id": "new16",
            "size": 16,
            "topology_id": "square-lattice-mux-16",
            "inherit_wiring_from": "src16",
        },
        headers=HEADERS,
    )

    assert response.status_code == 200, response.text
    provisioning = response.json()["provisioning"]
    assert provisioning["system_ids"] == ["new16", "new16-quel3"]
    assert provisioning["inherited_from"] == "src16"
    assert provisioning["publish"]["status"] == "published"


def test_create_chip_validation_failures_are_400(test_client: Any, tree: Path) -> None:
    response = test_client.post(
        "/chips",
        json={"chip_id": "src16", "size": 16, "inherit_wiring_from": "src16"},
        headers=HEADERS,
    )

    assert response.status_code == 400
    assert "itself" in response.json()["detail"]


def test_list_and_add_systems(test_client: Any, tree: Path) -> None:
    listed = test_client.get("/chips/src16/systems", headers=HEADERS)
    assert listed.status_code == 200
    assert [s["system_id"] for s in listed.json()["systems"]] == ["src16", "src16-quel3"]
    assert listed.json()["systems"][0]["is_default"] is True

    added = test_client.post(
        "/chips/src16/systems",
        json={"backend": "quel3", "mux_ids": [1], "wiring": quel3_rows(1)},
        headers=HEADERS,
    )
    assert added.status_code == 400
    assert "already has a quel3 System" in added.json()["detail"]

    missing = test_client.get("/chips/nope/systems", headers=HEADERS)
    assert missing.status_code == 404


def test_box_catalog_is_admin_only(test_client: Any, tree: Path) -> None:
    forbidden = test_client.get("/config/boxes", headers=HEADERS)
    assert forbidden.status_code == 403

    listed = test_client.get("/config/boxes", headers=ADMIN_HEADERS)
    assert listed.status_code == 200
    assert [b["box_id"] for b in listed.json()["boxes"]] == ["BOXA", "q3"]
    assert "quel3" in listed.json()["box_types"]

    upserted = test_client.post(
        "/config/boxes",
        json={"box_id": "q4", "name": "quel3 #4", "type": "quel3"},
        headers=ADMIN_HEADERS,
    )
    assert upserted.status_code == 200, upserted.text
    assert upserted.json()["created"] is True

    bad = test_client.post(
        "/config/boxes",
        json={"box_id": "q5", "name": "x", "type": "quel1-a"},
        headers=ADMIN_HEADERS,
    )
    assert bad.status_code == 400
    assert "address and adapter" in bad.json()["detail"]
