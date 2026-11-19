"""Worker and executor tests that spawn the real worker subprocess."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from qdash.api.metric_runtime import executor
from qdash.api.metric_runtime.executor import (
    QueueFullError,
    RuntimeSettings,
    ScriptFailure,
    WorkerFailure,
)
from qdash.api.metric_runtime.template_library import TEMPLATES
from tests.qdash.api.metric_runtime.fakes import FakeBroker, grid_topology

END = datetime(2026, 11, 20, tzinfo=UTC)
START = END - timedelta(days=14)
FAST = RuntimeSettings(timeout_seconds=30)


def run(source: str, metric_id: str, broker: FakeBroker, **kwargs: Any) -> executor.WorkerOutcome:
    settings = kwargs.pop("settings", FAST)
    return executor.evaluate(
        source=source,
        metric_id=metric_id,
        chip_id="chip-1",
        start=START.isoformat(),
        end=END.isoformat(),
        params=kwargs.pop("params", {}),
        broker=broker,
        settings=settings,
    )


def cells(outcome: executor.WorkerOutcome) -> dict[str, dict[str, Any]]:
    return {cell["key"]: cell for cell in outcome.result["cells"]}


def line_topology() -> dict[str, Any]:
    return grid_topology([0, 1, 2, 3], [[0, 1], [1, 2], [2, 3]])


def test_catalog_for_every_template():
    expected = {
        "getting_started": ["coherence_ratio", "upper_frequency_gap", "mean_dispersive_shift"],
        "collision": [
            "Type0A",
            "Type0B",
            "Type1A",
            "Type1B",
            "Type1C",
            "Type2A",
            "Type2B",
            "Type2C",
            "Type3A",
            "Type3B",
            "Type7",
            "Type8",
            "Type9",
        ],
        "zx90_median": ["zx90_median"],
    }
    for template_id, metric_ids in expected.items():
        outcome = executor.catalog(TEMPLATES[template_id].source, FAST)
        assert [m["id"] for m in outcome.result["metrics"]] == metric_ids, template_id
    zx90 = executor.catalog(TEMPLATES["zx90_median"].source, FAST).result["metrics"][0]
    assert zx90["target"] == "pair"
    assert zx90["hops"] == [1]
    assert zx90["unit"] == "%"
    assert zx90["has_legend"] is True
    assert zx90["parameters"]["min_samples"]["kind"] == "integer"
    assert zx90["parameters"]["min_samples"]["default"] == 3
    collision = executor.catalog(TEMPLATES["collision"].source, FAST).result["metrics"]
    assert collision[0]["title"] == "Type0A — Qubit quality"
    assert collision[0]["target"] == "qubit"
    assert all(m["hops"] == [1, 2] for m in collision[1:])


def test_catalog_failures_carry_diagnostics():
    with pytest.raises(ScriptFailure) as syntax:
        executor.catalog("from qdash_metrics import metric\ndef broken(:\n", FAST)
    assert syntax.value.diagnostics[0]["line"] == 2
    with pytest.raises(ScriptFailure) as policy:
        executor.catalog("import os\n", FAST)
    assert "not allowed" in policy.value.message
    assert policy.value.diagnostics[0]["line"] == 1
    with pytest.raises(ScriptFailure, match="No metrics found"):
        executor.catalog("x = 1\n", FAST)


def zx90_history() -> dict[tuple[str, str], list[dict[str, Any]]]:
    def record(value: float, hours: int, **extra: Any) -> dict[str, Any]:
        return {
            "value": value,
            "unit": "a.u.",
            "timestamp": (END - timedelta(hours=hours)).isoformat(),
            "task_id": f"t{hours}",
            "execution_id": "exec-1",
            "excluded": False,
            **extra,
        }

    return {
        ("zx90_gate_fidelity", "0-1"): [
            record(0.90, 30),
            record(0.99, 20),
            record(0.95, 10),
            record(0.10, 5, excluded=True),
        ],
        ("zx90_gate_fidelity", "1-0"): [record(0.97, 30), record(0.98, 10)],
    }


def test_zx90_median_over_raw_history():
    broker = FakeBroker(topology=line_topology(), history=zx90_history())
    outcome = run(TEMPLATES["zx90_median"].source, "zx90_median", broker)
    result = outcome.result
    assert result["params"] == {"min_samples": 3}
    assert result["legend"]["kind"] == "continuous"
    assert [stop["value"] for stop in result["legend"]["stops"]] == [90.0, 97.0, 99.0]
    by_key = cells(outcome)
    # hops=(1,) on a line: both directions of the three couplings only.
    assert sorted(by_key) == ["0>1", "1>0", "1>2", "2>1", "2>3", "3>2"]

    forward = by_key["0>1"]
    assert forward["status"] == "ok"
    assert forward["value"] == pytest.approx(95.0)
    assert forward["source"] == "0" and forward["target"] == "1" and forward["hops"] == 1
    assert forward["label"] == "median of 3"
    assert forward["assessment"]["count"] == 3
    checks = {c["label"]: c["value"] for c in forward["assessment"]["checks"]}
    assert checks["samples"] == 3
    assert checks["min (%)"] == pytest.approx(90.0)
    assert checks["max (%)"] == pytest.approx(99.0)
    assert checks["latest"] == (END - timedelta(hours=10)).isoformat()
    assert [ref["task_id"] for ref in forward["references"]] == ["t30", "t20", "t10"]
    assert forward["references"][0]["unit"] == "percent"

    reverse = by_key["1>0"]
    assert reverse["status"] == "missing"
    assert reverse["value"] is None
    assert reverse["color"] == "#737373"
    assert reverse["assessment"]["count"] == 2
    assert reverse["label"] == "fewer than min_samples observations"
    empty = by_key["2>3"]
    assert empty["status"] == "missing" and empty["assessment"]["count"] == 0

    # The directed pair is read: no reverse fallback, and the period is passed through.
    requests = broker.ops("history")
    assert {r["target"] for r in requests} == {"0-1", "1-0", "1-2", "2-1", "2-3", "3-2"}
    assert all(r["start"] == START.isoformat() and r["end"] == END.isoformat() for r in requests)

    relaxed = run(TEMPLATES["zx90_median"].source, "zx90_median", broker, params={"min_samples": 2})
    assert cells(relaxed)["1>0"]["value"] == pytest.approx(97.5)


def test_getting_started_qubit_metric():
    broker = FakeBroker(
        topology=line_topology(),
        latest={"qubit": {"t1": {"0": 50.0, "1": 40.0}, "t2_echo": {"0": 25.0, "1": 80.0}}},
    )
    outcome = run(TEMPLATES["getting_started"].source, "coherence_ratio", broker)
    by_key = cells(outcome)
    assert sorted(by_key, key=int) == ["0", "1", "2", "3"]
    assert by_key["0"]["status"] == "ok"
    assert by_key["0"]["qid"] == "0" and by_key["0"]["source"] is None
    assert by_key["0"]["value"] == pytest.approx(0.5)
    assert by_key["1"]["value"] == pytest.approx(2.0)
    assert [ref["metric"] for ref in by_key["0"]["references"]] == ["t2_echo", "t1"]
    assert by_key["2"]["status"] == "missing"
    assert "No t2_echo for Q2 in this period" in by_key["2"]["message"]
    assert outcome.result["metric"]["unit"] == "dimensionless"


CELL_KINDS = """\
from qdash_metrics import CellResult, MissingData, metric


@metric(title="Kinds", unit="GHz")
def kinds(target, ctx):
    print("evaluating", target)
    if target == "0":
        return 1 / 0
    if target == "1":
        raise MissingData("no data for one")
    if target == "2":
        return None
    if target == "3":
        return CellResult(None, color="#abc", assessment={"label": "skipped", "count": 0})
    return ctx.data["qubit_frequency"][target].latest().to("MHz")
"""


def test_cell_statuses_errors_and_log():
    topology = grid_topology([0, 1, 2, 3, 4], [[0, 1]])
    broker = FakeBroker(topology=topology, latest={"qubit": {"qubit_frequency": {"4": 7.25}}})
    outcome = run(CELL_KINDS, "kinds", broker)
    by_key = cells(outcome)
    error = by_key["0"]
    assert error["status"] == "error"
    assert error["message"] == "ZeroDivisionError: division by zero (line 8, kinds)"
    assert error["diagnostic"] == {
        "message": "ZeroDivisionError: division by zero",
        "line": 8,
        "function": "kinds",
    }
    assert by_key["1"]["status"] == "missing" and by_key["1"]["message"] == "no data for one"
    assert by_key["2"]["status"] == "empty"
    assert by_key["3"]["status"] == "missing"
    assert by_key["3"]["color"] == "#aabbcc"
    assert by_key["3"]["label"] == "skipped"
    assert by_key["4"]["status"] == "ok"
    # Quantities are converted back to the declared unit.
    assert by_key["4"]["value"] == pytest.approx(7.25)
    assert "evaluating 4" in outcome.log
    assert outcome.log_truncated is False


def test_broker_errors_become_cell_errors():
    source = TEMPLATES["zx90_median"].source
    broker = FakeBroker(
        topology=line_topology(),
        errors={"history": "history matched more than MAX_HISTORY_RECORDS = 5000 results"},
    )
    by_key = cells(run(source, "zx90_median", broker))
    assert all(cell["status"] == "error" for cell in by_key.values())
    assert "MAX_HISTORY_RECORDS" in by_key["0>1"]["message"]


def test_missing_topology_fails_the_evaluation():
    broker = FakeBroker(topology=line_topology(), errors={"topology": "Chip has no topology"})
    with pytest.raises(ScriptFailure, match="Chip has no topology"):
        run(TEMPLATES["zx90_median"].source, "zx90_median", broker)
    with pytest.raises(ScriptFailure, match="not defined"):
        run(TEMPLATES["zx90_median"].source, "nope", FakeBroker(topology=line_topology()))
    with pytest.raises(ScriptFailure, match="Parameter min_samples"):
        run(
            TEMPLATES["zx90_median"].source,
            "zx90_median",
            FakeBroker(topology=line_topology()),
            params={"min_samples": 0},
        )


LOOP = """\
from qdash_metrics import metric


@metric(title="Loop", unit="GHz")
def loop(target, ctx):
    while True:
        pass
"""


def test_timeout_kills_the_worker():
    settings = RuntimeSettings(timeout_seconds=1.5)
    started = time.monotonic()
    with pytest.raises(WorkerFailure, match="time limit"):
        run(LOOP, "loop", FakeBroker(topology=line_topology()), settings=settings)
    assert time.monotonic() - started < 10


PRINTER = """\
from qdash_metrics import metric

print("x" * 100000)


@metric(title="Printer", unit="GHz")
def printer(target, ctx):
    return 1.0
"""


def test_output_and_log_bounds():
    outcome = run(PRINTER, "printer", FakeBroker(topology=line_topology()))
    assert outcome.log_truncated is True
    assert len(outcome.log.encode()) <= 16 * 1024 + 64
    assert outcome.log.startswith("[Earlier log output truncated]")
    tiny = RuntimeSettings(timeout_seconds=30, output_limit_bytes=2000)
    with pytest.raises(WorkerFailure, match="output exceeded"):
        run(PRINTER, "printer", FakeBroker(topology=line_topology()), settings=tiny)


def test_worker_environment_is_scrubbed(monkeypatch):
    monkeypatch.setenv("MONGO_INITDB_ROOT_PASSWORD", "secret")
    monkeypatch.setenv("QDASH_API_TOKEN", "token")
    env = executor.scrubbed_env()
    assert set(env) == {
        "PATH",
        "PYTHONPATH",
        "LANG",
        "LC_ALL",
        "OPENBLAS_NUM_THREADS",
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
    }
    assert "secret" not in "".join(env.values())
    assert env["PYTHONPATH"].split(":")[0] == executor.SOURCE_ROOT


def test_queue_full_when_no_slot_frees_up():
    settings = RuntimeSettings(concurrency=97, queue_wait_seconds=0.1)
    slots = executor._semaphore(97)
    taken = [slots.acquire(timeout=1) for _ in range(97)]
    try:
        with pytest.raises(QueueFullError, match="queue is full"):
            executor.catalog("x = 1\n", settings)
    finally:
        for acquired in taken:
            if acquired:
                slots.release()


def test_settings_from_environment(monkeypatch):
    monkeypatch.setenv("METRIC_SCRIPT_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("METRIC_SCRIPT_MEMORY_MB", "512")
    monkeypatch.setenv("METRIC_SCRIPT_CONCURRENCY", "bogus")
    settings = executor.load_settings()
    assert settings.timeout_seconds == 12
    assert settings.memory_mb == 512
    assert settings.concurrency == executor.DEFAULT_CONCURRENCY
