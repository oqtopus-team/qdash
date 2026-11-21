"""Metric scripts and dashboards: local definitions and QDash.scripts / QDash.dashboards."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from test_sdk_session import Server

from qdash.client.services.models import AbsolutePeriod, MetricInfo
from qdash.sdk import (
    Dashboard,
    MetricScriptError,
    QDash,
    QDashApiError,
    Script,
    ScriptMetric,
)

if TYPE_CHECKING:
    from pathlib import Path

SCRIPT_ID = "ms_1"
DASHBOARD_ID = "dash_1"
NOW = "2026-11-20T00:00:00Z"
ZX90 = {
    "id": "zx90_median",
    "title": "Median ZX90 gate fidelity",
    "unit": "%",
    "target": "pair",
    "hops": [1],
    "parameters": {"min_samples": {"default": 3, "kind": "integer"}},
    "has_legend": True,
}
FREQ = {"id": "qubit_freq", "title": "Frequency", "unit": "GHz", "target": "qubit"}
TREND = {
    "id": "zx90_daily_trend",
    "title": "ZX90 gate fidelity trend",
    "unit": "%",
    "target": "pair",
    "result": "series",
    "hops": [1],
    "parameters": {"interval": {"default": "day", "kind": "choice", "choices": ["day", "week"]}},
}


def script_body(
    *, revision: int = 1, active: int | None = 1, invalid: bool = False
) -> dict[str, Any]:
    revisions = [
        {
            "revision": number,
            "source": f"# {number}",
            "created_at": NOW,
            "status": "invalid" if invalid and number == revision else "valid",
            "metrics": [] if invalid and number == revision else [ZX90, FREQ],
        }
        for number in range(1, revision + 1)
    ]
    return {
        "script_id": SCRIPT_ID,
        "project_id": "project-a",
        "name": "ZX90",
        "description": "",
        "visibility": "project",
        "status": "invalid" if invalid else "valid",
        "revision": revision,
        "active_revision": active,
        "metrics": [ZX90, FREQ] if active else [],
        "template_id": None,
        "owner_username": "alice",
        "owner_user_id": "u1",
        "can_edit": True,
        "created_at": NOW,
        "updated_at": NOW,
        "source": f"# {revision}",
        "active_source": None,
        "diagnostics": [{"message": "invalid syntax", "line": 1}] if invalid else [],
        "revisions": revisions,
    }


def dashboard_body(
    *, version: int = 0, panels: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {
        "dashboard_id": DASHBOARD_ID,
        "project_id": "project-a",
        "name": "Ops",
        "description": "",
        "visibility": "project",
        "chip_id": "64Qv3",
        "panels": [
            {**panel, "script_name": "ZX90", "latest_revision": 2} for panel in (panels or [])
        ],
        "owner_username": "alice",
        "owner_user_id": "u1",
        "can_edit": True,
        "version": version,
        "created_at": NOW,
        "updated_at": NOW,
    }


def metric(info: dict[str, Any] = ZX90, revision: int = 1) -> ScriptMetric:
    return ScriptMetric(SCRIPT_ID, revision, MetricInfo.model_validate(info))


def body(request: httpx.Request) -> Any:
    return json.loads(request.content)


def test_definitions_send_nothing_and_read_files_as_text(tmp_path: Path) -> None:
    server = Server()
    path = tmp_path / "zx90.py"
    path.write_text("raise SystemExit('never run')\n", encoding="utf-8")
    QDash(server.client())

    script = Script.from_file(path, visibility="project")
    board = Dashboard("Ops")
    board.add_metric(metric())

    assert (script.name, script.source) == ("zx90", "raise SystemExit('never run')\n")
    assert server.requests == []


def test_panels_get_readable_ids_and_the_editors_default_layout() -> None:
    board = Dashboard("Ops")
    note = board.add_markdown("# Notes")
    first = board.add_metric(metric())
    second = board.add_metric(metric(), view="table", direction="forward")
    qubit = board.add_metric(
        metric(FREQ),
        period=AbsolutePeriod.model_validate(
            {"start": "2026-11-01T00:00:00+09:00", "end": "2026-11-15T00:00:00+09:00"}
        ),
    )

    assert [p.panel_id for p in board.panels] == [
        "markdown",
        "zx90_median",
        "zx90_median-2",
        "qubit_freq",
    ]
    layouts = [(p.layout.x, p.layout.y, p.layout.w, p.layout.h) for p in board.panels]
    assert layouts == [(0, 0, 12, 2), (0, 2, 6, 4), (0, 6, 6, 4), (0, 10, 6, 4)]
    assert note.config == {"content": "# Notes"}
    assert first.title == "Median ZX90 gate fidelity"
    assert first.config == {
        "script_id": SCRIPT_ID,
        "script_revision": 1,
        "metric_id": "zx90_median",
        "period": {"kind": "relative", "days": 14},
        "params": {},
        "view": "map",
        "direction": "both",
        "hops": [1],
    }
    # Wire compatible with servers before series metrics, whose config forbids extra keys.
    assert all("targets" not in (p.config or {}) for p in (first, second, qubit))
    assert second.config is not None
    assert (second.config["view"], second.config["direction"]) == ("table", "forward")
    # A qubit metric that declares no hops keeps both, as the editor does.
    assert qubit.config is not None
    assert qubit.config["hops"] == [1, 2]
    assert qubit.config["period"]["kind"] == "absolute"
    with pytest.raises(ValueError, match="already on the dashboard"):
        board.add_markdown("x", panel_id="markdown")
    with pytest.raises(TypeError):
        board.add_metric(metric(), period=True)


def test_series_metrics_get_a_timeseries_panel_of_selected_targets() -> None:
    board = Dashboard("Trend")
    trend = metric(TREND)
    assert trend.result == "series"
    assert metric().result == "scalar"
    panel = board.add_metric(trend, targets=["0>1", "1>0"], params={"interval": "week"})
    assert panel.config is not None
    assert panel.config["view"] == "timeseries"
    assert panel.config["targets"] == ["0>1", "1>0"]
    assert panel.config["params"] == {"interval": "week"}
    with pytest.raises(ValueError, match="1 to 16 targets"):
        board.add_metric(trend)
    with pytest.raises(ValueError, match="1 to 16 targets"):
        board.add_metric(trend, targets=[f"{i}>{i + 1}" for i in range(17)])
    with pytest.raises(ValueError, match="view='timeseries'"):
        board.add_metric(trend, targets=["0>1"], view="map")
    with pytest.raises(ValueError, match="'map' or 'table'"):
        board.add_metric(metric(), view="timeseries")
    with pytest.raises(ValueError, match="only to series"):
        board.add_metric(metric(), targets=["0>1"])


def test_saved_script_metric_is_bound_to_the_saved_revision() -> None:
    server = Server(
        {
            ("GET", f"/metric-scripts/{SCRIPT_ID}"): [
                httpx.Response(200, json=script_body(revision=2, active=1, invalid=True))
            ]
        }
    )
    qdash = QDash(server.client())

    active = qdash.scripts.get(SCRIPT_ID)
    assert active.metric("zx90_median") == metric()
    with pytest.raises(MetricScriptError, match="declares: zx90_median, qubit_freq"):
        active.metric("missing")

    saved = qdash.scripts.get(SCRIPT_ID, revision=2)
    assert saved.valid is False
    assert saved.diagnostics == ["line 1: invalid syntax"]
    with pytest.raises(MetricScriptError, match="did not validate") as error:
        saved.metric("zx90_median")
    assert (error.value.script_id, error.value.revision) == (SCRIPT_ID, 2)


def test_script_create_and_update_send_only_given_fields() -> None:
    server = Server(
        {
            ("POST", "/metric-scripts"): [httpx.Response(201, json=script_body())],
            ("PATCH", f"/metric-scripts/{SCRIPT_ID}"): [
                httpx.Response(200, json=script_body(revision=2, active=1, invalid=True))
            ],
        }
    )
    qdash = QDash(server.client())

    created = qdash.scripts.create(Script("ZX90", "# 1", visibility="project"))
    updated = qdash.scripts.update(created, Script("ZX90", "def broken(:"))

    assert body(server.requests[0]) == {"name": "ZX90", "source": "# 1", "visibility": "project"}
    assert body(server.requests[1]) == {
        "name": "ZX90",
        "source": "def broken(:",
        "expected_revision": 1,
    }
    assert (created.revision, updated.revision, updated.valid) == (1, 2, False)
    with pytest.raises(MetricScriptError):
        updated.metric("zx90_median")


def test_dashboard_update_sends_the_version_it_is_based_on() -> None:
    panel = {
        "panel_id": "zx90_median",
        "type": "metric_script",
        "title": "ZX90",
        "layout": {"x": 0, "y": 0, "w": 6, "h": 4},
        "config": {"script_id": SCRIPT_ID, "script_revision": 1, "metric_id": "zx90_median"},
    }
    server = Server(
        {
            ("GET", f"/dashboards/{DASHBOARD_ID}"): [
                httpx.Response(200, json=dashboard_body(version=4, panels=[panel]))
            ],
            ("PATCH", f"/dashboards/{DASHBOARD_ID}"): [
                httpx.Response(200, json=dashboard_body(version=5, panels=[panel])),
                httpx.Response(409, json={"detail": "Dashboard was changed by another save"}),
            ],
        }
    )
    qdash = QDash(server.client())

    current = qdash.dashboards.get(DASHBOARD_ID)
    edited = current.edit()
    saved = qdash.dashboards.update(current, edited)

    assert edited.panels[0].model_dump(mode="json", exclude_unset=True) == panel
    assert body(server.requests[1]) == {
        "name": "Ops",
        "description": "",
        "visibility": "project",
        "chip_id": "64Qv3",
        "panels": [panel],
        "expected_version": 4,
    }
    assert saved.version == 5
    # An ID target reads the version first; a stale save surfaces as the server's 409.
    with pytest.raises(QDashApiError) as stale:
        qdash.dashboards.update(DASHBOARD_ID, edited)
    assert stale.value.status_code == 409
    assert body(server.requests[-1])["expected_version"] == 4
    assert server.paths()[-2:] == [
        ("GET", f"/dashboards/{DASHBOARD_ID}"),
        ("PATCH", f"/dashboards/{DASHBOARD_ID}"),
    ]


def test_create_omits_unset_settings() -> None:
    server = Server({("POST", "/dashboards"): [httpx.Response(201, json=dashboard_body())]})
    qdash = QDash(server.client())

    qdash.dashboards.create(Dashboard("Ops"))

    assert body(server.requests[0]) == {"name": "Ops", "panels": []}
