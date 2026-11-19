"""Tests for custom dashboard router endpoints."""

from __future__ import annotations

from typing import Any

from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.user import UserDocument

PROJECT = "dash_project"


def _create_project_owner(
    project_id: str = PROJECT, username: str = "dash_owner"
) -> dict[str, str]:
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
        name="Dashboard Project",
        owner_user_id=user.user_id,
        owner_username=user.username,
    ).insert()
    ProjectMembershipDocument(
        project_id=project_id,
        user_id=user.user_id,
        username=user.username,
        role=ProjectRole.OWNER,
        status="active",
        invited_by_user_id=user.user_id,
        invited_by=user.username,
    ).insert()
    return {"Authorization": f"Bearer {token}", "X-Project-Id": project_id}


def _create_project_member(
    *, username: str, role: ProjectRole = ProjectRole.EDITOR, project_id: str = PROJECT
) -> dict[str, str]:
    token = f"{username}_token"
    user = UserDocument(
        username=username,
        hashed_password="hashed",
        access_token=token,
        default_project_id=project_id,
        system_info=SystemInfoModel(),
    )
    user.insert()
    ProjectMembershipDocument(
        project_id=project_id,
        user_id=user.user_id,
        username=user.username,
        role=role,
        status="active",
        invited_by_user_id=user.user_id,
        invited_by=user.username,
    ).insert()
    return {"Authorization": f"Bearer {token}", "X-Project-Id": project_id}


def _panels() -> list[dict[str, Any]]:
    return [
        {
            "panel_id": "p1",
            "type": "qubit_metric",
            "title": "Qubit frequency",
            "layout": {"x": 0, "y": 0, "w": 6, "h": 4},
            "config": {"metric": "qubit_frequency"},
        },
        {
            "panel_id": "p2",
            "type": "collision_check",
            "title": "GE-GE",
            "layout": {"x": 6, "y": 0, "w": 6, "h": 4},
            "config": {"check": "Type1A", "params": {"cnot_time": 300}, "hops": [1]},
        },
        {
            "panel_id": "p3",
            "type": "markdown",
            "title": "",
            "layout": {"x": 0, "y": 4, "w": 12, "h": 2},
            "config": {"content": "# Notes"},
        },
    ]


def _create(client: Any, headers: dict[str, str], **overrides: Any) -> dict[str, Any]:
    request = {"name": "Ops", "panels": _panels(), **overrides}
    response = client.post("/custom-dashboards", json=request, headers=headers)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def test_create_get_list_update_delete(test_client, init_db):
    owner = _create_project_owner()
    created = _create(test_client, owner, description="desk", chip_id="chip-1")
    assert created["dashboard_id"].startswith("dash_")
    assert created["owner_username"] == "dash_owner"
    assert created["visibility"] == "private"
    assert created["can_edit"] is True
    assert created["chip_id"] == "chip-1"
    assert [p["panel_id"] for p in created["panels"]] == ["p1", "p2", "p3"]

    dashboard_id = created["dashboard_id"]
    got = test_client.get(f"/custom-dashboards/{dashboard_id}", headers=owner)
    assert got.status_code == 200
    assert got.json()["panels"][1]["config"]["params"] == {"cnot_time": 300}

    listed = test_client.get("/custom-dashboards", headers=owner).json()
    assert listed["total"] == 1
    assert listed["dashboards"][0]["dashboard_id"] == dashboard_id

    updated = test_client.patch(
        f"/custom-dashboards/{dashboard_id}",
        json={"name": "Ops v2", "panels": _panels()[:1], "chip_id": None},
        headers=owner,
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["name"] == "Ops v2"
    assert body["description"] == "desk"
    assert body["chip_id"] is None
    assert [p["panel_id"] for p in body["panels"]] == ["p1"]

    deleted = test_client.delete(f"/custom-dashboards/{dashboard_id}", headers=owner)
    assert deleted.status_code == 200
    assert deleted.json()["message"]
    missing = test_client.get(f"/custom-dashboards/{dashboard_id}", headers=owner)
    assert missing.status_code == 404


def test_list_sorted_by_update_time(test_client, init_db):
    owner = _create_project_owner()
    first = _create(test_client, owner, name="First")
    _create(test_client, owner, name="Second")
    test_client.patch(
        f"/custom-dashboards/{first['dashboard_id']}", json={"description": "x"}, headers=owner
    )
    names = [
        d["name"] for d in test_client.get("/custom-dashboards", headers=owner).json()["dashboards"]
    ]
    assert names == ["First", "Second"]


def test_private_dashboard_hidden_from_other_member(test_client, init_db):
    owner = _create_project_owner()
    editor = _create_project_member(username="dash_editor")
    private = _create(test_client, owner, name="Mine")

    listed = test_client.get("/custom-dashboards", headers=editor).json()
    assert listed == {"dashboards": [], "total": 0}
    assert (
        test_client.get(f"/custom-dashboards/{private['dashboard_id']}", headers=editor).status_code
        == 404
    )
    duplicated = test_client.post(
        f"/custom-dashboards/{private['dashboard_id']}/duplicate", headers=editor
    )
    assert duplicated.status_code == 404


def test_project_shared_dashboard_visible_but_not_editable_by_editor(test_client, init_db):
    owner = _create_project_owner()
    editor = _create_project_member(username="dash_editor")
    viewer = _create_project_member(username="dash_viewer", role=ProjectRole.VIEWER)
    shared = _create(test_client, owner, name="Shared", visibility="project")
    dashboard_id = shared["dashboard_id"]

    for headers in (editor, viewer):
        listed = test_client.get("/custom-dashboards", headers=headers).json()
        assert [d["dashboard_id"] for d in listed["dashboards"]] == [dashboard_id]
        assert listed["dashboards"][0]["can_edit"] is False

    patch = test_client.patch(
        f"/custom-dashboards/{dashboard_id}", json={"name": "Hijack"}, headers=editor
    )
    assert patch.status_code == 403
    delete = test_client.delete(f"/custom-dashboards/{dashboard_id}", headers=editor)
    assert delete.status_code == 403
    # Viewers lack write permission altogether.
    assert (
        test_client.post("/custom-dashboards", json={"name": "x"}, headers=viewer).status_code
        == 403
    )


def test_project_owner_can_edit_and_delete_members_shared_dashboard(test_client, init_db):
    owner = _create_project_owner()
    editor = _create_project_member(username="dash_editor")
    shared = _create(test_client, editor, name="Editor's", visibility="project")
    dashboard_id = shared["dashboard_id"]

    owner_view = test_client.get(f"/custom-dashboards/{dashboard_id}", headers=owner).json()
    assert owner_view["can_edit"] is True
    assert owner_view["owner_username"] == "dash_editor"

    patch = test_client.patch(
        f"/custom-dashboards/{dashboard_id}", json={"name": "Renamed"}, headers=owner
    )
    assert patch.status_code == 200
    assert patch.json()["name"] == "Renamed"
    assert patch.json()["owner_username"] == "dash_editor"

    delete = test_client.delete(f"/custom-dashboards/{dashboard_id}", headers=owner)
    assert delete.status_code == 200


def test_duplicate_creates_private_copy_owned_by_caller(test_client, init_db):
    owner = _create_project_owner()
    editor = _create_project_member(username="dash_editor")
    shared = _create(test_client, owner, name="Shared", visibility="project")

    response = test_client.post(
        f"/custom-dashboards/{shared['dashboard_id']}/duplicate", headers=editor
    )
    assert response.status_code == 201, response.text
    copy = response.json()
    assert copy["dashboard_id"] != shared["dashboard_id"]
    assert copy["name"] == "Shared (copy)"
    assert copy["visibility"] == "private"
    assert copy["owner_username"] == "dash_editor"
    assert copy["can_edit"] is True
    assert copy["panels"] == shared["panels"]

    owner_list = test_client.get("/custom-dashboards", headers=owner).json()
    assert [d["name"] for d in owner_list["dashboards"]] == ["Shared"]
    editor_list = test_client.get("/custom-dashboards", headers=editor).json()
    assert {d["name"] for d in editor_list["dashboards"]} == {"Shared", "Shared (copy)"}


def test_duplicate_keeps_name_within_limit(test_client, init_db):
    owner = _create_project_owner()
    source = _create(test_client, owner, name="x" * 200)

    response = test_client.post(
        f"/custom-dashboards/{source['dashboard_id']}/duplicate", headers=owner
    )
    assert response.status_code == 201, response.text
    copy = response.json()
    assert len(copy["name"]) == 200
    assert copy["name"].endswith(" (copy)")
    # The copy can be saved again under its generated name.
    saved = test_client.patch(
        f"/custom-dashboards/{copy['dashboard_id']}",
        json={"name": copy["name"]},
        headers=owner,
    )
    assert saved.status_code == 200, saved.text


def test_other_project_cannot_see_dashboard(test_client, init_db):
    owner = _create_project_owner()
    other = _create_project_owner(project_id="other_project", username="other_owner")
    shared = _create(test_client, owner, name="Shared", visibility="project")

    assert test_client.get("/custom-dashboards", headers=other).json()["total"] == 0
    assert (
        test_client.get(f"/custom-dashboards/{shared['dashboard_id']}", headers=other).status_code
        == 404
    )
    assert (
        test_client.delete(
            f"/custom-dashboards/{shared['dashboard_id']}", headers=other
        ).status_code
        == 404
    )
    # A non-member cannot read the project at all.
    cross = {**other, "X-Project-Id": PROJECT}
    assert test_client.get("/custom-dashboards", headers=cross).status_code == 403


def test_invalid_panel_config_is_rejected(test_client, init_db):
    owner = _create_project_owner()
    bad_metric = _panels()[:1]
    bad_metric[0]["config"] = {}
    response = test_client.post(
        "/custom-dashboards", json={"name": "Bad", "panels": bad_metric}, headers=owner
    )
    assert response.status_code == 422
    assert "Qubit frequency" in response.json()["detail"]
    assert "p1" in response.json()["detail"]

    bad_check = _panels()[1:2]
    bad_check[0]["config"] = {"check": "Type99"}
    response = test_client.post(
        "/custom-dashboards", json={"name": "Bad", "panels": bad_check}, headers=owner
    )
    assert response.status_code == 422
    assert "Type99" in response.json()["detail"]

    bad_param = _panels()[1:2]
    bad_param[0]["config"] = {"check": "Type2C", "params": {"cnot_time": 1}}
    response = test_client.post(
        "/custom-dashboards", json={"name": "Bad", "panels": bad_param}, headers=owner
    )
    assert response.status_code == 422
    assert "cnot_time" in response.json()["detail"]

    bad_hops = _panels()[1:2]
    bad_hops[0]["config"] = {"check": "Type1A", "hops": [3]}
    response = test_client.post(
        "/custom-dashboards", json={"name": "Bad", "panels": bad_hops}, headers=owner
    )
    assert response.status_code == 422

    duplicate_ids = _panels()
    duplicate_ids[1]["panel_id"] = "p1"
    response = test_client.post(
        "/custom-dashboards", json={"name": "Bad", "panels": duplicate_ids}, headers=owner
    )
    assert response.status_code == 422

    off_grid = _panels()[:1]
    off_grid[0]["layout"] = {"x": 8, "y": 0, "w": 6, "h": 4}
    response = test_client.post(
        "/custom-dashboards", json={"name": "Bad", "panels": off_grid}, headers=owner
    )
    assert response.status_code == 422

    created = _create(test_client, owner)
    response = test_client.patch(
        f"/custom-dashboards/{created['dashboard_id']}",
        json={"panels": bad_metric},
        headers=owner,
    )
    assert response.status_code == 422
    unchanged = test_client.get(f"/custom-dashboards/{created['dashboard_id']}", headers=owner)
    assert len(unchanged.json()["panels"]) == 3


def test_templates_listed_and_copied_on_create(test_client, init_db):
    owner = _create_project_owner()
    listed = test_client.get("/custom-dashboards/templates", headers=owner)
    assert listed.status_code == 200, listed.text
    templates = listed.json()["templates"]
    assert [t["template_id"] for t in templates] == ["frequency-collision-map"]
    assert templates[0]["panel_count"] == 8
    assert "collision_check" in templates[0]["panel_types"]

    first = _create(
        test_client, owner, name="Collisions", panels=[], template_id="frequency-collision-map"
    )
    second = _create(
        test_client, owner, name="Collisions 2", panels=[], template_id="frequency-collision-map"
    )
    assert len(first["panels"]) == 8
    checks = [p["config"]["check"] for p in first["panels"] if p["type"] == "collision_check"]
    assert checks == ["Type0A", "Type0B", "Type1A", "Type3A", "Type1C", "Type2C"]
    # Copy on create: every dashboard gets its own panel IDs.
    first_ids = {p["panel_id"] for p in first["panels"]}
    assert len(first_ids) == 8
    assert first_ids.isdisjoint(p["panel_id"] for p in second["panels"])

    # Explicit panels win over the template, and unknown templates are rejected.
    explicit = _create(test_client, owner, name="Mine", template_id="frequency-collision-map")
    assert explicit["panels"] == _panels()
    bad = test_client.post(
        "/custom-dashboards",
        json={"name": "Bad", "template_id": "nope"},
        headers=owner,
    )
    assert bad.status_code == 422
