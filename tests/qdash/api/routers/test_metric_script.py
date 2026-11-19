"""Tests for metric script router endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest

from qdash.api.metric_runtime import executor
from qdash.api.metric_runtime.executor import QueueFullError
from qdash.api.metric_runtime.template_library import TEMPLATES
from qdash.common.config.topology import load_topology
from qdash.common.utils.datetime import now
from qdash.datamodel.note import NoteModel
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
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


def test_zx90_median_end_to_end_with_real_worker(test_client, users):
    """Runs the real worker subprocess against task results stored in the database."""
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
