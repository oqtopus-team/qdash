"""Series metrics: time bins, result checks, target selection and the real worker."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Any

import pytest

from qdash.api.metric_runtime import broker, executor, sdk, worker
from qdash.api.metric_runtime.executor import RuntimeSettings, ScriptFailure
from qdash.api.metric_runtime.sdk import SeriesPoint, time_bins
from qdash.api.metric_runtime.template_library import TEMPLATES
from qdash.datamodel import metric_script as models
from tests.qdash.api.metric_runtime.fakes import FakeBroker, grid_topology

FAST = RuntimeSettings(mode="local", timeout_seconds=30)
# Thursday 2026-11-12 06:00 UTC .. Friday 2026-11-20 18:00 UTC.
START = datetime(2026, 11, 12, 6, tzinfo=UTC)
END = datetime(2026, 11, 20, 18, tzinfo=UTC)
TREND = TEMPLATES["zx90_daily_trend"].source


def line_topology() -> dict[str, Any]:
    return grid_topology([0, 1, 2, 3], [[0, 1], [1, 2], [2, 3]])


def context(broker: FakeBroker | None = None) -> sdk.AnalysisContext:
    fake = broker or FakeBroker(topology=line_topology())
    return sdk.AnalysisContext(fake, "chip-1", START, END)


def run(source: str, metric_id: str, broker: FakeBroker, **kwargs: Any) -> executor.WorkerOutcome:
    return executor.evaluate(
        source=source,
        metric_id=metric_id,
        chip_id="chip-1",
        start=kwargs.pop("start", START).isoformat(),
        end=kwargs.pop("end", END).isoformat(),
        params=kwargs.pop("params", {}),
        broker=broker,
        settings=FAST,
        targets=kwargs.pop("targets", None),
    )


def record(value: float, at: datetime, unit: str = "a.u.", **extra: Any) -> dict[str, Any]:
    return {
        "value": value,
        "unit": unit,
        "timestamp": at.isoformat(),
        "task_id": f"t-{at.isoformat()}",
        "execution_id": "exec-1",
        "excluded": False,
        **extra,
    }


# --- time bins -----------------------------------------------------------------


def test_daily_bins_start_at_utc_midnight_and_clip_the_period():
    bins = time_bins(START, END, "day")
    assert len(bins) == 9
    assert bins[0].start == START and bins[0].nominal_start == datetime(2026, 11, 12, tzinfo=UTC)
    assert bins[0].partial and not bins[0].last
    assert bins[1].start == datetime(2026, 11, 13, tzinfo=UTC) and not bins[1].partial
    assert bins[-1].start == datetime(2026, 11, 20, tzinfo=UTC)
    assert bins[-1].end == END and bins[-1].partial and bins[-1].last
    # Bins tile the period: each end is the next start.
    assert all(a.end == b.start for a, b in pairwise(bins))


def test_weekly_bins_start_on_monday_and_include_the_period_end():
    bins = time_bins(START, END, "week")
    assert [b.nominal_start for b in bins] == [
        datetime(2026, 11, 9, tzinfo=UTC),
        datetime(2026, 11, 16, tzinfo=UTC),
    ]
    assert bins[0].start == START and bins[0].end == datetime(2026, 11, 16, tzinfo=UTC)
    assert bins[1].contains(END) and not bins[0].contains(datetime(2026, 11, 16, tzinfo=UTC))
    assert bins[0].contains("2026-11-15T23:59:59+00:00")
    # A non-UTC offset is converted, not reinterpreted: 08:30 in Tokyo is 23:30 UTC.
    assert bins[0].contains("2026-11-16T08:30:00+09:00")
    assert bins[1].contains("2026-11-16T09:00:00+09:00")


def test_time_bins_refuse_bad_input():
    with pytest.raises(ValueError, match="every"):
        time_bins(START, END, "hour")
    with pytest.raises(ValueError, match="timezone"):
        time_bins(datetime(2026, 11, 1), END)
    with pytest.raises(ValueError, match="before"):
        time_bins(END, START)
    with pytest.raises(ValueError, match="MAX_SERIES_POINTS"):
        time_bins(END - timedelta(days=1100), END)


def test_series_declaration_and_metadata():
    @sdk.metric(title="Trend", unit="%", target="pair", hops=(1,), result="series")
    def trend(pair, ctx):
        return None

    assert trend.__qdash_metric__.metadata()["result"] == "series"  # type: ignore[attr-defined]
    with pytest.raises(ValueError, match="result"):
        sdk.metric(title="x", unit="%", result="chart")
    with pytest.raises(ValueError, match="legend"):
        sdk.metric(
            title="x",
            unit="%",
            result="series",
            legend=sdk.Legend.categorical([("#000", "x")]),
        )
    assert {"SeriesPoint", "SeriesResult", "TimeBin", "time_bins"} <= set(sdk.PUBLIC_NAMES)


def test_api_caps_match_the_worker_sdk():
    assert models.MAX_SERIES_TARGETS == sdk.MAX_SERIES_TARGETS
    assert models.MAX_SERIES_POINTS == sdk.MAX_SERIES_POINTS
    assert models.MAX_TOTAL_SERIES_POINTS == sdk.MAX_TOTAL_SERIES_POINTS
    assert models.MAX_PERIOD_DAYS == sdk.MAX_SERIES_PERIOD_DAYS == broker.MAX_HISTORY_DAYS
    assert sdk.MAX_SERIES_RESULT_BYTES < executor.OUTPUT_LIMIT_BYTES
    # 16 targets of 400 daily bins fit the aggregate budget.
    assert sdk.MAX_SERIES_TARGETS * 401 <= sdk.MAX_TOTAL_SERIES_POINTS


# --- result checks ---------------------------------------------------------------


def test_serialize_series_converts_units_and_infers_status():
    ctx = context()
    points = worker.serialize_series(
        [
            SeriesPoint(START, sdk.Quantity(0.99, "dimensionless"), count=3),
            SeriesPoint("2026-11-13T00:00:00+00:00", None, count=0, reason="no observations"),
            SeriesPoint(START + timedelta(days=2), None, count=1),
        ],
        "%",
        ctx,
    )
    assert points[0]["value"] == pytest.approx(99.0)
    assert points[0]["status"] == "ok"
    assert points[1]["status"] == "no_data" and points[1]["reason"] == "no observations"
    assert points[2]["status"] == "insufficient"
    assert points[1]["timestamp"] == "2026-11-13T00:00:00+00:00"


@pytest.mark.parametrize(
    ("points", "message"),
    [
        ([SeriesPoint(START, float("nan"))], "not finite"),
        ([SeriesPoint(START, True)], "bool"),
        ([SeriesPoint(datetime(2026, 11, 13), 1.0)], "timezone"),
        ([SeriesPoint(START - timedelta(seconds=1), 1.0)], "outside the period"),
        ([SeriesPoint(END + timedelta(seconds=1), 1.0)], "outside the period"),
        ([SeriesPoint(END, 1.0), SeriesPoint(START, 1.0)], "later than"),
        ([SeriesPoint(START, 1.0), SeriesPoint(START, 2.0)], "later than"),
        ([SeriesPoint(START, None, status="ok")], "status 'ok'"),
        ([SeriesPoint(START, 1.0, status="no_data")], "gap must have none"),
        ([SeriesPoint(START, 1.0, count=0)], "count 0"),
        ([SeriesPoint(START, 1.0, count=-1)], "negative"),
        ([SeriesPoint(START, 1.0, status="interpolated")], "status must be"),
        ([SeriesPoint(START, 1.0, start=START)], "both start and end"),
        ([SeriesPoint(START + timedelta(hours=1), 1.0, start=START, end=START)], "start <="),
        ([1.0], "must be a SeriesPoint"),
        ((SeriesPoint(START, sdk.Quantity(1, "GHz")),), "dimension"),
    ],
)
def test_serialize_series_refuses_points_instead_of_fixing_them(points, message):
    with pytest.raises(Exception, match=message):
        worker.serialize_series(points, "%", context())


def test_serialize_series_caps_points():
    step = (END - START) / (sdk.MAX_SERIES_POINTS + 1)
    points = [SeriesPoint(START + step * i, 1.0) for i in range(sdk.MAX_SERIES_POINTS + 1)]
    with pytest.raises(ValueError, match="MAX_SERIES_POINTS = 1024"):
        worker.serialize_series(points, "%", context())
    assert len(worker.serialize_series(points[:-1], "%", context())) == sdk.MAX_SERIES_POINTS


# --- target selection ------------------------------------------------------------


def _definition(target: str = "pair", hops: tuple[int, ...] = (1,)) -> sdk.Metric:
    return sdk.Metric("m", "M", "%", lambda *_: None, target, hops, result="series")  # type: ignore[arg-type]


def test_select_targets_validates_topology_hops_and_direction():
    topology = sdk.Topology(line_topology())
    selected = worker.select_targets(_definition(), topology, ["1>0", "Q01-Q02"])
    pairs = [p for p in selected if isinstance(p, sdk.QubitPair)]
    assert [(p.source, p.target, p.hops) for p in pairs] == [("1", "0", 1), ("1", "2", 1)]
    for targets, message in (
        (None, "needs targets"),
        ([], "needs targets"),
        ([str(i) for i in range(17)], "MAX_SERIES_TARGETS = 16"),
        (["0>2"], "2 hops apart"),
        (["0>3"], "not within 2 hops"),
        (["0>1", "0-1"], "twice"),
        (["0"], "not a directed pair"),
    ):
        with pytest.raises(ValueError, match=message):
            worker.select_targets(_definition(), topology, targets)
    qubits = worker.select_targets(_definition("qubit"), topology, ["Q03", "0"])
    assert qubits == ["3", "0"]
    with pytest.raises(ValueError, match="not on this chip"):
        worker.select_targets(_definition("qubit"), topology, ["9"])
    with pytest.raises(ValueError, match="not a qubit ID"):
        worker.select_targets(_definition("qubit"), topology, ["0>1"])


# --- the real worker -------------------------------------------------------------


def trend_history() -> dict[tuple[str, str], list[dict[str, Any]]]:
    return {
        ("zx90_gate_fidelity", "0-1"): [
            record(0.90, datetime(2026, 11, 12, 7, tzinfo=UTC)),
            record(0.98, datetime(2026, 11, 12, 9, tzinfo=UTC)),
            record(0.94, datetime(2026, 11, 12, 11, tzinfo=UTC)),
            # Excluded results are skipped by history(), not counted as out of range.
            record(0.10, datetime(2026, 11, 13, 9, tzinfo=UTC), excluded=True),
            record(0.97, datetime(2026, 11, 16, 0, tzinfo=UTC)),
            # Stored with unit "%": history() reads it as catalog value x scale, 9900 %, which
            # the 0-100 % range leaves out and counts instead of clipping.
            record(99.0, datetime(2026, 11, 16, 1, tzinfo=UTC), unit="%"),
            record(0.96, END),
        ],
        ("zx90_gate_fidelity", "1-0"): [record(0.80, datetime(2026, 11, 14, tzinfo=UTC))],
    }


def test_daily_trend_evaluates_only_the_selected_pairs():
    broker = FakeBroker(topology=line_topology(), history=trend_history())
    outcome = run(TREND, "zx90_daily_trend", broker, targets=["0>1", "2>1"])
    result = outcome.result
    assert result["metric"]["result"] == "series"
    assert result["legend"] is None
    assert [c["key"] for c in result["cells"]] == ["0>1", "2>1"]
    assert {r["target"] for r in broker.ops("history")} == {"0-1", "2-1"}

    forward = result["cells"][0]
    assert forward["status"] == "ok"
    assert forward["value"] is None
    assert forward["label"] == "daily median"
    series = forward["series"]
    assert len(series) == 9
    first = series[0]
    assert first["timestamp"] == START.isoformat() and first["start"] == START.isoformat()
    assert first["end"] == "2026-11-13T00:00:00+00:00"
    assert first["value"] == pytest.approx(94.0) and first["count"] == 3
    assert first["reason"] == "partial bin"
    # Nov 13 holds only an excluded result: a gap with its reason, never interpolated.
    assert series[1] == {
        "timestamp": "2026-11-13T00:00:00+00:00",
        "start": "2026-11-13T00:00:00+00:00",
        "end": "2026-11-14T00:00:00+00:00",
        "value": None,
        "count": 0,
        "status": "no_data",
        "reason": "no observations",
    }
    monday = series[4]
    assert monday["value"] == pytest.approx(97.0) and monday["count"] == 1
    assert monday["reason"] == "1 outside 0-100 % left out"
    last = series[-1]
    assert last["value"] == pytest.approx(96.0) and last["end"] == END.isoformat()
    checks = {c["label"]: c["value"] for c in forward["assessment"]["checks"]}
    assert checks == {"observations": 6, "outside valid range": 1}

    empty = result["cells"][1]
    assert empty["status"] == "missing"
    assert empty["message"] == "No point has a value: 9 no_data"


def test_weekly_trend_and_minimum_samples():
    broker = FakeBroker(topology=line_topology(), history=trend_history())
    outcome = run(
        TREND,
        "zx90_daily_trend",
        broker,
        targets=["0>1"],
        params={"interval": "week", "min_samples": 2},
    )
    series = outcome.result["cells"][0]["series"]
    assert [p["start"] for p in series] == [START.isoformat(), "2026-11-16T00:00:00+00:00"]
    assert series[0]["value"] == pytest.approx(94.0) and series[0]["count"] == 3
    assert series[1]["value"] == pytest.approx(96.5) and series[1]["count"] == 2
    assert series[1]["reason"] == "1 outside 0-100 % left out; partial bin"

    strict = run(
        TREND,
        "zx90_daily_trend",
        broker,
        targets=["0>1"],
        params={"interval": "week", "min_samples": 3},
    )
    gap = strict.result["cells"][0]["series"][1]
    assert gap["status"] == "insufficient" and gap["value"] is None and gap["count"] == 2
    assert gap["reason"].startswith("2 < min_samples 3")


def test_daily_trend_bin_with_only_out_of_range_observations_is_insufficient():
    """Observations that are all left out make an insufficient gap, not "no observations"."""
    day = datetime(2026, 11, 13, tzinfo=UTC)
    history = {
        ("zx90_gate_fidelity", "0-1"): [
            record(99.0, day + timedelta(hours=1), unit="%"),
            record(98.0, day + timedelta(hours=2), unit="%"),
        ]
    }
    fake = FakeBroker(topology=line_topology(), history=history)
    cell = run(TREND, "zx90_daily_trend", fake, targets=["0>1"]).result["cells"][0]
    series = cell["series"]
    assert series[1] == {
        "timestamp": "2026-11-13T00:00:00+00:00",
        "start": "2026-11-13T00:00:00+00:00",
        "end": "2026-11-14T00:00:00+00:00",
        "value": None,
        "count": 0,
        "status": "insufficient",
        "reason": "0 of 2 observations valid; 2 outside 0-100 % left out",
    }
    # Bins without any observation stay no_data.
    assert series[2]["status"] == "no_data" and series[2]["reason"] == "no observations"
    assert cell["status"] == "missing"
    assert cell["message"] == "No point has a value: 8 no_data, 1 insufficient"
    checks = {c["label"]: c["value"] for c in cell["assessment"]["checks"]}
    assert checks == {"observations": 2, "outside valid range": 2}


def test_series_periods_over_the_history_cap_fail_before_any_read():
    days = sdk.MAX_SERIES_PERIOD_DAYS
    fake = FakeBroker(topology=line_topology(), history=trend_history())
    with pytest.raises(ScriptFailure, match=f"MAX_SERIES_PERIOD_DAYS = {days} days"):
        run(
            TREND,
            "zx90_daily_trend",
            fake,
            targets=["0>1"],
            start=END - timedelta(days=days, seconds=1),
        )
    assert fake.ops("history") == [] and fake.ops("topology") == []
    # Exactly the cap is evaluated, and scalar metrics keep longer periods.
    longest = run(
        TREND, "zx90_daily_trend", fake, targets=["0>1"], start=END - timedelta(days=days)
    )
    assert longest.result["cells"][0]["status"] == "ok"
    scalar = run(
        TEMPLATES["zx90_median"].source, "zx90_median", fake, start=END - timedelta(days=days + 30)
    )
    assert scalar.result["metric"]["result"] == "scalar"


def test_series_requests_need_targets_and_scalar_requests_refuse_them():
    broker = FakeBroker(topology=line_topology(), history=trend_history())
    with pytest.raises(ScriptFailure, match="needs targets"):
        run(TREND, "zx90_daily_trend", broker)
    with pytest.raises(ScriptFailure, match="2 hops apart"):
        run(TREND, "zx90_daily_trend", broker, targets=["0>2"])
    assert broker.ops("history") == []
    with pytest.raises(ScriptFailure, match="only to series"):
        run(TEMPLATES["zx90_median"].source, "zx90_median", broker, targets=["0>1"])


WRONG_RETURNS = """\
from qdash_metrics import CellResult, SeriesPoint, SeriesResult, metric


@metric(title="Series", unit="%", result="series")
def series(target, ctx):
    if target == "0":
        return 1.0
    if target == "1":
        return SeriesResult([SeriesPoint(ctx.end, 1.0), SeriesPoint(ctx.start, 2.0)])
    return None


@metric(title="Scalar", unit="%")
def scalar(target, ctx):
    return SeriesResult([SeriesPoint(ctx.start, 1.0)])
"""


def test_wrong_return_kinds_are_cell_errors():
    broker = FakeBroker(topology=line_topology())
    cells = run(WRONG_RETURNS, "series", broker, targets=["0", "1", "2"]).result["cells"]
    assert cells[0]["status"] == "error" and "SeriesResult" in cells[0]["message"]
    assert cells[1]["status"] == "error" and "later than" in cells[1]["message"]
    assert cells[2]["status"] == "empty"
    scalar = run(WRONG_RETURNS, "scalar", broker).result["cells"]
    assert all(c["status"] == "error" and "result='series'" in c["message"] for c in scalar)


DENSE = """\
from qdash_metrics import Parameter, SeriesPoint, SeriesResult, metric


@metric(
    title="Dense",
    unit="%",
    result="series",
    parameters={"points": Parameter(default=512, min=1, max=1024, step=1)},
)
def dense(target, ctx):
    for index in range(200):
        ctx.references.append(
            {"metric": "zx90_gate_fidelity", "target": "1000-1001", "task_id": "t" * 40,
             "execution_id": "e" * 40, "timestamp": ctx.end.isoformat(), "value": float(index),
             "unit": "percent"}
        )
    count = ctx.params["points"]
    step = (ctx.end - ctx.start) / count
    return SeriesResult(
        [
            SeriesPoint(ctx.start + step * i, 99.123456789, count=1000, reason="x" * 1000,
                        start=ctx.start + step * i, end=ctx.start + step * (i + 1))
            for i in range(count)
        ],
        label="y" * 1000,
    )
"""


def test_largest_allowed_series_response_fits_the_output_bound():
    """16 targets with 8192 points in all, every text at its cap, stay about half of 8 MiB."""
    qubits = list(range(16))
    broker = FakeBroker(topology=grid_topology(qubits, [], columns=4))
    targets = [str(q) for q in qubits]
    outcome = run(DENSE, "dense", broker, targets=targets)
    cells = outcome.result["cells"]
    assert sum(len(c["series"]) for c in cells) == sdk.MAX_TOTAL_SERIES_POINTS
    assert all(len(c["series"][0]["reason"]) == worker.MAX_REASON for c in cells)
    assert all(len(c["references"]) == worker.MAX_SERIES_REFERENCES for c in cells)
    assert all(c["references_truncated"] for c in cells)
    size = len(json.dumps(outcome.result))
    assert size < executor.OUTPUT_LIMIT_BYTES * 0.6, size

    with pytest.raises(ScriptFailure, match="MAX_TOTAL_SERIES_POINTS = 8192"):
        run(DENSE, "dense", broker, targets=targets, params={"points": 513})


TEXT_HEAVY = """\
from qdash_metrics import Parameter, SeriesPoint, SeriesResult, metric


@metric(
    title="Text heavy",
    unit="%",
    result="series",
    parameters={
        "text": Parameter(default="x", choices=["x", "cjk", "emoji"]),
        "points": Parameter(default=512, min=1, max=1024, step=1),
    },
)
def heavy(target, ctx):
    char = {"x": "x", "cjk": "\u89b3", "emoji": "\U0001f600"}[ctx.params["text"]]
    count = ctx.params["points"]
    step = (ctx.end - ctx.start) / count
    return SeriesResult(
        [
            SeriesPoint(ctx.start + step * i, None, count=0, status="no_data", reason=char * 1000)
            for i in range(count)
        ],
        label=char * 1000,
    )
"""


@pytest.mark.parametrize(("text", "point_bytes"), [("cjk", 6), ("emoji", 12)])
def test_non_ascii_series_text_is_held_to_the_result_byte_budget(text, point_bytes):
    """Escaped CJK or emoji reasons at their cap fail with a clear error instead of 8 MiB."""
    qubits = list(range(16))
    fake = FakeBroker(topology=grid_topology(qubits, [], columns=4))
    targets = [str(q) for q in qubits]
    point = worker.encoded_size(
        worker.serialize_series(
            [
                SeriesPoint(
                    START,
                    None,
                    count=0,
                    reason={"cjk": "\u89b3", "emoji": "\U0001f600"}[text] * 200,
                )
            ],
            "%",
            context(),
        )[0]
    )
    # Every escaped character costs 6 bytes (12 for an emoji's surrogate pair).
    assert point > worker.MAX_REASON * point_bytes
    assert point * sdk.MAX_TOTAL_SERIES_POINTS > executor.OUTPUT_LIMIT_BYTES
    with pytest.raises(ScriptFailure, match="MAX_SERIES_RESULT_BYTES = 6 MiB") as failure:
        run(TEXT_HEAVY, "heavy", fake, targets=targets, params={"text": text})
    assert "non-ASCII" in str(failure.value)
    # The same shape in ASCII fits, with every point kept and nothing cut silently.
    ascii_run = run(TEXT_HEAVY, "heavy", fake, targets=targets, params={"text": "x"})
    cells = ascii_run.result["cells"]
    assert sum(len(c["series"]) for c in cells) == sdk.MAX_TOTAL_SERIES_POINTS
    assert worker.encoded_size(cells) <= sdk.MAX_SERIES_RESULT_BYTES


def test_series_result_budget_counts_every_field():
    """A cell is measured whole: an oversized assessment is refused like oversized points."""
    cell = {"key": "0", "series": [], "assessment": {"estimates": ["\u89b3" * 4000] * 200}}
    assert worker.encoded_size(cell) > 4000 * 200 * 6
    message = worker.series_size_message(7 * 1024 * 1024, "0")
    assert "by target 0" in message and "assessment" in message
