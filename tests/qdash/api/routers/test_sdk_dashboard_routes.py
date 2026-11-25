"""The Python SDK's script and dashboard authoring against the real API routes.

Each test drives a ``qdash.sdk`` session on the FastAPI test client, with the
in-process metric runtime validating script source, so request bodies, permissions, pins and
version guards are the server's own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from qdash.api.metric_runtime.template_library import TEMPLATES
from qdash.datamodel.project import ProjectRole
from qdash.dbmodel.metric_script import MetricScriptDocument
from qdash.sdk import (
    Dashboard,
    MetricScriptError,
    QDash,
    QDashApiError,
    QDashConfig,
    QDashNotFoundError,
    Script,
)
from qdash.sdk._generated._authoring import MetricScriptEvaluateRequest
from tests.qdash.api.routers.test_dashboard import (
    PROJECT,
    _create_project_member,
    _create_project_owner,
)
from tests.qdash.api.routers.test_metric_script import _seed_chip

if TYPE_CHECKING:
    from pathlib import Path

    import httpx
    from fastapi.testclient import TestClient

COLLISION_GRID = ("Type0A", "Type0B", "Type1A", "Type3A")


@pytest.fixture
def runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.qdash.api.metric_runtime.fakes import install_inprocess_runtime

    install_inprocess_runtime(monkeypatch)


def _session(test_client: TestClient, headers: dict[str, str], project_id: str = PROJECT) -> QDash:
    token = headers["Authorization"].removeprefix("Bearer ")
    config = QDashConfig(base_url="http://testserver", api_token=token, project_id=project_id)
    # TestClient is an httpx.Client that answers from the app in process.
    return QDash(config, http_client=cast("httpx.Client", test_client))


def _pins(script_id: str) -> dict[str, list[int]]:
    doc = MetricScriptDocument.find_one({"script_id": script_id}).run()
    assert doc is not None
    return {dashboard_id: pin.revisions for dashboard_id, pin in doc.pins.items()}


def test_shared_zx90_median_dashboard(test_client, init_db, runtime, tmp_path: Path) -> None:
    owner = _create_project_owner()
    member = _create_project_member(username="sdk_member")
    path = tmp_path / "zx90_median.py"
    path.write_text(TEMPLATES["zx90_median"].source, encoding="utf-8")
    qdash = _session(test_client, owner)

    script = qdash.scripts.create(Script.from_file(path, visibility="project"))
    zx90 = script.metric("zx90_median")
    board = Dashboard("ZX90 health", visibility="project", chip_id="chip-1")
    board.add_markdown("Median of every ZX90 observation per directed coupling.")
    board.add_metric(zx90, period=14, params={"min_samples": 3})
    saved = qdash.dashboards.create(board)

    assert script.name == "zx90_median"
    assert (script.revision, zx90.hops, zx90.target) == (1, [1], "pair")
    assert saved.version == 0
    stored = test_client.get(f"/dashboards/{saved.dashboard_id}", headers=member).json()
    assert stored["visibility"] == "project"
    assert [(p["panel_id"], p["layout"]) for p in stored["panels"]] == [
        ("markdown", {"x": 0, "y": 0, "w": 12, "h": 2}),
        ("zx90_median", {"x": 0, "y": 2, "w": 6, "h": 4}),
    ]
    assert stored["panels"][1]["title"] == "Median ZX90 gate fidelity"
    assert stored["panels"][1]["config"] == {
        "script_id": script.script_id,
        "script_revision": 1,
        "metric_id": "zx90_median",
        "period": {"kind": "relative", "days": 14},
        "params": {"min_samples": 3},
        "view": "map",
        "targets": [],
        "direction": "both",
        "hops": [1],
    }
    assert _pins(script.script_id) == {saved.dashboard_id: [1]}


def test_frequency_collision_grid(test_client, init_db, runtime) -> None:
    qdash = _session(test_client, _create_project_owner())

    collision = qdash.scripts.create(qdash.scripts.template("collision", visibility="project"))
    board = Dashboard("Collision grid", visibility="project")
    for index, kind in enumerate(COLLISION_GRID):
        board.add_metric(
            collision.metric(kind), period=30, layout=(6 * (index % 2), 4 * (index // 2), 6, 4)
        )
    saved = qdash.dashboards.create(board)

    panels = saved.response.panels
    assert [panel.panel_id for panel in panels] == ["type0a", "type0b", "type1a", "type3a"]
    assert [(p.layout.x, p.layout.y) for p in panels] == [(0, 0), (6, 0), (0, 4), (6, 4)]
    assert all(panel.config and panel.config["hops"] == [1, 2] for panel in panels)
    assert collision.response.template_id is None


def test_read_edit_save_refuses_a_stale_version(test_client, init_db, runtime) -> None:
    owner = _create_project_owner()
    qdash = _session(test_client, owner)
    zx90 = qdash.scripts.create(qdash.scripts.template("zx90_median")).metric("zx90_median")
    board = Dashboard("Ops")
    board.add_metric(zx90)
    created = qdash.dashboards.create(board)

    current = qdash.dashboards.get(created.dashboard_id)
    edited = current.edit()
    edited.add_markdown("Checked weekly.")
    # Someone else saves the dashboard after it was read.
    test_client.patch(
        f"/dashboards/{created.dashboard_id}", json={"name": "Renamed"}, headers=owner
    )

    with pytest.raises(QDashApiError) as stale:
        qdash.dashboards.update(current, edited)
    assert stale.value.status_code == 409
    after = qdash.dashboards.get(created.dashboard_id)
    assert (after.name, after.version, len(after.response.panels)) == ("Renamed", 1, 1)

    saved = qdash.dashboards.update(after, after.edit())
    assert saved.version == 2
    # An ID target reads the current version just before saving.
    edited.name = "Ops"
    saved = qdash.dashboards.update(created.dashboard_id, edited)
    assert (saved.version, saved.name, len(saved.response.panels)) == (3, "Ops", 2)


def test_script_updates_keep_revisions_honest(test_client, init_db, runtime) -> None:
    qdash = _session(test_client, _create_project_owner())
    source = TEMPLATES["zx90_median"].source
    first = qdash.scripts.create(Script("ZX90", source))

    unchanged = qdash.scripts.update(first, Script("ZX90", source, description="median"))
    assert (unchanged.revision, unchanged.response.revision) == (1, 1)
    assert unchanged.response.description == "median"

    broken = qdash.scripts.update(first.script_id, Script("ZX90", "def broken(:\n"))
    assert (broken.revision, broken.response.active_revision, broken.valid) == (2, 1, False)
    with pytest.raises(MetricScriptError) as error:
        broken.metric("zx90_median")
    assert error.value.script_id == first.script_id
    assert error.value.revision == 2
    assert error.value.diagnostics
    # The last valid revision is still reachable, but only when asked for explicitly.
    assert qdash.scripts.get(first.script_id).metric("zx90_median").revision == 1

    with pytest.raises(QDashApiError) as stale:
        qdash.scripts.update(first, Script("ZX90", source + "\n# v3\n"))
    assert stale.value.status_code == 409


def test_permissions_and_project_scope_are_the_servers(test_client, init_db, runtime) -> None:
    owner = _session(test_client, _create_project_owner())
    viewer = _session(
        test_client, _create_project_member(username="sdk_viewer", role=ProjectRole.VIEWER)
    )
    private = owner.scripts.create(owner.scripts.template("zx90_median"))
    board = Dashboard("Shared", visibility="project")
    board.add_metric(private.metric("zx90_median"))

    with pytest.raises(QDashApiError) as unshared:
        owner.dashboards.create(board)
    assert unshared.value.status_code == 422
    assert "private" in str(unshared.value)

    with pytest.raises(QDashApiError) as forbidden:
        viewer.dashboards.create(Dashboard("Mine"))
    assert forbidden.value.status_code == 403

    saved = owner.dashboards.create(Dashboard("Private"))
    outsider_headers = _create_project_owner(project_id="other_project", username="outsider")
    outsider = _session(test_client, outsider_headers, project_id="other_project")
    with pytest.raises(QDashNotFoundError):
        outsider.dashboards.get(saved.dashboard_id)


def test_values_keep_missing_and_counts(test_client, init_db, runtime) -> None:
    """Evaluation through the client returns cells with status, value and count as stored."""
    qdash = _session(test_client, _create_project_owner())
    _seed_chip()
    script = qdash.scripts.create(qdash.scripts.template("zx90_median"))
    request = MetricScriptEvaluateRequest.model_validate(
        {"metric_id": "zx90_median", "chip_id": "chip-1", "period": {"kind": "relative"}}
    )
    result = qdash.api.metric_script.evaluate_metric_script(
        script.script_id, **request.model_dump(mode="json", exclude_unset=True)
    )
    assert result.metric.unit == "%"
    assert result.cells
    statuses = {cell.status for cell in result.cells}
    assert statuses <= {"ok", "missing", "empty", "error"}
    assert all(cell.value is None for cell in result.cells if cell.status != "ok")
    counts = [cell.assessment.count for cell in result.cells if cell.assessment]
    assert counts
    assert all(count == 0 for count in counts)


def test_series_trend_dashboard_through_the_sdk(test_client, init_db, runtime) -> None:
    """A trend panel saves settings only, and evaluating it returns the selected series."""
    qdash = _session(test_client, _create_project_owner())
    _seed_chip()
    script = qdash.scripts.create(qdash.scripts.template("zx90_daily_trend", visibility="project"))
    trend = script.metric("zx90_daily_trend")
    assert trend.result == "series"
    board = Dashboard("ZX90 trend", visibility="project", chip_id="chip-1")
    board.add_metric(trend, period=28, targets=["0>1", "1>0"], params={"interval": "week"})
    saved = qdash.dashboards.create(board)
    config = saved.response.panels[0].config
    assert config is not None
    assert (config["view"], config["targets"]) == ("timeseries", ["0>1", "1>0"])
    assert "series" not in config and "cells" not in config

    request = MetricScriptEvaluateRequest.model_validate(
        {
            "metric_id": trend.id,
            "chip_id": "chip-1",
            "period": config["period"],
            "params": config["params"],
            "targets": config["targets"],
        }
    )
    result = qdash.api.metric_script.evaluate_metric_script(
        script.script_id, **request.model_dump(mode="json", exclude_unset=True)
    )
    assert [cell.key for cell in result.cells] == ["0>1", "1>0"]
    for cell in result.cells:
        # No task results are stored: every weekly bin is an honest gap.
        assert cell.status == "missing"
        assert cell.series
        assert all(point.value is None for point in cell.series)
        assert all(point.status == "no_data" for point in cell.series)
