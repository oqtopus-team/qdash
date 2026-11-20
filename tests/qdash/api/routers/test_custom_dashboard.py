"""Tests for custom dashboard router endpoints."""

from __future__ import annotations

from typing import Any

import pytest

from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.metric_script import MetricScriptDocument
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.user import UserDocument
from qdash.repository.custom_dashboard import MongoCustomDashboardRepository

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
            "type": "coupling_metric",
            "title": "ZX90",
            "layout": {"x": 6, "y": 0, "w": 6, "h": 4},
            "config": {"metric": "zx90_gate_fidelity"},
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
    assert got.json()["panels"][1]["config"] == {"metric": "zx90_gate_fidelity"}
    assert got.json()["panels"][1]["script_name"] is None

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


def _panel_fields(panel: dict[str, Any]) -> dict[str, Any]:
    return {key: panel[key] for key in ("panel_id", "type", "title", "layout", "config")}


@pytest.fixture
def runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.qdash.api.metric_runtime.fakes import install_inprocess_runtime

    install_inprocess_runtime(monkeypatch)


def _script(client: Any, headers: dict[str, str], **body: Any) -> dict[str, Any]:
    request = {"name": "ZX90", "template_id": "zx90_median", "visibility": "project", **body}
    response = client.post("/metric-scripts", json=request, headers=headers)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def _script_panel(script_id: str, **config: Any) -> dict[str, Any]:
    return {
        "panel_id": "s1",
        "type": "metric_script",
        "title": "Median ZX90",
        "layout": {"x": 0, "y": 0, "w": 6, "h": 4},
        "config": {
            "script_id": script_id,
            "metric_id": "zx90_median",
            "script_revision": 1,
            "period": {"kind": "relative", "days": 14},
            "params": {"min_samples": 2},
            "view": "table",
            "direction": "forward",
            "hops": [1],
            **config,
        },
    }


def test_metric_script_panel_is_pinned_and_annotated(test_client, init_db, runtime):
    owner = _create_project_owner()
    script = _script(test_client, owner)
    script_id = script["script_id"]
    created = _create(test_client, owner, name="ZX90", panels=[_script_panel(script_id)])
    panel = created["panels"][0]
    assert panel["config"]["script_revision"] == 1
    assert panel["script_name"] == "ZX90"
    assert panel["latest_revision"] == 1

    # A newer valid revision is announced, but the pinned panel does not move.
    source = script["source"] + "\n# tweak\n"
    test_client.patch(f"/metric-scripts/{script_id}", json={"source": source}, headers=owner)
    got = test_client.get(f"/custom-dashboards/{created['dashboard_id']}", headers=owner).json()
    assert got["panels"][0]["config"]["script_revision"] == 1
    assert got["panels"][0]["latest_revision"] == 2
    listed = test_client.get("/custom-dashboards", headers=owner).json()
    assert listed["dashboards"][0]["panels"][0]["latest_revision"] == 2
    # An invalid save does not advance the announced revision.
    test_client.patch(
        f"/metric-scripts/{script_id}", json={"source": "def broken(:\n"}, headers=owner
    )
    got = test_client.get(f"/custom-dashboards/{created['dashboard_id']}", headers=owner).json()
    assert got["panels"][0]["latest_revision"] == 2

    updated = test_client.patch(
        f"/custom-dashboards/{created['dashboard_id']}",
        json={"panels": [_script_panel(script_id, script_revision=2)]},
        headers=owner,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["panels"][0]["config"]["script_revision"] == 2
    # Panels pointing at an invalid revision are rejected.
    invalid = test_client.patch(
        f"/custom-dashboards/{created['dashboard_id']}",
        json={"panels": [_script_panel(script_id, script_revision=3)]},
        headers=owner,
    )
    assert invalid.status_code == 422
    assert "invalid" in invalid.json()["detail"]


def test_metric_script_panel_validation(test_client, init_db, runtime):
    owner = _create_project_owner()
    editor = _create_project_member(username="dash_editor")
    script_id = _script(test_client, owner)["script_id"]
    private_id = _script(test_client, owner, name="Mine", visibility="private")["script_id"]

    def create(panel: dict[str, Any], headers: dict[str, str] = owner, **body: Any) -> Any:
        return test_client.post(
            "/custom-dashboards",
            json={"name": "Bad", "panels": [panel], **body},
            headers=headers,
        )

    cases = [
        (_script_panel("ms_missing"), "not found"),
        (_script_panel(script_id, script_revision=7), "revision 7"),
        (_script_panel(script_id, metric_id="nope"), "unknown metric 'nope'"),
        (_script_panel(script_id, params={"min_samples": 0}), "min_samples"),
        (_script_panel(script_id, params={"bogus": 1}), "Unknown parameters: bogus"),
        (_script_panel(script_id, hops=[2]), "outside the metric's declared hops"),
        (_script_panel(script_id, view="chart"), "view"),
        (_script_panel(script_id, direction="sideways"), "direction"),
        (_script_panel(script_id, period={"kind": "relative", "days": 0}), "period"),
        (_script_panel(script_id, extra=1), "extra"),
    ]
    for panel, message in cases:
        response = create(panel)
        assert response.status_code == 422, (message, response.text)
        assert message in response.json()["detail"], (message, response.text)
        assert "Median ZX90" in response.json()["detail"]
    missing_revision = _script_panel(script_id)
    del missing_revision["config"]["script_revision"]
    response = create(missing_revision)
    assert response.status_code == 422
    assert "script_revision" in response.json()["detail"]

    # Other members cannot reference a private script they cannot see.
    assert create(_script_panel(private_id), headers=editor).status_code == 422
    # Private scripts can back private dashboards only.
    assert create(_script_panel(private_id)).status_code == 201
    shared = create(_script_panel(private_id), visibility="project")
    assert shared.status_code == 422
    assert "share it with the project" in shared.json()["detail"]
    private = create(_script_panel(private_id)).json()
    publish = test_client.patch(
        f"/custom-dashboards/{private['dashboard_id']}",
        json={"visibility": "project"},
        headers=owner,
    )
    assert publish.status_code == 422


def test_duplicate_copies_pins(test_client, init_db, runtime):
    owner = _create_project_owner()
    editor = _create_project_member(username="dash_editor")
    script = _script(test_client, owner)
    shared = _create(
        test_client,
        owner,
        name="Shared",
        visibility="project",
        panels=[_script_panel(script["script_id"])],
    )
    test_client.patch(
        f"/metric-scripts/{script['script_id']}",
        json={"source": script["source"] + "\n# v2\n"},
        headers=owner,
    )
    copy = test_client.post(
        f"/custom-dashboards/{shared['dashboard_id']}/duplicate", headers=editor
    ).json()
    assert copy["panels"][0]["config"] == shared["panels"][0]["config"]
    assert copy["panels"][0]["config"]["script_revision"] == 1
    assert copy["panels"][0]["latest_revision"] == 2
    # Copying the script does not retarget panels.
    test_client.post(f"/metric-scripts/{script['script_id']}/copy", headers=editor)
    again = test_client.get(f"/custom-dashboards/{copy['dashboard_id']}", headers=editor).json()
    assert again["panels"][0]["config"]["script_id"] == script["script_id"]


def test_templates_listed_and_copied_on_create(test_client, init_db, runtime):
    owner = _create_project_owner()
    editor = _create_project_member(username="dash_editor")
    listed = test_client.get("/custom-dashboards/templates", headers=owner)
    assert listed.status_code == 200, listed.text
    templates = listed.json()["templates"]
    assert [t["template_id"] for t in templates] == ["frequency-collision-map"]
    assert templates[0]["panel_count"] == 8
    assert templates[0]["panel_types"] == ["markdown", "metric_script", "qubit_metric"]

    first = _create(
        test_client, owner, name="Collisions", panels=[], template_id="frequency-collision-map"
    )
    assert len(first["panels"]) == 8
    script_panels = [p for p in first["panels"] if p["type"] == "metric_script"]
    assert [p["config"]["metric_id"] for p in script_panels] == [
        "Type0A",
        "Type0B",
        "Type1A",
        "Type3A",
        "Type1C",
        "Type2C",
    ]
    script_ids = {p["config"]["script_id"] for p in script_panels}
    assert len(script_ids) == 1
    script_id = script_ids.pop()
    assert all(p["config"]["script_revision"] == 1 for p in script_panels)
    assert all(p["script_name"] == "Frequency collision checks" for p in script_panels)
    assert script_panels[0]["config"]["period"] == {"kind": "relative", "days": 30}
    # Maps come first; the short reading guide sits last, beside the Type2C map it explains.
    in_order = sorted(first["panels"], key=lambda p: (p["layout"]["y"], p["layout"]["x"]))
    assert in_order[0]["type"] == "qubit_metric"
    assert in_order[-1]["type"] == "markdown"
    guide = in_order[-1]["config"]["content"]
    assert not guide.lstrip().startswith("#")
    assert "MHz" in guide
    assert "missing" in guide

    script = test_client.get(f"/metric-scripts/{script_id}", headers=editor).json()
    assert script["template_id"] == "collision"
    assert script["visibility"] == "project"
    assert script["owner_username"] == "dash_owner"

    # A second dashboard reuses the shared script; panel IDs are fresh.
    second = _create(
        test_client, editor, name="Collisions 2", panels=[], template_id="frequency-collision-map"
    )
    assert {p["config"]["script_id"] for p in second["panels"] if p["type"] == "metric_script"} == {
        script_id
    }
    first_ids = {p["panel_id"] for p in first["panels"]}
    assert len(first_ids) == 8
    assert first_ids.isdisjoint(p["panel_id"] for p in second["panels"])
    assert test_client.get("/metric-scripts", headers=editor).json()["total"] == 1

    # A shared script that no longer defines the checks is not reused.
    test_client.patch(
        f"/metric-scripts/{script_id}",
        json={
            "source": "from qdash_metrics import metric\n"
            "@metric(title='x', unit='GHz')\ndef x(target, ctx):\n    return 1\n"
        },
        headers=owner,
    )
    third = _create(
        test_client, owner, name="Collisions 3", panels=[], template_id="frequency-collision-map"
    )
    assert {p["config"]["script_id"] for p in third["panels"] if p["type"] == "metric_script"} != {
        script_id
    }

    # Explicit panels win over the template, and unknown templates are rejected.
    explicit = _create(test_client, owner, name="Mine", template_id="frequency-collision-map")
    assert [_panel_fields(p) for p in explicit["panels"]] == _panels()
    bad = test_client.post(
        "/custom-dashboards",
        json={"name": "Bad", "template_id": "nope"},
        headers=owner,
    )
    assert bad.status_code == 422


def _pins(script_id: str) -> dict[str, Any]:
    """The pins stored on a script, as plain data."""
    doc = MetricScriptDocument.find_one({"script_id": script_id}).run()
    assert doc is not None
    return {
        dashboard_id: {"revisions": pin.revisions, "shared": pin.shared}
        for dashboard_id, pin in doc.pins.items()
    }


def _new_revision(client: Any, headers: dict[str, str], script: dict[str, Any], tag: str) -> None:
    saved = client.patch(
        f"/metric-scripts/{script['script_id']}",
        json={"source": script["source"] + f"\n# {tag}\n"},
        headers=headers,
    )
    assert saved.status_code == 200, saved.text


def test_dashboard_writes_keep_script_pins_in_step(test_client, init_db, runtime):
    owner = _create_project_owner()
    script = _script(test_client, owner)
    script_id = script["script_id"]
    _new_revision(test_client, owner, script, "v2")
    second = {**_script_panel(script_id, script_revision=2), "panel_id": "s2"}
    second["layout"] = {"x": 6, "y": 0, "w": 6, "h": 4}

    created = _create(test_client, owner, panels=[_script_panel(script_id), second])
    dashboard_id = created["dashboard_id"]
    assert _pins(script_id) == {dashboard_id: {"revisions": [1, 2], "shared": False}}

    # Sharing the dashboard marks its pins shared; metadata edits leave them alone.
    shared = test_client.patch(
        f"/custom-dashboards/{dashboard_id}", json={"visibility": "project"}, headers=owner
    )
    assert shared.status_code == 200, shared.text
    assert _pins(script_id) == {dashboard_id: {"revisions": [1, 2], "shared": True}}
    renamed = test_client.patch(
        f"/custom-dashboards/{dashboard_id}", json={"name": "Renamed"}, headers=owner
    )
    assert renamed.status_code == 200, renamed.text
    assert _pins(script_id) == {dashboard_id: {"revisions": [1, 2], "shared": True}}

    # Removing a panel narrows the pin; making the dashboard private clears the flag.
    narrowed = test_client.patch(
        f"/custom-dashboards/{dashboard_id}",
        json={"panels": [second], "visibility": "private"},
        headers=owner,
    )
    assert narrowed.status_code == 200, narrowed.text
    assert _pins(script_id) == {dashboard_id: {"revisions": [2], "shared": False}}

    # A duplicate pins on its own; deleting a dashboard removes only its pin.
    copy = test_client.post(f"/custom-dashboards/{dashboard_id}/duplicate", headers=owner)
    assert copy.status_code == 201, copy.text
    copy_id = copy.json()["dashboard_id"]
    assert _pins(script_id)[copy_id] == {"revisions": [2], "shared": False}
    assert (
        test_client.delete(f"/custom-dashboards/{dashboard_id}", headers=owner).status_code == 200
    )
    assert _pins(script_id) == {copy_id: {"revisions": [2], "shared": False}}

    # Dropping every script panel clears the pin and frees the script for deletion.
    cleared = test_client.patch(
        f"/custom-dashboards/{copy_id}", json={"panels": _panels()}, headers=owner
    )
    assert cleared.status_code == 200, cleared.text
    assert _pins(script_id) == {}
    assert test_client.delete(f"/metric-scripts/{script_id}", headers=owner).status_code == 200


def test_template_dashboard_pins_its_script(test_client, init_db, runtime):
    owner = _create_project_owner()
    created = _create(
        test_client, owner, name="Collisions", panels=[], template_id="frequency-collision-map"
    )
    script_ids = {
        p["config"]["script_id"] for p in created["panels"] if p["type"] == "metric_script"
    }
    assert [_pins(script_id) for script_id in script_ids] == [
        {created["dashboard_id"]: {"revisions": [1], "shared": False}}
    ]


def _interleave(monkeypatch: pytest.MonkeyPatch, target: Any, name: str, other: Any) -> None:
    """Run ``other`` inside the first call of ``target.name``, then continue that call."""
    original = getattr(target, name)
    calls: list[int] = []

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not calls:
            calls.append(1)
            other()
        return original(*args, **kwargs)

    monkeypatch.setattr(target, name, wrapper)


def test_concurrent_updates_of_one_dashboard_keep_the_winners_pins(
    test_client, init_db, runtime, monkeypatch
):
    owner = _create_project_owner()
    script = _script(test_client, owner)
    script_id = script["script_id"]
    _new_revision(test_client, owner, script, "v2")
    _new_revision(test_client, owner, script, "v3")
    dashboard_id = _create(test_client, owner, panels=[_script_panel(script_id)])["dashboard_id"]
    winner: dict[str, Any] = {}

    def update_b() -> None:
        winner["response"] = test_client.patch(
            f"/custom-dashboards/{dashboard_id}",
            json={"panels": [_script_panel(script_id, script_revision=3)]},
            headers=owner,
        )

    # A pinned revision 2 and is about to store its panels when B's update lands.
    _interleave(monkeypatch, MongoCustomDashboardRepository, "save_if_unchanged", update_b)
    a = test_client.patch(
        f"/custom-dashboards/{dashboard_id}",
        json={"panels": [_script_panel(script_id, script_revision=2)]},
        headers=owner,
    )

    assert winner["response"].status_code == 200, winner["response"].text
    assert a.status_code == 409
    assert "reload it before saving" in a.json()["detail"]
    stored = test_client.get(f"/custom-dashboards/{dashboard_id}", headers=owner).json()
    assert stored["panels"][0]["config"]["script_revision"] == 3
    # B narrowed after A widened, so A's revision 2 is not left behind as a surplus pin.
    assert _pins(script_id) == {dashboard_id: {"revisions": [3], "shared": False}}


def test_update_racing_a_delete_leaves_no_pins(test_client, init_db, runtime, monkeypatch):
    owner = _create_project_owner()
    script = _script(test_client, owner)
    script_id = script["script_id"]
    _new_revision(test_client, owner, script, "v2")
    dashboard_id = _create(test_client, owner, panels=[_script_panel(script_id)])["dashboard_id"]
    deleted: dict[str, Any] = {}

    def delete() -> None:
        deleted["response"] = test_client.delete(
            f"/custom-dashboards/{dashboard_id}", headers=owner
        )

    _interleave(monkeypatch, MongoCustomDashboardRepository, "save_if_unchanged", delete)
    update = test_client.patch(
        f"/custom-dashboards/{dashboard_id}",
        json={"panels": [_script_panel(script_id, script_revision=2)]},
        headers=owner,
    )

    assert deleted["response"].status_code == 200
    assert update.status_code == 409
    assert test_client.get(f"/custom-dashboards/{dashboard_id}", headers=owner).status_code == 404
    assert _pins(script_id) == {}


def test_expected_version_guards_a_read_edit_save(test_client, init_db, runtime):
    owner = _create_project_owner()
    script = _script(test_client, owner)
    script_id = script["script_id"]
    _new_revision(test_client, owner, script, "v2")
    created = _create(test_client, owner, panels=[_script_panel(script_id)])
    dashboard_id = created["dashboard_id"]
    assert created["version"] == 0
    url = f"/custom-dashboards/{dashboard_id}"

    saved = test_client.patch(url, json={"name": "Ops v2", "expected_version": 0}, headers=owner)
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] == 1
    assert test_client.get(url, headers=owner).json()["version"] == 1

    # An editor still holding version 0 loses, before any pin is widened.
    stale = test_client.patch(
        url,
        json={"panels": [_script_panel(script_id, script_revision=2)], "expected_version": 0},
        headers=owner,
    )
    assert stale.status_code == 409
    assert "reload it before saving" in stale.json()["detail"]
    stored = test_client.get(url, headers=owner).json()
    assert stored["name"] == "Ops v2"
    assert stored["version"] == 1
    assert stored["panels"][0]["config"]["script_revision"] == 1
    assert _pins(script_id) == {dashboard_id: {"revisions": [1], "shared": False}}

    # Omitting expected_version keeps the unguarded update of existing callers.
    legacy = test_client.patch(url, json={"description": "desk"}, headers=owner)
    assert legacy.status_code == 200
    assert legacy.json()["version"] == 2


@pytest.mark.parametrize("value", [-1, "1", 1.0, True])
def test_expected_version_must_be_a_non_negative_integer(test_client, init_db, value):
    owner = _create_project_owner()
    dashboard_id = _create(test_client, owner)["dashboard_id"]
    response = test_client.patch(
        f"/custom-dashboards/{dashboard_id}", json={"expected_version": value}, headers=owner
    )
    assert response.status_code == 422


def test_expected_version_is_checked_at_the_compare_and_set(
    test_client, init_db, runtime, monkeypatch
):
    owner = _create_project_owner()
    dashboard_id = _create(test_client, owner)["dashboard_id"]
    url = f"/custom-dashboards/{dashboard_id}"
    other: dict[str, Any] = {}

    def concurrent() -> None:
        other["response"] = test_client.patch(url, json={"name": "B"}, headers=owner)

    # The guarded save read version 0 and passed the early check when B lands.
    _interleave(monkeypatch, MongoCustomDashboardRepository, "save_if_unchanged", concurrent)
    guarded = test_client.patch(url, json={"name": "A", "expected_version": 0}, headers=owner)

    assert other["response"].status_code == 200
    assert guarded.status_code == 409
    assert test_client.get(url, headers=owner).json()["name"] == "B"


def test_config_normalization_preserves_accepted_extra_settings():
    from qdash.api.services.custom_dashboard_service import validate_panel_configs
    from qdash.datamodel.custom_dashboard import DashboardPanelModel, PanelLayoutModel

    panel = DashboardPanelModel(
        panel_id="notes",
        type="markdown",
        layout=PanelLayoutModel(x=0, y=0, w=6, h=4),
        config={"custom_setting": {"keep": True}},
    )
    validate_panel_configs([panel])
    assert panel.config == {"content": "", "custom_setting": {"keep": True}}
