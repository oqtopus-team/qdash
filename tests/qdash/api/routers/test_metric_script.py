"""Tests for metric script router endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest
from pymongo.errors import NetworkTimeout, OperationFailure

from qdash.api.metric_runtime import executor
from qdash.api.metric_runtime.executor import QueueFullError, RunnerUnavailableError
from qdash.api.metric_runtime.template_library import TEMPLATES
from qdash.api.schemas.metric_script import MAX_REVISIONS
from qdash.api.services import metric_script_service
from qdash.common.config.topology import load_topology
from qdash.common.utils.datetime import now
from qdash.datamodel.note import NoteModel
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.custom_dashboard import CustomDashboardDocument
from qdash.dbmodel.metric_script import MetricScriptDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.repository.custom_dashboard import MongoCustomDashboardRepository
from qdash.repository.metric_script import MongoMetricScriptRepository
from tests.qdash.api.metric_runtime.fakes import install_inprocess_runtime
from tests.qdash.api.routers.test_custom_dashboard import (
    PROJECT,
    _create_project_member,
    _create_project_owner,
)

TOPOLOGY = "square-lattice-mux-16"

RATIO = """\
from qdash_metrics import Parameter, metric


@metric(
    title="Scaled frequency",
    unit="GHz",
    parameters={"factor": Parameter(default=1.0, min=0, label="Factor")},
)
def scaled_frequency(target, ctx):
    return ctx.data["qubit_frequency"][target].latest() * ctx.params["factor"]
"""

BROKEN = "from qdash_metrics import metric\n\ndef broken(:\n"


@pytest.fixture
def runtime(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    return install_inprocess_runtime(monkeypatch)


@pytest.fixture
def users(init_db: None) -> dict[str, dict[str, str]]:
    return {
        "owner": _create_project_owner(),
        "editor": _create_project_member(username="script_editor"),
        "other": _create_project_member(username="script_other"),
        "viewer": _create_project_member(username="script_viewer", role=ProjectRole.VIEWER),
    }


def _create(client: Any, headers: dict[str, str], **body: Any) -> dict[str, Any]:
    request = {"name": "Ratio", "source": RATIO, **body}
    response = client.post("/metric-scripts", json=request, headers=headers)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def _seed_chip(chip_id: str = "chip-1", topology_id: str | None = TOPOLOGY) -> None:
    ChipDocument(
        project_id=PROJECT,
        chip_id=chip_id,
        username="dash_owner",
        size=16,
        topology_id=topology_id,
        system_info=SystemInfoModel(),
    ).insert()


def _task_result(
    *, qid: str, task_type: str, outputs: dict[str, Any], hours_ago: float, **extra: Any
) -> None:
    started = now() - timedelta(hours=hours_ago)
    TaskResultHistoryDocument(
        project_id=PROJECT,
        username="dash_owner",
        task_id=f"task-{qid}-{hours_ago}",
        name="ZX90InterleavedRandomizedBenchmarking",
        upstream_id="",
        status="completed",
        message="",
        input_parameters={},
        output_parameters=outputs,
        output_parameter_names=list(outputs),
        note={},
        user_note=NoteModel(),
        figure_path=[],
        json_figure_path=[],
        raw_data_path=[],
        start_at=started,
        end_at=started,
        elapsed_time=1.0,
        task_type=task_type,
        system_info=SystemInfoModel(),
        qid=qid,
        execution_id="exec-1",
        tags=[],
        chip_id="chip-1",
        **extra,
    ).insert()


def _fidelity(value: float) -> dict[str, Any]:
    return {"zx90_gate_fidelity": {"value": value, "unit": "a.u.", "error": 0.0}}


# --- catalog and templates ---------------------------------------------------


def test_templates_and_catalog_are_readable_by_viewers(test_client, users):
    viewer = users["viewer"]
    templates = test_client.get("/metric-scripts/templates", headers=viewer)
    assert templates.status_code == 200, templates.text
    listed = templates.json()["templates"]
    assert [t["template_id"] for t in listed] == ["getting_started", "collision", "zx90_median"]
    assert listed[2]["source"] == TEMPLATES["zx90_median"].source

    catalog = test_client.get("/metric-scripts/catalog", headers=viewer).json()
    qubit = {entry["name"]: entry for entry in catalog["qubit_metrics"]}
    coupling = {entry["name"]: entry for entry in catalog["coupling_metrics"]}
    assert qubit["qubit_anharmonicity"]["unit"] == "MHz"
    assert qubit["qubit_anharmonicity"]["scale"] == 1000
    assert coupling["zx90_gate_fidelity"]["unit"] == "%"
    assert coupling["zx90_gate_fidelity"]["title"] == "ZX90 Gate Fidelity"


# --- CRUD and visibility -------------------------------------------------------


def test_create_get_list_and_visibility(test_client, users, runtime):
    editor, other, owner, viewer = users["editor"], users["other"], users["owner"], users["viewer"]
    created = _create(test_client, editor, description="desc")
    script_id = created["script_id"]
    assert script_id.startswith("ms_") and len(script_id) == 15
    assert created["revision"] == 1
    assert created["active_revision"] == 1
    assert created["status"] == "valid"
    assert created["visibility"] == "private"
    assert created["metrics"][0]["id"] == "scaled_frequency"
    assert created["metrics"][0]["parameters"]["factor"]["kind"] == "number"
    assert created["source"] == RATIO and created["active_source"] == RATIO
    assert created["can_edit"] is True
    assert [r["revision"] for r in created["revisions"]] == [1]

    listed = test_client.get("/metric-scripts", headers=editor).json()
    assert listed["total"] == 1
    assert "source" not in listed["scripts"][0]

    # Private: other members see nothing; the project owner does not either.
    for headers in (other, viewer, owner):
        assert test_client.get("/metric-scripts", headers=headers).json()["total"] == 0
        assert test_client.get(f"/metric-scripts/{script_id}", headers=headers).status_code == 404

    shared = test_client.patch(
        f"/metric-scripts/{script_id}", json={"visibility": "project"}, headers=editor
    )
    assert shared.status_code == 200, shared.text
    assert shared.json()["revision"] == 1  # settings-only updates add no revision
    other_view = test_client.get(f"/metric-scripts/{script_id}", headers=other).json()
    assert other_view["can_edit"] is False
    assert test_client.get(f"/metric-scripts/{script_id}", headers=owner).json()["can_edit"]

    hijack = test_client.patch(f"/metric-scripts/{script_id}", json={"name": "Mine"}, headers=other)
    assert hijack.status_code == 403
    assert test_client.delete(f"/metric-scripts/{script_id}", headers=other).status_code == 403
    renamed = test_client.patch(
        f"/metric-scripts/{script_id}", json={"name": "Owner rename"}, headers=owner
    )
    assert renamed.status_code == 200
    assert renamed.json()["owner_username"] == "script_editor"

    # Viewers cannot create, validate or preview drafts.
    assert (
        test_client.post("/metric-scripts", json={"name": "x", "source": RATIO}, headers=viewer)
    ).status_code == 403

    deleted = test_client.delete(f"/metric-scripts/{script_id}", headers=owner)
    assert deleted.status_code == 200
    assert test_client.get(f"/metric-scripts/{script_id}", headers=editor).status_code == 404


def test_create_from_template_and_invalid_requests(test_client, users, runtime):
    editor = users["editor"]
    created = test_client.post(
        "/metric-scripts", json={"name": "Collisions", "template_id": "collision"}, headers=editor
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["template_id"] == "collision"
    assert body["source"] == TEMPLATES["collision"].source
    assert len(body["metrics"]) == 13

    unknown = test_client.post(
        "/metric-scripts", json={"name": "x", "template_id": "nope"}, headers=editor
    )
    assert unknown.status_code == 422
    neither = test_client.post("/metric-scripts", json={"name": "x"}, headers=editor)
    assert neither.status_code == 422
    too_long = test_client.post(
        "/metric-scripts", json={"name": "x" * 121, "source": RATIO}, headers=editor
    )
    assert too_long.status_code == 422
    too_big = test_client.post(
        "/metric-scripts", json={"name": "x", "source": "#" * (256 * 1024 + 1)}, headers=editor
    )
    assert too_big.status_code == 422
    # Multibyte text: within the character limit, over the byte limit.
    multibyte = test_client.post(
        "/metric-scripts", json={"name": "x", "source": "#" + "é" * 140000}, headers=editor
    )
    assert multibyte.status_code == 422
    assert "256 KiB" in multibyte.json()["detail"]


def test_validate_does_not_persist(test_client, users, runtime):
    editor = users["editor"]
    ok = test_client.post("/metric-scripts/validate", json={"source": RATIO}, headers=editor)
    assert ok.status_code == 200, ok.text
    assert ok.json()["ok"] is True
    assert [m["id"] for m in ok.json()["metrics"]] == ["scaled_frequency"]

    bad = test_client.post("/metric-scripts/validate", json={"source": BROKEN}, headers=editor)
    assert bad.status_code == 200
    body = bad.json()
    assert body["ok"] is False and body["metrics"] == []
    assert body["diagnostics"][0]["line"] == 3

    policy = test_client.post(
        "/metric-scripts/validate", json={"source": "import os\n"}, headers=editor
    )
    assert "not allowed" in policy.json()["diagnostics"][0]["message"]

    assert test_client.get("/metric-scripts", headers=editor).json()["total"] == 0
    viewer = test_client.post(
        "/metric-scripts/validate", json={"source": RATIO}, headers=users["viewer"]
    )
    assert viewer.status_code == 403


def test_invalid_save_keeps_last_good_revision(test_client, users, runtime):
    editor = users["editor"]
    created = _create(test_client, editor)
    script_id = created["script_id"]

    broken = test_client.patch(
        f"/metric-scripts/{script_id}", json={"source": BROKEN}, headers=editor
    )
    assert broken.status_code == 200, broken.text
    body = broken.json()
    assert body["revision"] == 2
    assert body["status"] == "invalid"
    assert body["source"] == BROKEN
    assert body["active_revision"] == 1
    assert body["active_source"] == RATIO
    assert [m["id"] for m in body["metrics"]] == ["scaled_frequency"]
    assert body["diagnostics"][0]["line"] == 3
    assert [(r["revision"], r["status"]) for r in body["revisions"]] == [
        (1, "valid"),
        (2, "invalid"),
    ]

    fixed_source = RATIO.replace("Scaled frequency", "Scaled qubit frequency")
    fixed = test_client.patch(
        f"/metric-scripts/{script_id}",
        json={"source": fixed_source, "expected_revision": 2},
        headers=editor,
    ).json()
    assert fixed["revision"] == 3
    assert fixed["status"] == "valid"
    assert fixed["active_revision"] == 3
    assert fixed["diagnostics"] == []
    assert fixed["metrics"][0]["title"] == "Scaled qubit frequency"

    # Saving the same text again is a no-op.
    same = test_client.patch(
        f"/metric-scripts/{script_id}", json={"source": fixed_source}, headers=editor
    )
    assert same.json()["revision"] == 3

    # A script that never validated has no active revision.
    never = _create(test_client, editor, name="Broken", source=BROKEN)
    assert never["status"] == "invalid"
    assert never["active_revision"] is None
    assert never["active_source"] is None


def test_expected_revision_conflict(test_client, users, runtime):
    editor = users["editor"]
    script_id = _create(test_client, editor)["script_id"]
    test_client.patch(
        f"/metric-scripts/{script_id}", json={"source": RATIO + "\n# v2\n"}, headers=editor
    )
    stale = test_client.patch(
        f"/metric-scripts/{script_id}",
        json={"source": RATIO + "\n# stale\n", "expected_revision": 1},
        headers=editor,
    )
    assert stale.status_code == 409
    assert "revision 2" in stale.json()["detail"]
    current = test_client.get(f"/metric-scripts/{script_id}", headers=editor).json()
    assert current["revision"] == 2


SOURCE_A = RATIO + "\n# saved by A\n"
SOURCE_B = RATIO + "\n# saved by B\n"
CONFLICT = "Script was changed by another save; reload it before saving"


def _stored(script_id: str) -> dict[str, Any] | None:
    """The raw stored script document."""
    stored: dict[str, Any] | None = MetricScriptDocument.get_motor_collection().find_one(
        {"script_id": script_id}
    )
    return stored


def _interleave(monkeypatch: pytest.MonkeyPatch, target: Any, name: str, other_save: Any) -> None:
    """Run ``other_save`` inside the first call of ``target.name``, then continue that call."""
    original = getattr(target, name)
    calls: list[int] = []

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not calls:
            calls.append(1)
            other_save()
        return original(*args, **kwargs)

    monkeypatch.setattr(target, name, wrapper)


def _pinned_panel(script_id: str, revision: int, panel_id: str = "p1") -> dict[str, Any]:
    return {
        "panel_id": panel_id,
        "type": "metric_script",
        "title": "Pinned",
        "layout": {"x": 0, "y": 0, "w": 6, "h": 4},
        "config": {
            "script_id": script_id,
            "metric_id": "scaled_frequency",
            "script_revision": revision,
        },
    }


@pytest.mark.parametrize("a_expected_revision", [None, 1])
def test_concurrent_source_saves_reject_the_later_one(
    test_client, users, runtime, monkeypatch, a_expected_revision
):
    editor, owner = users["editor"], users["owner"]
    script_id = _create(test_client, editor, visibility="project")["script_id"]
    winner: dict[str, Any] = {}

    def save_b_and_pin() -> None:
        # B saves while A's source is still validating; a dashboard then pins B's revision.
        response = test_client.patch(
            f"/metric-scripts/{script_id}", json={"source": SOURCE_B}, headers=owner
        )
        winner["response"] = response
        dashboard = test_client.post(
            "/custom-dashboards",
            json={"name": "Pins", "panels": [_pinned_panel(script_id, 2)]},
            headers=owner,
        )
        assert dashboard.status_code == 201, dashboard.text
        winner["stored"] = _stored(script_id)

    _interleave(monkeypatch, metric_script_service, "validate_source", save_b_and_pin)
    body: dict[str, Any] = {"source": SOURCE_A}
    if a_expected_revision is not None:
        body["expected_revision"] = a_expected_revision
    a = test_client.patch(f"/metric-scripts/{script_id}", json=body, headers=editor)

    b = winner["response"]
    assert b.status_code == 200, b.text
    assert b.json()["revision"] == 2
    assert a.status_code == 409
    assert a.json()["detail"] == CONFLICT
    assert _stored(script_id) == winner["stored"]

    current = test_client.get(f"/metric-scripts/{script_id}", headers=editor).json()
    assert current["revision"] == 2
    assert current["source"] == SOURCE_B
    assert [(r["revision"], r["source"]) for r in current["revisions"]] == [
        (1, RATIO),
        (2, SOURCE_B),
    ]
    assert SOURCE_A not in str(_stored(script_id))


def test_metadata_update_loses_to_concurrent_source_save(test_client, users, runtime, monkeypatch):
    editor, owner = users["editor"], users["owner"]
    script_id = _create(test_client, editor, visibility="project")["script_id"]
    winner: dict[str, Any] = {}

    def save_b() -> None:
        winner["response"] = test_client.patch(
            f"/metric-scripts/{script_id}", json={"source": SOURCE_B}, headers=owner
        )
        winner["stored"] = _stored(script_id)

    # A name-only update does not validate; land B's save just before A's write instead.
    _interleave(monkeypatch, MongoMetricScriptRepository, "save_if_unchanged", save_b)
    a = test_client.patch(f"/metric-scripts/{script_id}", json={"name": "Renamed"}, headers=editor)

    assert winner["response"].status_code == 200, winner["response"].text
    assert a.status_code == 409
    assert a.json()["detail"] == CONFLICT
    assert _stored(script_id) == winner["stored"]
    current = test_client.get(f"/metric-scripts/{script_id}", headers=editor).json()
    assert current["name"] == "Ratio"
    assert current["revision"] == 2
    assert current["source"] == SOURCE_B


def test_source_save_loses_to_concurrent_metadata_update(test_client, users, runtime, monkeypatch):
    editor, owner = users["editor"], users["owner"]
    script_id = _create(test_client, editor, visibility="project")["script_id"]
    winner: dict[str, Any] = {}

    def rename_b() -> None:
        winner["response"] = test_client.patch(
            f"/metric-scripts/{script_id}", json={"name": "Renamed by B"}, headers=owner
        )
        winner["stored"] = _stored(script_id)

    _interleave(monkeypatch, metric_script_service, "validate_source", rename_b)
    a = test_client.patch(f"/metric-scripts/{script_id}", json={"source": SOURCE_A}, headers=editor)

    assert winner["response"].status_code == 200, winner["response"].text
    assert winner["response"].json()["revision"] == 1
    assert a.status_code == 409
    assert _stored(script_id) == winner["stored"]
    current = test_client.get(f"/metric-scripts/{script_id}", headers=editor).json()
    assert current["name"] == "Renamed by B"
    assert current["revision"] == 1
    assert [(r["revision"], r["source"]) for r in current["revisions"]] == [(1, RATIO)]


def test_rejected_save_keeps_pinned_revision_source(test_client, users, runtime, monkeypatch):
    editor, owner = users["editor"], users["owner"]
    script_id = _create(test_client, editor, visibility="project")["script_id"]
    saved = test_client.patch(
        f"/metric-scripts/{script_id}", json={"source": SOURCE_B}, headers=editor
    )
    assert saved.status_code == 200, saved.text
    dashboard = test_client.post(
        "/custom-dashboards",
        json={"name": "Pins", "panels": [_pinned_panel(script_id, 2)]},
        headers=owner,
    )
    assert dashboard.status_code == 201, dashboard.text
    newest = RATIO + "\n# saved by B again\n"
    winner: dict[str, Any] = {}

    def save_b() -> None:
        winner["response"] = test_client.patch(
            f"/metric-scripts/{script_id}", json={"source": newest}, headers=owner
        )

    _interleave(monkeypatch, metric_script_service, "validate_source", save_b)
    a = test_client.patch(f"/metric-scripts/{script_id}", json={"source": SOURCE_A}, headers=editor)

    assert winner["response"].status_code == 200, winner["response"].text
    assert a.status_code == 409
    current = test_client.get(f"/metric-scripts/{script_id}", headers=editor).json()
    sources = {r["revision"]: r["source"] for r in current["revisions"]}
    assert sources == {1: RATIO, 2: SOURCE_B, 3: newest}
    # The pinned revision still resolves to the source it had when it was pinned.
    stored = MetricScriptDocument.find_one({"script_id": script_id}).run()
    assert stored is not None
    pinned = stored.find_revision(2)
    assert pinned is not None and pinned.source == SOURCE_B


def test_copy_uses_active_source(test_client, users, runtime):
    editor, other = users["editor"], users["other"]
    script = _create(test_client, editor, visibility="project", template_id=None)
    test_client.patch(
        f"/metric-scripts/{script['script_id']}", json={"source": BROKEN}, headers=editor
    )
    copied = test_client.post(f"/metric-scripts/{script['script_id']}/copy", headers=other)
    assert copied.status_code == 201, copied.text
    body = copied.json()
    assert body["script_id"] != script["script_id"]
    assert body["name"] == "Ratio (copy)"
    assert body["visibility"] == "private"
    assert body["owner_username"] == "script_other"
    assert body["source"] == RATIO
    assert body["revision"] == 1 and body["active_revision"] == 1
    assert body["template_id"] is None

    never = _create(test_client, editor, name="Broken", source=BROKEN)
    response = test_client.post(f"/metric-scripts/{never['script_id']}/copy", headers=editor)
    assert response.status_code == 422


def test_revision_history_is_capped_but_keeps_pins(test_client, users, runtime):
    owner = users["owner"]
    script_id = _create(test_client, owner, visibility="project")["script_id"]
    panel = {
        "panel_id": "p1",
        "type": "metric_script",
        "title": "Pinned",
        "layout": {"x": 0, "y": 0, "w": 6, "h": 4},
        "config": {"script_id": script_id, "metric_id": "scaled_frequency", "script_revision": 1},
    }
    dashboard = test_client.post(
        "/custom-dashboards", json={"name": "Pins", "panels": [panel]}, headers=owner
    )
    assert dashboard.status_code == 201, dashboard.text
    for index in range(55):
        test_client.patch(
            f"/metric-scripts/{script_id}",
            json={"source": RATIO + f"\n# {index}\n"},
            headers=owner,
        )
    body = test_client.get(f"/metric-scripts/{script_id}", headers=owner).json()
    revisions = [r["revision"] for r in body["revisions"]]
    assert body["revision"] == 56
    assert len(revisions) == 50
    assert revisions[0] == 1  # pinned by the dashboard
    assert revisions[-1] == 56
    stored = _stored_doc(script_id)
    assert stored.pins[dashboard.json()["dashboard_id"]].revisions == [1]


def _script_with_revisions(client: Any, headers: dict[str, str], count: int) -> str:
    """A shared script whose history holds revisions 1..``count``, all valid."""
    script_id: str = _create(client, headers, visibility="project")["script_id"]
    for index in range(2, count + 1):
        saved = client.patch(
            f"/metric-scripts/{script_id}",
            json={"source": RATIO + f"\n# {index}\n"},
            headers=headers,
        )
        assert saved.status_code == 200, saved.text
    assert _stored_doc(script_id).revision == count
    return script_id


def _stored_doc(script_id: str) -> MetricScriptDocument:
    doc = MetricScriptDocument.find_one({"script_id": script_id}).run()
    assert doc is not None
    return doc


def _post_dashboard(client: Any, headers: dict[str, str], panels: list[Any], **body: Any) -> Any:
    return client.post(
        "/custom-dashboards", json={"name": "Pins", "panels": panels, **body}, headers=headers
    )


def _assert_every_dashboard_pin_holds(client: Any, headers: dict[str, str]) -> None:
    """Every stored panel's revision is pinned on its script and still evaluates."""
    for dashboard in CustomDashboardDocument.find({"project_id": PROJECT}).run():
        for panel in dashboard.panels:
            if panel.type != "metric_script":
                continue
            script_id = panel.config["script_id"]
            revision = panel.config["script_revision"]
            script = _stored_doc(script_id)
            assert len(script.revisions) <= MAX_REVISIONS
            assert revision in script.pins[dashboard.dashboard_id].revisions
            evaluated = client.post(
                f"/metric-scripts/{script_id}/evaluate",
                json={"metric_id": "scaled_frequency", "chip_id": "chip-1", "revision": revision},
                headers=headers,
            )
            assert evaluated.status_code == 200, evaluated.text


@pytest.mark.parametrize(
    ("target", "name"),
    [
        (metric_script_service, "validate_source"),
        (MongoMetricScriptRepository, "save_if_unchanged"),
    ],
)
def test_pin_during_script_save_fails_the_save(
    test_client, users, runtime, monkeypatch, target, name
):
    # The script save read 50 revisions and would evict revision 1; a dashboard pins
    # revision 1 before the save writes. The pin moved the script's version on.
    _seed_chip()
    owner = users["owner"]
    script_id = _script_with_revisions(test_client, owner, MAX_REVISIONS)
    stored: dict[str, Any] = {}

    def pin_revision_1() -> None:
        stored["dashboard"] = _post_dashboard(test_client, owner, [_pinned_panel(script_id, 1)])
        stored["script"] = _stored(script_id)

    _interleave(monkeypatch, target, name, pin_revision_1)
    save = test_client.patch(
        f"/metric-scripts/{script_id}", json={"source": RATIO + "\n# 51\n"}, headers=owner
    )

    assert stored["dashboard"].status_code == 201, stored["dashboard"].text
    assert save.status_code == 409
    assert save.json()["detail"] == CONFLICT
    assert _stored(script_id) == stored["script"]
    assert _stored_doc(script_id).find_revision(1) is not None
    _assert_every_dashboard_pin_holds(test_client, owner)

    # A retry sees the pin and evicts revision 2 instead.
    retry = test_client.patch(
        f"/metric-scripts/{script_id}", json={"source": RATIO + "\n# 51\n"}, headers=owner
    )
    assert retry.status_code == 200, retry.text
    revisions = [r.revision for r in _stored_doc(script_id).revisions]
    assert revisions == [1, *range(3, 52)]
    _assert_every_dashboard_pin_holds(test_client, owner)


def test_script_save_during_pin_fails_the_dashboard_save(test_client, users, runtime, monkeypatch):
    # The dashboard validated revision 1; the script save evicts it before the pin lands.
    _seed_chip()
    owner = users["owner"]
    script_id = _script_with_revisions(test_client, owner, MAX_REVISIONS)
    stored: dict[str, Any] = {}

    def save_script() -> None:
        stored["save"] = test_client.patch(
            f"/metric-scripts/{script_id}", json={"source": RATIO + "\n# 51\n"}, headers=owner
        )

    _interleave(monkeypatch, MongoMetricScriptRepository, "add_pin", save_script)
    dashboard = _post_dashboard(test_client, owner, [_pinned_panel(script_id, 1)])

    assert stored["save"].status_code == 200, stored["save"].text
    assert dashboard.status_code == 422
    assert "revision 1 of metric script 'Ratio' was removed" in dashboard.json()["detail"]
    assert "reload the dashboard" in dashboard.json()["detail"]
    assert CustomDashboardDocument.find({"project_id": PROJECT}).count() == 0
    script = _stored_doc(script_id)
    assert script.find_revision(1) is None
    assert script.pins == {}
    assert len(script.revisions) == MAX_REVISIONS


def test_script_save_between_pin_and_dashboard_insert_keeps_the_pin(
    test_client, users, runtime, monkeypatch
):
    # The pin is registered before the dashboard document exists; the script save sees it.
    _seed_chip()
    owner = users["owner"]
    script_id = _script_with_revisions(test_client, owner, MAX_REVISIONS)
    stored: dict[str, Any] = {}

    def save_script() -> None:
        stored["pins"] = dict(_stored_doc(script_id).pins)
        stored["save"] = test_client.patch(
            f"/metric-scripts/{script_id}", json={"source": RATIO + "\n# 51\n"}, headers=owner
        )

    _interleave(monkeypatch, MongoCustomDashboardRepository, "insert", save_script)
    dashboard = _post_dashboard(test_client, owner, [_pinned_panel(script_id, 1)])

    assert dashboard.status_code == 201, dashboard.text
    assert list(stored["pins"]) == [dashboard.json()["dashboard_id"]]
    assert stored["save"].status_code == 200, stored["save"].text
    revisions = [r.revision for r in _stored_doc(script_id).revisions]
    assert revisions == [1, *range(3, 52)]
    _assert_every_dashboard_pin_holds(test_client, owner)


def test_delete_fails_when_a_dashboard_pins_the_script_meanwhile(
    test_client, users, runtime, monkeypatch
):
    owner = users["owner"]
    script_id = _create(test_client, owner, visibility="project")["script_id"]
    stored: dict[str, Any] = {}

    def pin() -> None:
        stored["dashboard"] = _post_dashboard(test_client, owner, [_pinned_panel(script_id, 1)])

    _interleave(monkeypatch, MongoMetricScriptRepository, "delete_if_unchanged", pin)
    deleted = test_client.delete(f"/metric-scripts/{script_id}", headers=owner)

    assert stored["dashboard"].status_code == 201, stored["dashboard"].text
    assert deleted.status_code == 409
    assert deleted.json()["detail"] == CONFLICT
    script = _stored_doc(script_id)
    assert list(script.pins) == [stored["dashboard"].json()["dashboard_id"]]


def test_unshare_fails_when_a_shared_dashboard_pins_the_script_meanwhile(
    test_client, users, runtime, monkeypatch
):
    owner = users["owner"]
    script_id = _create(test_client, owner, visibility="project")["script_id"]
    stored: dict[str, Any] = {}

    def pin_shared() -> None:
        stored["dashboard"] = _post_dashboard(
            test_client, owner, [_pinned_panel(script_id, 1)], visibility="project"
        )

    _interleave(monkeypatch, MongoMetricScriptRepository, "save_if_unchanged", pin_shared)
    unshare = test_client.patch(
        f"/metric-scripts/{script_id}", json={"visibility": "private"}, headers=owner
    )

    assert stored["dashboard"].status_code == 201, stored["dashboard"].text
    assert unshare.status_code == 409
    assert unshare.json()["detail"] == CONFLICT
    script = _stored_doc(script_id)
    assert script.visibility == "project"
    assert script.pins[stored["dashboard"].json()["dashboard_id"]].shared is True
    # Without the race the shared pin blocks unsharing up front, naming the dashboard.
    again = test_client.patch(
        f"/metric-scripts/{script_id}", json={"visibility": "private"}, headers=owner
    )
    assert again.status_code == 409
    assert "'Pins'" in again.json()["detail"]


def test_save_refused_when_every_revision_is_pinned(test_client, users, runtime):
    owner = users["owner"]
    script_id = _script_with_revisions(test_client, owner, MAX_REVISIONS)
    panels = [
        {
            **_pinned_panel(script_id, revision, panel_id=f"p{revision}"),
            "layout": {"x": 0, "y": revision * 4, "w": 6, "h": 4},
        }
        for revision in range(1, MAX_REVISIONS + 1)
    ]
    dashboard = _post_dashboard(test_client, owner, panels)
    assert dashboard.status_code == 201, dashboard.text
    before = _stored(script_id)

    save = test_client.patch(
        f"/metric-scripts/{script_id}", json={"source": RATIO + "\n# 51\n"}, headers=owner
    )

    assert save.status_code == 409
    assert f"pin {MAX_REVISIONS} revisions" in save.json()["detail"]
    assert "unpin dashboards" in save.json()["detail"]
    assert _stored(script_id) == before
    # Metadata saves still work.
    renamed = test_client.patch(
        f"/metric-scripts/{script_id}", json={"name": "Renamed"}, headers=owner
    )
    assert renamed.status_code == 200, renamed.text


def test_delete_and_unshare_blocked_while_dashboards_reference_script(test_client, users, runtime):
    editor = users["editor"]
    script_id = _create(test_client, editor, visibility="project")["script_id"]
    panel = {
        "panel_id": "p1",
        "type": "metric_script",
        "title": "Ratio",
        "layout": {"x": 0, "y": 0, "w": 6, "h": 4},
        "config": {"script_id": script_id, "metric_id": "scaled_frequency", "script_revision": 1},
    }
    dashboard = test_client.post(
        "/custom-dashboards",
        json={"name": "Uses ratio", "visibility": "project", "panels": [panel]},
        headers=editor,
    ).json()

    blocked = test_client.delete(f"/metric-scripts/{script_id}", headers=editor)
    assert blocked.status_code == 409
    assert "'Uses ratio'" in blocked.json()["detail"]
    assert dashboard["dashboard_id"] in blocked.json()["detail"]
    unshare = test_client.patch(
        f"/metric-scripts/{script_id}", json={"visibility": "private"}, headers=editor
    )
    assert unshare.status_code == 409

    test_client.patch(
        f"/custom-dashboards/{dashboard['dashboard_id']}", json={"panels": []}, headers=editor
    )
    assert test_client.delete(f"/metric-scripts/{script_id}", headers=editor).status_code == 200


# --- evaluation ----------------------------------------------------------------


def test_draft_evaluate_is_for_editors_only(test_client, users, runtime):
    _seed_chip()
    request = {
        "source": RATIO,
        "metric_id": "scaled_frequency",
        "chip_id": "chip-1",
        "period": {"kind": "relative", "days": 7},
        "params": {"factor": 2},
    }
    response = test_client.post("/metric-scripts/evaluate", json=request, headers=users["editor"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["script_id"] is None and body["revision"] is None
    assert body["metric"]["id"] == "scaled_frequency"
    assert body["params"] == {"factor": 2.0}
    assert len(body["cells"]) == 16
    assert {cell["status"] for cell in body["cells"]} == {"missing"}
    assert body["cells"][0]["message"] == "No qubit_frequency for Q0 in this period"
    assert body["truncated"] is False
    span = datetime.fromisoformat(body["end"]) - datetime.fromisoformat(body["start"])
    assert span == timedelta(days=7)
    assert runtime[-1]["mode"] == "evaluate"

    viewer = test_client.post("/metric-scripts/evaluate", json=request, headers=users["viewer"])
    assert viewer.status_code == 403

    broken = test_client.post(
        "/metric-scripts/evaluate", json={**request, "source": BROKEN}, headers=users["editor"]
    )
    assert broken.status_code == 422
    assert broken.json()["detail"]["diagnostics"][0]["line"] == 3


def test_saved_evaluate_for_viewers_and_errors(test_client, users, runtime):
    _seed_chip()
    _seed_chip(chip_id="no-topology", topology_id=None)
    _seed_chip(chip_id="bad-topology", topology_id="does-not-exist")
    editor, viewer = users["editor"], users["viewer"]
    script = _create(test_client, editor)
    script_id = script["script_id"]
    body = {"metric_id": "scaled_frequency", "chip_id": "chip-1"}

    # Private scripts are not visible to other members.
    assert (
        test_client.post(f"/metric-scripts/{script_id}/evaluate", json=body, headers=viewer)
    ).status_code == 404
    test_client.patch(
        f"/metric-scripts/{script_id}", json={"visibility": "project"}, headers=editor
    )
    ok = test_client.post(f"/metric-scripts/{script_id}/evaluate", json=body, headers=viewer)
    assert ok.status_code == 200, ok.text
    assert ok.json()["script_id"] == script_id
    assert ok.json()["revision"] == 1
    assert ok.json()["params"] == {"factor": 1.0}

    def evaluate(**overrides: Any) -> Any:
        return test_client.post(
            f"/metric-scripts/{script_id}/evaluate", json={**body, **overrides}, headers=viewer
        )

    assert evaluate(metric_id="nope").status_code == 422
    bad_param = evaluate(params={"factor": -1})
    assert bad_param.status_code == 422
    assert "factor" in bad_param.json()["detail"]
    assert evaluate(params={"bogus": 1}).status_code == 422
    assert evaluate(chip_id="missing").status_code == 404
    assert evaluate(chip_id="no-topology").status_code == 409
    assert evaluate(chip_id="bad-topology").status_code == 409
    assert evaluate(revision=9).status_code == 404
    naive = evaluate(period={"kind": "absolute", "start": "2026-01-01T00:00:00", "end": "x"})
    assert naive.status_code == 422

    # A pinned older revision keeps evaluating after newer saves; invalid revisions do not run.
    test_client.patch(f"/metric-scripts/{script_id}", json={"source": BROKEN}, headers=editor)
    assert evaluate(revision=1).status_code == 200
    assert evaluate().json()["revision"] == 1  # active (last good) by default
    assert evaluate(revision=2).status_code == 422


def test_queue_full_returns_429(test_client, users, monkeypatch):
    _seed_chip()

    def full(*_args: Any, **_kwargs: Any) -> Any:
        raise QueueFullError("full")

    monkeypatch.setattr(executor, "run_worker", full)
    response = test_client.post(
        "/metric-scripts/evaluate",
        json={"source": RATIO, "metric_id": "scaled_frequency", "chip_id": "chip-1"},
        headers=users["editor"],
    )
    assert response.status_code == 429
    assert response.json()["detail"] == "Metric script evaluation queue is full"


def test_runner_unavailable_returns_503_and_records_nothing(
    test_client, users, runtime, monkeypatch
):
    _seed_chip()
    editor = users["editor"]
    script = _create(test_client, editor)
    script_id = script["script_id"]

    def down(*_args: Any, **_kwargs: Any) -> Any:
        raise RunnerUnavailableError("The metric script runner is not available")

    monkeypatch.setattr(executor, "run_worker", down)
    # Template sources are cached after their first validation; start cold.
    monkeypatch.setattr(metric_script_service, "_template_validation_cache", {})

    def assert_unavailable(response: Any) -> None:
        assert response.status_code == 503, response.text
        assert response.json()["detail"] == {
            "message": "The metric script runner is not available",
            "diagnostics": [],
            "log": "",
        }

    assert_unavailable(
        test_client.post("/metric-scripts/validate", json={"source": RATIO}, headers=editor)
    )

    # Neither a new script nor a new revision is recorded while the runner is down.
    assert_unavailable(
        test_client.post("/metric-scripts", json={"name": "New", "source": RATIO}, headers=editor)
    )
    assert_unavailable(
        test_client.post(
            "/metric-scripts", json={"name": "T", "template_id": "zx90_median"}, headers=editor
        )
    )
    assert_unavailable(
        test_client.patch(
            f"/metric-scripts/{script_id}", json={"source": RATIO + "\n# v2\n"}, headers=editor
        )
    )
    saved = test_client.get(f"/metric-scripts/{script_id}", headers=editor).json()
    assert saved["revision"] == 1
    assert saved["status"] == "valid"
    assert len(saved["revisions"]) == 1
    assert test_client.get("/metric-scripts", headers=editor).json()["total"] == 1

    # Dashboard templates create their scripts through the same validation.
    assert_unavailable(
        test_client.post(
            "/custom-dashboards",
            json={"name": "Collisions", "panels": [], "template_id": "frequency-collision-map"},
            headers=users["owner"],
        )
    )
    assert test_client.get("/metric-scripts", headers=users["owner"]).json()["total"] == 0

    body = {"metric_id": "scaled_frequency", "chip_id": "chip-1"}
    assert_unavailable(
        test_client.post("/metric-scripts/evaluate", json={**body, "source": RATIO}, headers=editor)
    )
    assert_unavailable(
        test_client.post(f"/metric-scripts/{script_id}/evaluate", json=body, headers=editor)
    )


def test_missing_runner_socket_returns_503(test_client, users, monkeypatch, tmp_path):
    """The real executor in socket mode, with nothing listening at the socket path."""
    monkeypatch.setenv("METRIC_RUNNER_MODE", "socket")
    monkeypatch.setenv("METRIC_RUNNER_SOCKET", str(tmp_path / "missing.sock"))
    response = test_client.post(
        "/metric-scripts/validate", json={"source": RATIO}, headers=users["editor"]
    )
    assert response.status_code == 503, response.text
    assert "runner is not available" in response.json()["detail"]["message"]


def test_zx90_median_end_to_end_with_real_worker(test_client, users, monkeypatch):
    """Runs the real worker subprocess against task results stored in the database."""
    monkeypatch.setenv("METRIC_RUNNER_MODE", "local")
    _seed_chip()
    couplings = {f"{a}-{b}" for a, b in load_topology(TOPOLOGY).couplings}
    assert "0-1" in couplings
    for value, hours in ((0.90, 30), (0.99, 20), (0.95, 10)):
        _task_result(qid="0-1", task_type="coupling", outputs=_fidelity(value), hours_ago=hours)
    # Excluded, outside the period, and the reverse direction are not counted for 0-1.
    _task_result(
        qid="0-1", task_type="coupling", outputs=_fidelity(0.1), hours_ago=5, excluded=True
    )
    _task_result(qid="0-1", task_type="coupling", outputs=_fidelity(0.5), hours_ago=24 * 30)
    _task_result(qid="1-0", task_type="coupling", outputs=_fidelity(0.97), hours_ago=12)

    editor = users["editor"]
    created = test_client.post(
        "/metric-scripts",
        json={"name": "ZX90", "template_id": "zx90_median", "visibility": "project"},
        headers=editor,
    )
    assert created.status_code == 201, created.text
    script_id = created.json()["script_id"]
    response = test_client.post(
        f"/metric-scripts/{script_id}/evaluate",
        json={
            "metric_id": "zx90_median",
            "chip_id": "chip-1",
            "period": {"kind": "relative", "days": 14},
        },
        headers=users["viewer"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["metric"]["unit"] == "%"
    assert body["legend"]["kind"] == "continuous"
    cells = {cell["key"]: cell for cell in body["cells"]}
    assert all(cell["hops"] == 1 for cell in body["cells"])
    assert len(cells) == 2 * len(couplings)

    forward = cells["0>1"]
    assert forward["status"] == "ok"
    assert forward["value"] == pytest.approx(95.0)
    assert forward["assessment"]["count"] == 3
    assert forward["label"] == "median of 3"
    assert len(forward["references"]) == 3
    assert forward["references"][0]["metric"] == "zx90_gate_fidelity"
    assert forward["references"][0]["target"] == "0-1"

    reverse = cells["1>0"]
    assert reverse["status"] == "missing"
    assert reverse["assessment"]["count"] == 1
    assert reverse["color"] == "#737373"


@pytest.mark.parametrize("error", [NetworkTimeout, OperationFailure, RuntimeError])
@pytest.mark.parametrize("operation", ["insert", "save_if_unchanged", "delete"])
@pytest.mark.parametrize("committed", [False, True])
def test_ambiguous_dashboard_write_preserves_pins(
    test_client, users, runtime, monkeypatch, error, operation, committed
):
    owner = users["owner"]
    script_id = _create(test_client, owner)["script_id"]
    panel = _pinned_panel(script_id, 1)
    dashboard_id = None
    if operation != "insert":
        dashboard_id = _post_dashboard(test_client, owner, [panel]).json()["dashboard_id"]
    original = getattr(MongoCustomDashboardRepository, operation)

    def uncertain(self, *args, **kwargs):
        if committed:
            original(self, *args, **kwargs)
        raise error("write outcome unknown")

    monkeypatch.setattr(MongoCustomDashboardRepository, operation, uncertain)
    with pytest.raises(error):
        if operation == "insert":
            _post_dashboard(test_client, owner, [panel])
        elif operation == "delete":
            test_client.delete(f"/custom-dashboards/{dashboard_id}", headers=owner)
        else:
            test_client.patch(
                f"/custom-dashboards/{dashboard_id}", json={"panels": []}, headers=owner
            )
    # Even a noncommitted write cannot be distinguished from a lost acknowledgement.
    assert _stored_doc(script_id).pins
    assert test_client.delete(f"/metric-scripts/{script_id}", headers=owner).status_code == 409
    for dashboard in CustomDashboardDocument.find({"project_id": PROJECT}).run():
        for item in dashboard.panels:
            assert item.config["script_revision"] in _stored_doc(script_id).pinned_revisions()


def test_pin_failure_before_insert_releases_new_dashboard_pins(
    test_client, users, runtime, monkeypatch
):
    owner = users["owner"]
    script_id = _create(test_client, owner)["script_id"]
    original = MongoMetricScriptRepository.add_pin

    def fail_after_pin(self, **kwargs):
        original(self, **kwargs)
        raise NetworkTimeout("pin acknowledgement lost before dashboard insert")

    monkeypatch.setattr(MongoMetricScriptRepository, "add_pin", fail_after_pin)
    with pytest.raises(NetworkTimeout):
        _post_dashboard(test_client, owner, [_pinned_panel(script_id, 1)])
    assert CustomDashboardDocument.find({"project_id": PROJECT}).count() == 0
    assert _stored_doc(script_id).pins == {}
    assert test_client.delete(f"/metric-scripts/{script_id}", headers=owner).status_code == 200


def _make_legacy(script_id, dashboard_id, *, partial=False):
    collection = MetricScriptDocument.get_motor_collection()
    unset = {"pins_initialized": "", "version": ""}
    if not partial:
        unset["pins"] = ""
    collection.update_one({"script_id": script_id}, {"$unset": unset})
    CustomDashboardDocument.get_motor_collection().update_one(
        {"dashboard_id": dashboard_id}, {"$unset": {"version": ""}}
    )


@pytest.mark.parametrize("value", ["1", 1.0, True])
@pytest.mark.parametrize("initialized", [False, True])
@pytest.mark.parametrize("action", ["delete", "unshare", "evict", "metadata"])
def test_legacy_references_are_backfilled_before_writes(
    test_client, users, runtime, monkeypatch, action, value, initialized
):
    owner = users["owner"]
    script_id = _create(test_client, owner, visibility="project")["script_id"]
    dashboard_id = _post_dashboard(
        test_client, owner, [_pinned_panel(script_id, 1)], visibility="project"
    ).json()["dashboard_id"]
    _make_legacy(script_id, dashboard_id)
    CustomDashboardDocument.get_motor_collection().update_one(
        {"dashboard_id": dashboard_id},
        {"$set": {"panels.0.config.script_revision": value}},
    )
    MetricScriptDocument.get_motor_collection().update_one(
        {"script_id": script_id},
        {
            "$set": {"pins_initialized": initialized, "pins": {}},
            "$unset": {"pins_schema_version": ""},
        },
    )
    if action == "delete":
        assert test_client.delete(f"/metric-scripts/{script_id}", headers=owner).status_code == 409
    elif action == "unshare":
        assert (
            test_client.patch(
                f"/metric-scripts/{script_id}", json={"visibility": "private"}, headers=owner
            ).status_code
            == 409
        )
    elif action == "evict":
        monkeypatch.setattr(metric_script_service, "MAX_REVISIONS", 2)
        for index in range(3):
            response = test_client.patch(
                f"/metric-scripts/{script_id}",
                json={"source": RATIO + f"\n# {index}"},
                headers=owner,
            )
            assert response.status_code == 200, response.text
    else:
        response = test_client.patch(
            f"/custom-dashboards/{dashboard_id}", json={"name": "Renamed legacy"}, headers=owner
        )
        assert response.status_code == 200, response.text
    doc = _stored_doc(script_id)
    assert doc.pins_initialized
    assert doc.pins[dashboard_id].revisions == [1]
    assert doc.pins[dashboard_id].shared
    assert doc.find_revision(1) is not None


@pytest.mark.parametrize("initialized", [False, True])
def test_legacy_backfill_retries_concurrent_dashboard_pin(
    test_client, users, runtime, monkeypatch, initialized
):
    owner = users["owner"]
    script_id = _create(test_client, owner, visibility="project")["script_id"]
    panel = _pinned_panel(script_id, 1)
    legacy_id = _post_dashboard(test_client, owner, [panel], visibility="project").json()[
        "dashboard_id"
    ]
    _make_legacy(script_id, legacy_id)
    CustomDashboardDocument.get_motor_collection().update_one(
        {"dashboard_id": legacy_id}, {"$set": {"panels.0.config.script_revision": "1"}}
    )
    MetricScriptDocument.get_motor_collection().update_one(
        {"script_id": script_id},
        {
            "$set": {"pins_initialized": initialized, "pins": {}},
            "$unset": {"pins_schema_version": ""},
        },
    )
    collection = MetricScriptDocument.get_motor_collection()
    update = collection.update_one
    raced: list[Any] = []

    def interleaved(query, change, *args, **kwargs):
        if change.get("$set", {}).get("pins_initialized") and not raced:
            raced.append(True)
            # A second lazy migration and a new dashboard complete before our CAS.
            response = _post_dashboard(test_client, owner, [panel])
            assert response.status_code == 201, response.text
            raced.append(response.json()["dashboard_id"])
        return update(query, change, *args, **kwargs)

    monkeypatch.setattr(collection, "update_one", interleaved)
    doc = MongoMetricScriptRepository().get(project_id=PROJECT, script_id=script_id)
    assert doc is not None
    assert set(doc.pins) == {legacy_id, raced[1]}
    assert doc.pins[legacy_id].shared


def test_partial_registry_is_merged_and_empty_registry_is_completed(test_client, users, runtime):
    owner = users["owner"]
    script_id = _create(test_client, owner, visibility="project")["script_id"]
    dashboard_id = _post_dashboard(test_client, owner, [_pinned_panel(script_id, 1)]).json()[
        "dashboard_id"
    ]
    _make_legacy(script_id, dashboard_id, partial=True)
    collection = MetricScriptDocument.get_motor_collection()
    collection.update_one(
        {"script_id": script_id},
        {"$set": {"pins.dash_pending": {"revisions": [1], "shared": True, "writer": "pending"}}},
    )
    repo = MongoMetricScriptRepository()
    doc = repo.get(project_id=PROJECT, script_id=script_id)
    assert doc is not None
    assert set(doc.pins) == {dashboard_id, "dash_pending"}
    assert doc.pins["dash_pending"].writer == "pending"
    again = repo.get(project_id=PROJECT, script_id=script_id)
    assert again is not None and again.version == doc.version
    empty_id = _create(test_client, owner)["script_id"]
    _make_legacy(empty_id, "dash_absent")
    empty = repo.get(project_id=PROJECT, script_id=empty_id)
    assert empty is not None and empty.pins_initialized and empty.pins == {}
    assert test_client.delete(f"/metric-scripts/{empty_id}", headers=owner).status_code == 200


def test_unmigrated_snapshot_cannot_replace_or_delete_script(test_client, users, runtime):
    owner = users["owner"]
    script_id = _create(test_client, owner)["script_id"]
    _make_legacy(script_id, "dash_absent")
    doc = _stored_doc(script_id)  # Bypass the repository's lazy migration.
    repo = MongoMetricScriptRepository()
    assert not repo.delete_if_unchanged(doc, version=doc.version)
    assert not repo.save_if_unchanged(
        doc, revision=doc.revision, updated_at=doc.system_info.updated_at, version=doc.version
    )
    assert _stored_doc(script_id).source == RATIO


@pytest.mark.parametrize("committed", [False, True])
def test_migration_failure_retries_without_losing_references(
    test_client, users, runtime, monkeypatch, committed
):
    owner = users["owner"]
    script_id = _create(test_client, owner, visibility="project")["script_id"]
    dashboard_id = _post_dashboard(
        test_client, owner, [_pinned_panel(script_id, 1)], visibility="project"
    ).json()["dashboard_id"]
    _make_legacy(script_id, dashboard_id)
    collection = MetricScriptDocument.get_motor_collection()
    update = collection.update_one

    def interrupted(query, change, *args, **kwargs):
        if change.get("$set", {}).get("pins_initialized"):
            if committed:
                update(query, change, *args, **kwargs)
            raise NetworkTimeout("migration acknowledgement lost")
        return update(query, change, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(collection, "update_one", interrupted)
        with pytest.raises(NetworkTimeout):
            test_client.delete(f"/metric-scripts/{script_id}", headers=owner)
    assert test_client.delete(f"/metric-scripts/{script_id}", headers=owner).status_code == 409
    assert _stored_doc(script_id).pins[dashboard_id].shared


@pytest.mark.parametrize("operation", ["narrow_pin", "clear_dashboard_pins"])
@pytest.mark.parametrize("committed", [False, True])
def test_pin_release_failures_preserve_live_references(
    test_client, users, runtime, monkeypatch, operation, committed
):
    owner = users["owner"]
    script_id = _create(test_client, owner)["script_id"]
    panel = _pinned_panel(script_id, 1)
    first = _post_dashboard(test_client, owner, [panel]).json()["dashboard_id"]
    second = _post_dashboard(test_client, owner, [panel]).json()["dashboard_id"]
    original = getattr(MongoMetricScriptRepository, operation)

    def interrupted(self, **kwargs):
        if committed:
            original(self, **kwargs)
        raise NetworkTimeout("pin release acknowledgement lost")

    monkeypatch.setattr(MongoMetricScriptRepository, operation, interrupted)
    with pytest.raises(NetworkTimeout):
        if operation == "narrow_pin":
            test_client.patch(f"/custom-dashboards/{first}", json={"panels": []}, headers=owner)
        else:
            test_client.delete(f"/custom-dashboards/{first}", headers=owner)
    assert _stored_doc(script_id).pins[second].revisions == [1]
    assert test_client.delete(f"/metric-scripts/{script_id}", headers=owner).status_code == 409


def test_unacknowledged_delete_does_not_release_pins(test_client, users, runtime, monkeypatch):
    from pymongo.results import DeleteResult

    owner = users["owner"]
    script_id = _create(test_client, owner)["script_id"]
    dashboard_id = _post_dashboard(test_client, owner, [_pinned_panel(script_id, 1)]).json()[
        "dashboard_id"
    ]
    monkeypatch.setattr(CustomDashboardDocument, "delete", lambda self: DeleteResult({}, False))
    with pytest.raises(RuntimeError, match="not acknowledged"):
        test_client.delete(f"/custom-dashboards/{dashboard_id}", headers=owner)
    assert _stored_doc(script_id).pins[dashboard_id].revisions == [1]


@pytest.mark.parametrize("mode", ["duplicate", "template"])
def test_lost_insert_acknowledgement_protects_every_creation_path(
    test_client, users, runtime, monkeypatch, mode
):
    owner = users["owner"]
    script_id = _create(test_client, owner)["script_id"]
    dashboard_id = _post_dashboard(test_client, owner, [_pinned_panel(script_id, 1)]).json()[
        "dashboard_id"
    ]
    insert = MongoCustomDashboardRepository.insert
    persisted = []

    def committed(self, doc):
        insert(self, doc)
        persisted.append(doc)
        raise NetworkTimeout("insert acknowledgement lost")

    monkeypatch.setattr(MongoCustomDashboardRepository, "insert", committed)
    with pytest.raises(NetworkTimeout):
        if mode == "duplicate":
            test_client.post(f"/custom-dashboards/{dashboard_id}/duplicate", headers=owner)
        else:
            test_client.post(
                "/custom-dashboards",
                json={"name": "Template", "template_id": "frequency-collision-map"},
                headers=owner,
            )
    assert len(persisted) == 1
    for panel in persisted[0].panels:
        if panel.type == "metric_script":
            script = _stored_doc(panel.config["script_id"])
            assert (
                panel.config["script_revision"] in script.pins[persisted[0].dashboard_id].revisions
            )
            assert (
                test_client.delete(f"/metric-scripts/{script.script_id}", headers=owner).status_code
                == 409
            )


def test_dashboard_delete_invalidates_a_legacy_migration_snapshot(
    test_client, users, runtime, monkeypatch
):
    owner = users["owner"]
    script_id = _create(test_client, owner)["script_id"]
    dashboard_id = _post_dashboard(test_client, owner, [_pinned_panel(script_id, 1)]).json()[
        "dashboard_id"
    ]
    _make_legacy(script_id, dashboard_id)
    collection = MetricScriptDocument.get_motor_collection()
    update = collection.update_one
    raced = False

    def interleaved(query, change, *args, **kwargs):
        nonlocal raced
        if change.get("$set", {}).get("pins_initialized") and not raced:
            raced = True
            response = test_client.delete(f"/custom-dashboards/{dashboard_id}", headers=owner)
            assert response.status_code == 200, response.text
        return update(query, change, *args, **kwargs)

    monkeypatch.setattr(collection, "update_one", interleaved)
    doc = MongoMetricScriptRepository().get(project_id=PROJECT, script_id=script_id)
    assert doc is not None and doc.pins_initialized and doc.pins == {}
    assert test_client.delete(f"/metric-scripts/{script_id}", headers=owner).status_code == 200


@pytest.mark.parametrize("value", ["1", "1.0", " 1 ", 1.0, True])
def test_coerced_references_are_normalized_and_stay_pinned(test_client, users, runtime, value):
    owner = users["owner"]
    script_id = _create(test_client, owner, visibility="project")["script_id"]
    panel = _pinned_panel(script_id, 1)
    panel["config"].update(script_revision=value, hops=[2, "1", 2])
    created = _post_dashboard(test_client, owner, [panel], visibility="project")
    assert created.status_code == 201, created.text
    dashboard_id = created.json()["dashboard_id"]
    for response in [
        created,
        test_client.patch(
            f"/custom-dashboards/{dashboard_id}", json={"panels": [panel]}, headers=owner
        ),
    ]:
        assert response.status_code in (200, 201), response.text
        config = response.json()["panels"][0]["config"]
        assert type(config["script_revision"]) is int
        assert config["script_revision"] == 1
        assert config["hops"] == [1, 2]
        assert config["period"] == {"kind": "relative", "days": 14}
        assert _stored_doc(script_id).pins[dashboard_id].revisions == [1]
    raw = CustomDashboardDocument.get_motor_collection().find_one({"dashboard_id": dashboard_id})
    assert raw is not None
    assert type(raw["panels"][0]["config"]["script_revision"]) is int
    assert test_client.delete(f"/metric-scripts/{script_id}", headers=owner).status_code == 409
    assert (
        test_client.patch(
            f"/metric-scripts/{script_id}", json={"visibility": "private"}, headers=owner
        ).status_code
        == 409
    )
    # Copy and metadata-save legacy raw values through the same canonicalizer.
    CustomDashboardDocument.get_motor_collection().update_one(
        {"dashboard_id": dashboard_id}, {"$set": {"panels.0.config.script_revision": value}}
    )
    copied = test_client.post(f"/custom-dashboards/{dashboard_id}/duplicate", headers=owner)
    assert copied.status_code == 201, copied.text
    copy_id = copied.json()["dashboard_id"]
    assert type(copied.json()["panels"][0]["config"]["script_revision"]) is int
    assert _stored_doc(script_id).pins[copy_id].revisions == [1]
    assert (
        test_client.delete(f"/custom-dashboards/{dashboard_id}", headers=owner).status_code == 200
    )
    assert test_client.delete(f"/metric-scripts/{script_id}", headers=owner).status_code == 409
    assert test_client.delete(f"/custom-dashboards/{copy_id}", headers=owner).status_code == 200
    assert test_client.delete(f"/metric-scripts/{script_id}", headers=owner).status_code == 200


@pytest.mark.parametrize(
    "field,value",
    [
        ("script_revision", False),
        ("script_revision", 1.5),
        ("script_revision", "1.5"),
        ("script_revision", "invalid"),
        ("script_revision", None),
        ("script_revision", 2**63),
        ("script_revision", str(2**63)),
        ("script_revision", 1e100),
        ("script_id", 1),
        ("script_id", True),
        ("script_id", " "),
        ("script_id", " padded "),
    ],
)
def test_invalid_reference_never_creates_dashboard(test_client, users, runtime, field, value):
    owner = users["owner"]
    script_id = _create(test_client, owner)["script_id"]
    panel = _pinned_panel(script_id, 1)
    panel["config"][field] = value
    response = _post_dashboard(test_client, owner, [panel])
    assert response.status_code == 422, response.text
    assert CustomDashboardDocument.find({"project_id": PROJECT}).count() == 0
    assert _stored_doc(script_id).pins == {}
