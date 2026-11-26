"""Tests for ReanalysisService: figure selection, seed outputs, and PNG previews."""

from __future__ import annotations

import base64
import http.server
import json
import threading
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import plotly.graph_objs as go
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from qdash.analysis.spectroscopy import compute_coarse_control_amplitude
from qdash.analysis.spectroscopy.estimate_resonator_frequency import Peak, Resonance
from qdash.api.schemas import reanalysis as reanalysis_schema
from qdash.api.schemas.reanalysis import (
    ReanalyzeQubitSpectroscopyParams,
    ReanalyzeQubitSpectroscopyRequest,
    ReanalyzeRequest,
    ReanalyzeResonatorSpectroscopyParams,
    ReanalyzeResonatorSpectroscopyRequest,
    ReanalyzeResponse,
)
from qdash.api.services import reanalysis_service as module
from qdash.api.services.reanalysis_service import ReanalysisService
from qdash.common.visualization.figure_metadata import set_figure_role

if TYPE_CHECKING:
    from pathlib import Path

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _heatmap(z_value: float = 0.0) -> go.Figure:
    return go.Figure(
        data=[
            go.Heatmap(
                x=[6.0, 6.1, 6.2, 6.3],
                y=[-60.0, -55.0, -50.0, -45.0, -40.0, -35.0, -30.0, -25.0],
                z=[[z_value] * 4 for _ in range(8)],
            )
        ]
    )


def _raw_figure() -> go.Figure:
    return set_figure_role(_heatmap(1.0), "raw")


def _marked_figure() -> go.Figure:
    fig = _heatmap(2.0)
    fig.add_trace(go.Scatter(x=[6.1], y=[-30.0], mode="markers"))
    return set_figure_role(fig, "marked")


def _write(path: Path, fig: go.Figure) -> str:
    path.write_text(fig.to_json(), encoding="utf-8")
    return str(path)


def _doc(paths: list[str], *, name: str, run_parameters: dict[str, Any] | None = None) -> Any:
    return SimpleNamespace(
        task_id="task-1",
        name=name,
        chip_id="chip",
        qid="1",
        run_parameters=run_parameters or {},
        json_figure_path=paths,
    )


def _is_raw(fig: go.Figure) -> bool:
    return len(fig.data) == 1 and fig.data[0].z[0][0] == 1.0


def _outputs(response: ReanalyzeResponse) -> dict[str, tuple[float, str]]:
    return {p.name: (p.value, p.unit) for p in response.output_parameters}


# ── Raw figure selection ────────────────────────────────────────────────────


def test_load_raw_figure_prefers_raw_suffix_when_marked_comes_first(tmp_path: Path) -> None:
    paths = [
        _write(tmp_path / "CheckQubitSpectroscopy_1_marked_0.json", _marked_figure()),
        _write(tmp_path / "CheckQubitSpectroscopy_1_raw_1.json", _raw_figure()),
    ]

    fig = ReanalysisService._load_raw_figure(_doc(paths, name="CheckQubitSpectroscopy"))

    assert _is_raw(fig)


def test_load_raw_figure_prefers_raw_suffix_when_raw_comes_first(tmp_path: Path) -> None:
    paths = [
        _write(tmp_path / "CheckQubitSpectroscopy_1_raw_0.json", _raw_figure()),
        _write(tmp_path / "CheckQubitSpectroscopy_1_marked_1.json", _marked_figure()),
    ]

    fig = ReanalysisService._load_raw_figure(_doc(paths, name="CheckQubitSpectroscopy"))

    assert _is_raw(fig)


def test_load_raw_figure_uses_figure_role_when_filenames_have_no_suffix(tmp_path: Path) -> None:
    paths = [
        _write(tmp_path / "CheckQubitSpectroscopy_1_0.json", _marked_figure()),
        _write(tmp_path / "CheckQubitSpectroscopy_1_1.json", _raw_figure()),
    ]

    fig = ReanalysisService._load_raw_figure(_doc(paths, name="CheckQubitSpectroscopy"))

    assert _is_raw(fig)


def test_load_raw_figure_falls_back_to_single_legacy_figure(tmp_path: Path) -> None:
    legacy = _heatmap(3.0)  # no role metadata, no suffix
    paths = [_write(tmp_path / "CheckQubitSpectroscopy_1.json", legacy)]

    fig = ReanalysisService._load_raw_figure(_doc(paths, name="CheckQubitSpectroscopy"))

    assert fig.data[0].z[0][0] == 3.0


def test_load_raw_figure_uses_first_of_unlabeled_legacy_pair(tmp_path: Path) -> None:
    # Records without role metadata predate the marked-first order: raw came first.
    legacy_raw = _heatmap(1.0)
    legacy_marked = _heatmap(2.0)
    legacy_marked.add_trace(go.Scatter(x=[6.1], y=[-30.0], mode="markers"))
    paths = [
        _write(tmp_path / "CheckQubitSpectroscopy_1_0.json", legacy_raw),
        _write(tmp_path / "CheckQubitSpectroscopy_1_1.json", legacy_marked),
    ]

    fig = ReanalysisService._load_raw_figure(_doc(paths, name="CheckQubitSpectroscopy"))

    assert _is_raw(fig)


def test_load_raw_figure_rejects_marked_with_missing_raw(tmp_path: Path) -> None:
    paths = [
        _write(tmp_path / "CheckQubitSpectroscopy_1_0.json", _marked_figure()),
        str(tmp_path / "CheckQubitSpectroscopy_1_1.json"),
    ]

    with pytest.raises(HTTPException) as excinfo:
        ReanalysisService._load_raw_figure(_doc(paths, name="CheckQubitSpectroscopy"))

    assert excinfo.value.status_code == 410


def test_load_raw_figure_rejects_marked_with_malformed_raw(tmp_path: Path) -> None:
    malformed = tmp_path / "CheckQubitSpectroscopy_1_1.json"
    malformed.write_text("{not json", encoding="utf-8")
    paths = [
        _write(tmp_path / "CheckQubitSpectroscopy_1_0.json", _marked_figure()),
        str(malformed),
    ]

    with pytest.raises(HTTPException) as excinfo:
        ReanalysisService._load_raw_figure(_doc(paths, name="CheckQubitSpectroscopy"))

    assert excinfo.value.status_code == 500


def test_load_raw_figure_rejects_single_marked_figure(tmp_path: Path) -> None:
    paths = [_write(tmp_path / "CheckQubitSpectroscopy_1_0.json", _marked_figure())]

    with pytest.raises(HTTPException) as excinfo:
        ReanalysisService._load_raw_figure(_doc(paths, name="CheckQubitSpectroscopy"))

    assert excinfo.value.status_code == 409


def test_load_raw_figure_reports_missing_file(tmp_path: Path) -> None:
    paths = [str(tmp_path / "CheckQubitSpectroscopy_1_raw_1.json")]

    with pytest.raises(HTTPException) as excinfo:
        ReanalysisService._load_raw_figure(_doc(paths, name="CheckQubitSpectroscopy"))

    assert excinfo.value.status_code == 410


def test_load_raw_figure_requires_a_json_figure() -> None:
    with pytest.raises(HTTPException) as excinfo:
        ReanalysisService._load_raw_figure(_doc([], name="CheckQubitSpectroscopy"))

    assert excinfo.value.status_code == 409


# ── Qubit spectroscopy seeds ────────────────────────────────────────────────


def _qubit_service(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, repr_db: float
) -> tuple[ReanalysisService, dict[str, go.Figure]]:
    paths = [
        _write(tmp_path / "CheckQubitSpectroscopy_1_marked_0.json", _marked_figure()),
        _write(tmp_path / "CheckQubitSpectroscopy_1_raw_1.json", _raw_figure()),
    ]
    doc = _doc(paths, name="CheckQubitSpectroscopy")
    service = ReanalysisService()
    monkeypatch.setattr(service, "_load_source_doc", lambda **_: doc)
    seen: dict[str, go.Figure] = {}

    def fake_estimate(fig: go.Figure, _config: Any, retry_with_trim: bool) -> Any:
        seen["input"] = fig
        f01 = SimpleNamespace(frequency=7.123, repr_db=repr_db, quality_level=4)
        result = SimpleNamespace(f01=f01, f12=None, anharmonicity=None)
        return go.Figure(fig), result

    monkeypatch.setattr(module, "estimate_and_mark_qubit_figure", fake_estimate)
    return service, seen


def test_qubit_reanalysis_returns_coarse_seeds_and_marks_amplitude(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    service, seen = _qubit_service(monkeypatch, tmp_path, repr_db=-30.0)

    response = service.reanalyze_qubit_spectroscopy(
        project_id="p",
        chip_id="chip",
        qid="1",
        params=ReanalyzeQubitSpectroscopyParams(),
    )

    assert _is_raw(seen["input"])
    outputs = _outputs(response)
    expected_amplitude = min(10 ** (-30.0 / 20) * 10 ** (10.0 / 20), 1.0)
    assert outputs["coarse_qubit_frequency"] == (7.123, "GHz")
    assert outputs["qubit_frequency"] == (7.123, "GHz")
    assert outputs["coarse_control_amplitude"][0] == pytest.approx(expected_amplitude)
    assert outputs["coarse_control_amplitude"][1] == "a.u."
    assert outputs["f01_repr_db"] == (-30.0, "dB")
    assert outputs["f01_quality_level"] == (4.0, "a.u.")
    annotations = [a["text"] for a in response.figure["layout"].get("annotations", [])]
    assert f"coarse A = {expected_amplitude:.4f} a.u." in annotations
    assert response.image_base64 is None
    assert response.image_media_type is None


def test_qubit_reanalysis_caps_coarse_amplitude(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    service, _ = _qubit_service(monkeypatch, tmp_path, repr_db=0.0)

    response = service.reanalyze_qubit_spectroscopy(
        project_id="p",
        chip_id="chip",
        qid="1",
        params=ReanalyzeQubitSpectroscopyParams(),
    )

    assert _outputs(response)["coarse_control_amplitude"][0] == 1.0


def test_coarse_amplitude_matches_workflow_formula() -> None:
    amplitude, marker_db = compute_coarse_control_amplitude(-25.0)

    assert amplitude == pytest.approx(min(10 ** (-25.0 / 20) * 10 ** (10.0 / 20), 1.0))
    assert marker_db == pytest.approx(-15.0)


# ── Resonator spectroscopy seeds ────────────────────────────────────────────


def _resonator_service(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, resonance_count: int = 4
) -> ReanalysisService:
    paths = [
        _write(tmp_path / "CheckResonatorSpectroscopy_1_marked_0.json", _marked_figure()),
        _write(tmp_path / "CheckResonatorSpectroscopy_1_raw_1.json", _raw_figure()),
    ]
    doc = _doc(paths, name="CheckResonatorSpectroscopy")
    service = ReanalysisService()
    monkeypatch.setattr(service, "_load_source_doc", lambda **_: doc)
    resonances = [
        Resonance(high_power_peaks=None, low_power_peak=Peak(x=i, y=6, prominence=1.0))
        for i in range(resonance_count)
    ]
    frequencies = [6.0, 6.1, 6.2, 6.3][:resonance_count]

    def fake_estimate(fig: go.Figure, _config: Any) -> Any:
        assert _is_raw(fig)
        return resonances, [], frequencies

    monkeypatch.setattr(module, "estimate_resonator_frequency_from_figure", fake_estimate)
    monkeypatch.setattr(module, "estimate_minimum_usable_power", lambda *_a, **_k: -40.0)
    return service


def test_resonator_reanalysis_returns_optimal_power_and_readout_amplitude(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    service = _resonator_service(monkeypatch, tmp_path)

    response = service.reanalyze_resonator_spectroscopy(
        project_id="p",
        chip_id="chip",
        qid="1",
        params=ReanalyzeResonatorSpectroscopyParams(bare_shift_estimator_type="config"),
    )

    # Same fixture and values as CheckResonatorSpectroscopy.postprocess's own test.
    outputs = _outputs(response)
    assert outputs["readout_frequency"] == (6.3, "GHz")
    assert outputs["optimal_power"] == (-35.0, "dB")
    assert outputs["readout_amplitude"][0] == pytest.approx(10 ** (-35.0 / 20))
    assert outputs["readout_amplitude"][1] == "a.u."
    stars = [
        trace
        for trace in response.figure["data"]
        if trace.get("marker", {}).get("symbol") == "star"
    ]
    assert len(stars) == 4
    labels = {a["text"] for a in response.figure["layout"].get("annotations", [])}
    assert "Q01 / s3" in labels


def test_resonator_reanalysis_omits_power_outputs_when_qid_is_unassigned(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    service = _resonator_service(monkeypatch, tmp_path, resonance_count=2)

    response = service.reanalyze_resonator_spectroscopy(
        project_id="p",
        chip_id="chip",
        qid="1",
        params=ReanalyzeResonatorSpectroscopyParams(bare_shift_estimator_type="config"),
    )

    assert _outputs(response) == {"readout_frequency": (0.0, "GHz")}


def test_resonator_reanalysis_keeps_frequency_when_power_analysis_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    service = _resonator_service(monkeypatch, tmp_path)

    def broken(*_a: Any, **_k: Any) -> float:
        raise ValueError("no correlated rows")

    monkeypatch.setattr(module, "estimate_minimum_usable_power", broken)

    response = service.reanalyze_resonator_spectroscopy(
        project_id="p",
        chip_id="chip",
        qid="1",
        params=ReanalyzeResonatorSpectroscopyParams(bare_shift_estimator_type="config"),
    )

    assert _outputs(response) == {"readout_frequency": (6.3, "GHz")}


# ── PNG preview ─────────────────────────────────────────────────────────────


def test_include_image_defaults_to_false() -> None:
    assert ReanalyzeRequest().include_image is False


def test_include_image_returns_base64_png(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    service, _ = _qubit_service(monkeypatch, tmp_path, repr_db=-30.0)
    monkeypatch.setattr(ReanalysisService, "_render_png", staticmethod(lambda _fig: PNG_BYTES))

    response = service.reanalyze_qubit_spectroscopy(
        project_id="p",
        chip_id="chip",
        qid="1",
        params=ReanalyzeQubitSpectroscopyParams(),
        include_image=True,
    )

    assert response.image_media_type == "image/png"
    assert response.image_base64 is not None
    assert base64.b64decode(response.image_base64) == PNG_BYTES
    assert response.image_error is None


def test_include_image_reports_renderer_failure_without_failing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    service = _resonator_service(monkeypatch, tmp_path)
    internal_path = "/private/service/chrome/bin/chrome"

    def no_renderer(_fig: go.Figure) -> bytes:
        raise RuntimeError(f"Kaleido subprocess {internal_path} exited with code 1")

    monkeypatch.setattr(ReanalysisService, "_render_png", staticmethod(no_renderer))

    response = service.reanalyze_resonator_spectroscopy(
        project_id="p",
        chip_id="chip",
        qid="1",
        params=ReanalyzeResonatorSpectroscopyParams(bare_shift_estimator_type="config"),
        include_image=True,
    )

    assert response.image_base64 is None
    assert response.image_media_type is None
    assert response.image_error == "Preview image rendering failed."
    assert internal_path not in response.model_dump_json()
    assert "RuntimeError" not in response.model_dump_json()
    # The cause is kept for operators in the server log.
    assert any(
        record.exc_info and internal_path in str(record.exc_info[1]) for record in caplog.records
    )
    assert _outputs(response)["readout_frequency"] == (6.3, "GHz")


def test_render_png_produces_png_with_kaleido() -> None:
    pytest.importorskip("kaleido")

    png = ReanalysisService._render_png(_heatmap(1.0))

    assert png.startswith(b"\x89PNG\r\n\x1a\n")


# ── Inline figure ───────────────────────────────────────────────────────────


def _figure_json(fig: go.Figure) -> dict[str, Any]:
    result: dict[str, Any] = json.loads(fig.to_json())
    return result


def _no_stored_lookup(**_: Any) -> Any:
    raise AssertionError("an inline figure must not read stored task results")


def test_qubit_reanalysis_of_inline_figure_skips_stored_results(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    service, seen = _qubit_service(monkeypatch, tmp_path, repr_db=-30.0)
    monkeypatch.setattr(service, "_load_source_doc", _no_stored_lookup)
    monkeypatch.setattr(ReanalysisService, "_render_png", staticmethod(lambda _fig: PNG_BYTES))

    response = service.reanalyze_qubit_spectroscopy(
        project_id="p",
        chip_id="chip",
        qid="1",
        params=ReanalyzeQubitSpectroscopyParams(),
        figure=_figure_json(_heatmap(1.0)),
        include_image=True,
    )

    assert _is_raw(seen["input"])
    assert response.source_task_id is None
    assert response.source_task_name == "CheckQubitSpectroscopy"
    assert _outputs(response)["coarse_qubit_frequency"] == (7.123, "GHz")
    assert response.image_media_type == "image/png"


def test_resonator_reanalysis_of_inline_figure_uses_analysis_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    service = _resonator_service(monkeypatch, tmp_path)
    monkeypatch.setattr(service, "_load_source_doc", _no_stored_lookup)
    configs: list[Any] = []
    original = module.ReanalysisService._build_resonator_config

    def record_config(params: Any, stored: dict[str, Any]) -> Any:
        configs.append(stored)
        return original(params, stored)

    monkeypatch.setattr(ReanalysisService, "_build_resonator_config", staticmethod(record_config))

    response = service.reanalyze_resonator_spectroscopy(
        project_id="p",
        chip_id="chip",
        qid="1",
        params=ReanalyzeResonatorSpectroscopyParams(bare_shift_estimator_type="config"),
        figure=_figure_json(_raw_figure()),
    )

    assert configs == [{}]
    assert response.source_task_id is None
    assert response.source_task_name == "CheckResonatorSpectroscopy"
    outputs = _outputs(response)
    assert outputs["readout_frequency"] == (6.3, "GHz")
    assert outputs["optimal_power"] == (-35.0, "dB")


def test_request_rejects_source_task_id_with_figure() -> None:
    with pytest.raises(ValidationError, match="either source_task_id or figure"):
        ReanalyzeQubitSpectroscopyRequest(
            source_task_id="task-1", figure=_figure_json(_heatmap(1.0))
        )


def test_request_accepts_figure_with_null_source_task_id() -> None:
    request = ReanalyzeQubitSpectroscopyRequest(
        source_task_id=None, figure=_figure_json(_heatmap(1.0))
    )

    assert request.figure is not None


def test_service_rejects_source_task_id_with_figure() -> None:
    with pytest.raises(HTTPException) as excinfo:
        ReanalysisService().reanalyze_qubit_spectroscopy(
            project_id="p",
            chip_id="chip",
            qid="1",
            params=ReanalyzeQubitSpectroscopyParams(),
            source_task_id="task-1",
            figure=_figure_json(_heatmap(1.0)),
        )

    assert excinfo.value.status_code == 422


@pytest.mark.parametrize(
    ("figure", "message"),
    [
        ({"layout": {}}, "non-empty 'data'"),
        ({"data": []}, "non-empty 'data'"),
        ({"data": [{"type": "scatter", "x": [1], "y": [2]}]}, "heatmap"),
        ({"data": ["heatmap"]}, "heatmap"),
    ],
)
def test_request_rejects_figure_without_heatmap(figure: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        ReanalyzeResonatorSpectroscopyRequest(figure=figure)


def test_request_rejects_oversized_figure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reanalysis_schema, "MAX_INLINE_FIGURE_BYTES", 1024)
    big = _figure_json(_heatmap(1.0))
    big["layout"]["title"] = {"text": "x" * 2048}

    with pytest.raises(ValidationError, match="at most 1024"):
        ReanalyzeResonatorSpectroscopyRequest(figure=big)


_GRID = {"type": "heatmap", "x": [6.0, 6.1], "y": [-60.0, -55.0], "z": [[1.0, 2.0], [3.0, 4.0]]}


def _trace(**overrides: Any) -> dict[str, Any]:
    return {"data": [{**_GRID, **overrides}], "layout": {}}


@pytest.mark.parametrize(
    ("figure", "message"),
    [
        (_trace(type="surface"), "type 'heatmap'"),
        (_trace(type=None), "type 'heatmap'"),
        ({"data": [{k: v for k, v in _GRID.items() if k != "type"}]}, "type 'heatmap'"),
        (_trace(z=["ab", "cd"]), "one value per x"),
        (_trace(z=[["a", "b"], ["c", "d"]]), "finite numbers"),
        (_trace(z=[[1.0, float("nan")], [3.0, 4.0]]), "finite numbers"),
        (_trace(z=[[True, False], [3.0, 4.0]]), "finite numbers"),
        (_trace(z=[[1.0, 2.0]]), "one row per y"),
        (_trace(z=[[1.0], [3.0]]), "one value per x"),
        (_trace(x=["6.0 GHz", "6.1 GHz"]), "finite numbers"),
        (_trace(y="ab"), "list of numbers"),
        (_trace(x=None), "list of numbers"),
        (_trace(x=[6.0], y=[-60.0], z=[[1.0]]), "at least 2 values"),
        (_trace(x=[6.0, float("inf")]), "finite numbers"),
        (_trace(z={"dtype": "f8", "bdata": "AAAA"}), "typed array"),
        ({"data": ["heatmap"]}, "non-empty list of traces"),
    ],
)
def test_service_rejects_malformed_inline_figure(figure: dict[str, Any], message: str) -> None:
    with pytest.raises(HTTPException) as excinfo:
        ReanalysisService._parse_inline_figure(figure)

    assert excinfo.value.status_code == 422
    assert message in str(excinfo.value.detail)


def test_inline_figure_keeps_only_the_heatmap_and_plain_labels() -> None:
    probe = "http://127.0.0.1:9/internal-probe"
    figure = {
        "data": [
            {
                **_GRID,
                "colorscale": "Viridis",
                "colorbar": {"title": {"text": "<b>signal</b>"}},
                "customdata": [[probe]],
                "hovertemplate": f"<a href='{probe}'>x</a>",
            },
            {"type": "scatter", "x": [6.0], "y": [-60.0]},
        ],
        "layout": {
            "title": {"text": f"<img src='{probe}'>Resonator"},
            "xaxis": {"title": {"text": "Frequency (GHz)"}, "range": [0, 1]},
            "yaxis": {"title": "Power (dB)"},
            "width": 800,
            "height": 10**9,
            "images": [{"source": probe, "xref": "paper", "yref": "paper", "x": 0, "y": 1}],
            "template": {"layout": {"images": [{"source": probe}]}},
            "shapes": [{"type": "line", "x0": 0, "x1": 1, "y0": 0, "y1": 1}],
            "annotations": [{"text": probe}],
            "meta": {"note": probe},
        },
    }

    fig = ReanalysisService._parse_inline_figure(figure)

    assert len(fig.data) == 1
    trace = fig.data[0]
    assert trace.type == "heatmap"
    assert list(trace.x) == [6.0, 6.1]
    assert [list(row) for row in trace.z] == [[1.0, 2.0], [3.0, 4.0]]
    assert trace.colorscale is not None
    assert trace.colorbar.title.text == "signal"
    assert trace.customdata is None
    assert trace.hovertemplate is None
    assert fig.layout.images == ()
    assert fig.layout.shapes == ()
    assert fig.layout.annotations == ()
    assert fig.layout.meta is None
    assert fig.layout.title.text == "Resonator"
    assert fig.layout.xaxis.title.text == "Frequency (GHz)"
    assert fig.layout.yaxis.title.text == "Power (dB)"
    assert fig.layout.width == 800
    assert fig.layout.height is None
    assert probe not in fig.to_json()


def test_inline_figure_render_fetches_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("kaleido")
    hits: list[str] = []

    class Probe(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            hits.append(self.path)
            self.send_response(404)
            self.end_headers()

        def log_message(self, *_args: Any) -> None:
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Probe)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        probe = f"http://127.0.0.1:{server.server_address[1]}/internal-probe"
        service, _ = _qubit_service(monkeypatch, tmp_path, repr_db=-30.0)
        monkeypatch.setattr(service, "_load_source_doc", _no_stored_lookup)
        figure = {
            "data": [dict(_GRID)],
            "layout": {
                "images": [{"source": probe, "xref": "paper", "yref": "paper", "x": 0, "y": 1}]
            },
        }

        response = service.reanalyze_qubit_spectroscopy(
            project_id="p",
            chip_id="chip",
            qid="1",
            params=ReanalyzeQubitSpectroscopyParams(),
            figure=figure,
            include_image=True,
        )
    finally:
        server.shutdown()
        server.server_close()

    assert response.image_media_type == "image/png"
    assert hits == []
    assert probe not in json.dumps(response.figure)


def test_inline_figure_analysis_failure_is_a_sanitized_422(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ReanalysisService()
    monkeypatch.setattr(service, "_load_source_doc", _no_stored_lookup)

    def degenerate(*_args: Any, **_kwargs: Any) -> Any:
        raise ValueError("xs/ys too short at /srv/internal/estimate.py")

    monkeypatch.setattr(module, "estimate_and_mark_qubit_figure", degenerate)

    with pytest.raises(HTTPException) as excinfo:
        service.reanalyze_qubit_spectroscopy(
            project_id="p",
            chip_id="chip",
            qid="1",
            params=ReanalyzeQubitSpectroscopyParams(),
            figure=_trace(),
        )

    assert excinfo.value.status_code == 422
    assert "/srv/internal" not in str(excinfo.value.detail)
    assert "too short" not in str(excinfo.value.detail)


def test_stored_result_analysis_failure_still_propagates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    service, _ = _qubit_service(monkeypatch, tmp_path, repr_db=-30.0)

    def degenerate(*_args: Any, **_kwargs: Any) -> Any:
        raise ValueError("degenerate")

    monkeypatch.setattr(module, "estimate_and_mark_qubit_figure", degenerate)

    with pytest.raises(ValueError, match="degenerate"):
        service.reanalyze_qubit_spectroscopy(
            project_id="p",
            chip_id="chip",
            qid="1",
            params=ReanalyzeQubitSpectroscopyParams(),
        )


def test_service_rejects_inline_marked_figure() -> None:
    with pytest.raises(HTTPException) as excinfo:
        ReanalysisService._parse_inline_figure(_figure_json(_marked_figure()))

    assert excinfo.value.status_code == 422
    assert "marked" in str(excinfo.value.detail)
