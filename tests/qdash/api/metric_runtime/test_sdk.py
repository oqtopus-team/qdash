"""Unit tests for the qdash_metrics SDK (in process, no worker)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from qdash.api.metric_runtime import sdk
from qdash.api.metric_runtime.sdk import (
    AnalysisContext,
    Legend,
    MissingData,
    Parameter,
    Quantity,
    QubitPair,
    coupling_id,
    qid,
    resolve_parameters,
    unit_name,
)
from tests.qdash.api.metric_runtime.fakes import FakeBroker, grid_topology

END = datetime(2026, 11, 20, tzinfo=UTC)
START = END - timedelta(days=14)


def context(broker: FakeBroker, params: dict[str, Any] | None = None) -> AnalysisContext:
    return AnalysisContext(broker, "chip-1", START, END, params)


def broker() -> FakeBroker:
    return FakeBroker(
        topology=grid_topology([0, 1, 2, 3], [[0, 1], [0, 2], [1, 3], [2, 3]]),
        latest={
            "qubit": {
                "qubit_frequency": {"0": 7.0, "1": 7.5},
                "qubit_anharmonicity": {"0": -0.3},
                "t1": {"0": 50.0},
                "average_readout_fidelity": {"0": 0.97},
            },
            "coupling": {
                "zx90_gate_fidelity": {"0-1": 0.99},
                "qubit_qubit_coupling_strength": {"1-0": 8.0},
            },
        },
    )


def test_units_and_aliases():
    assert unit_name("%") == "percent"
    assert unit_name("μs") == "us"
    assert unit_name("µs") == "us"
    assert unit_name("") == "dimensionless"
    assert unit_name("a.u.") == "au"
    assert unit_name("KHz") == "kHz"
    assert unit_name("MHz/a.u.") == "MHz/au"
    assert Quantity(8300, "MHz").to("GHz").magnitude == pytest.approx(8.3)
    assert Quantity(50, unit_name("μs")).to("ns").magnitude == pytest.approx(50000)
    assert Quantity(1, "kHz").to("MHz").magnitude == pytest.approx(0.001)
    assert Quantity(0.95, "dimensionless").to("percent").magnitude == pytest.approx(95)
    with pytest.raises(Exception, match="Cannot convert"):
        Quantity(1, "GHz").to("furlongs")


def test_qid_and_coupling_normalization():
    assert qid("Q05") == "5"
    assert qid(5) == "5"
    assert qid("005") == "5"
    with pytest.raises(ValueError):
        qid("Qx")
    with pytest.raises(ValueError):
        qid(True)
    assert coupling_id("Q00-Q01") == "0-1"
    assert coupling_id(QubitPair("3", "2", 1)) == "3-2"
    with pytest.raises(ValueError):
        coupling_id("0-1-2")


def test_parameter_validation():
    integer = Parameter(default=3, min=1)
    assert integer.kind == "integer"
    assert integer.validate(4.0) == 4
    with pytest.raises(ValueError):
        integer.validate(0)
    with pytest.raises(ValueError):
        integer.validate(2.5)
    with pytest.raises(ValueError):
        integer.validate(True)
    assert Parameter(default=True).kind == "boolean"
    choice = Parameter(default="a", choices=["a", "b"])
    assert choice.kind == "choice"
    with pytest.raises(ValueError):
        choice.validate("c")
    with pytest.raises(ValueError, match="minimum exceeds maximum"):
        Parameter(default=1.0, min=2, max=1)
    with pytest.raises(ValueError, match="step"):
        Parameter(default=1.0, step=0)
    with pytest.raises(ValueError):
        Parameter(default=float("nan"))
    with pytest.raises(ValueError, match="Choices"):
        Parameter(default="a", choices=[])
    number = Parameter(default=0.5, min=0, max=1, step=0.1, unit="GHz", label="Limit")
    assert Parameter.from_metadata(number.metadata()) == number
    # JSON round trips turn 3.0 into 3; the declared kind survives.
    restored = Parameter.from_metadata({**number.metadata(), "default": 1, "max": 2})
    assert restored.kind == "number"


def test_resolve_parameters():
    declared = {"cnot_time": Parameter(default=500.0, min=1), "n": Parameter(default=3, min=1)}
    assert resolve_parameters(declared, {"cnot_time": 300}) == {"cnot_time": 300.0, "n": 3}
    with pytest.raises(ValueError, match="Unknown parameters: bogus"):
        resolve_parameters(declared, {"bogus": 1})
    with pytest.raises(ValueError, match="Parameter cnot_time"):
        resolve_parameters(declared, {"cnot_time": 0})


def test_legend_validation_and_serialization():
    categorical = Legend.categorical([("#f00", "bad"), ("#2563eb", "good")])
    assert categorical.serialize("%", "%")["items"][0] == {"color": "#ff0000", "label": "bad"}
    continuous = Legend.continuous([(90, "#dc2626"), (99, "#2563eb")])
    assert continuous.serialize("%", "%")["stops"] == [
        {"value": 90.0, "color": "#dc2626"},
        {"value": 99.0, "color": "#2563eb"},
    ]
    assert continuous.serialize("GHz", "MHz")["stops"][0]["value"] == pytest.approx(90000)
    with pytest.raises(ValueError, match="increasing"):
        Legend.continuous([(99, "#dc2626"), (90, "#2563eb")])
    with pytest.raises(ValueError, match="two stops"):
        Legend.continuous([(90, "#dc2626")])
    with pytest.raises(ValueError, match="Colors"):
        Legend.categorical([("red", "bad")])
    with pytest.raises(ValueError):
        Legend.categorical([])


def test_metric_decorator_validates_declarations():
    with pytest.raises(ValueError, match="target"):
        sdk.metric(title="x", unit="GHz", target="edge")
    with pytest.raises(ValueError, match="hops"):
        sdk.metric(title="x", unit="GHz", target="pair", hops=(3,))
    with pytest.raises(ValueError, match="hops"):
        sdk.metric(title="x", unit="GHz", target="pair", hops=())
    with pytest.raises(Exception, match="nope"):
        sdk.metric(title="x", unit="nope")

    @sdk.metric(title="Pair", unit="%", target="pair", hops=[1, 1])
    def pair_metric(pair, ctx):
        return None

    definition = pair_metric.__qdash_metric__  # type: ignore[attr-defined]
    assert definition.metadata() == {
        "id": "pair_metric",
        "title": "Pair",
        "unit": "%",
        "target": "pair",
        "result": "scalar",
        "hops": [1],
        "parameters": {},
        "has_legend": False,
    }


def test_latest_applies_catalog_scale_and_records_references():
    fake = broker()
    ctx = context(fake)
    frequency = ctx.data["qubit_frequency"]["Q00"].latest()
    assert frequency.to("GHz").magnitude == pytest.approx(7.0)
    anharmonicity = ctx.data["qubit_anharmonicity"][0].latest()
    assert str(anharmonicity.units) == "megahertz"
    assert anharmonicity.magnitude == pytest.approx(-300)
    fidelity = ctx.data["average_readout_fidelity"]["0"].latest()
    assert fidelity.to("percent").magnitude == pytest.approx(97)
    assert ctx.references[0] == {
        "metric": "qubit_frequency",
        "target": "0",
        "task_id": "task-0",
        "execution_id": "exec-1",
        "timestamp": None,
        "value": 7.0,
        "unit": "gigahertz",
    }
    # One latest request per metric, then cached.
    ctx.data["qubit_frequency"]["1"].latest()
    assert len([a for a in fake.ops("latest") if a["metric"] == "qubit_frequency"]) == 1


def test_missing_data_and_unknown_metrics():
    ctx = context(broker())
    with pytest.raises(MissingData, match="No t1 for Q1 in this period"):
        ctx.data["t1"]["1"].latest()
    with pytest.raises(KeyError, match="metrics catalog"):
        ctx.data["not_a_metric"]
    assert "t1" in ctx.data
    assert "not_a_metric" not in ctx.data
    with pytest.raises(TypeError, match="qubit metric"):
        ctx.data["t1"][QubitPair("0", "1", 1)]
    with pytest.raises(TypeError, match="coupling metric"):
        ctx.data["zx90_gate_fidelity"][0]


def test_coupling_access_is_directed_but_strength_is_undirected():
    ctx = context(broker())
    pair = QubitPair("0", "1", 1)
    assert ctx.data["zx90_gate_fidelity"][pair].latest().to("percent").magnitude == pytest.approx(
        99
    )
    with pytest.raises(MissingData):
        ctx.data["zx90_gate_fidelity"]["1-0"].latest()
    strength = ctx.coupling_strength("0", "1")
    assert strength.to("GHz").magnitude == pytest.approx(0.008)
    assert ctx.references[-1]["target"] == "1-0"
    assert ctx.coupling_strength("2", "3") is None


def test_history_units_exclusion_and_bounds():
    base = END - timedelta(days=1)
    records: list[dict[str, Any]] = [
        {"value": 0.95, "unit": "a.u.", "timestamp": (base + timedelta(hours=2)).isoformat()},
        {"value": 0.90, "unit": "", "timestamp": base.isoformat(), "task_id": "t1"},
        {"value": 0.10, "unit": None, "timestamp": base.isoformat(), "excluded": True},
        {"value": None, "unit": None, "timestamp": base.isoformat()},
    ]
    fake = FakeBroker(
        topology=grid_topology([0, 1], [[0, 1]]),
        history={
            ("zx90_gate_fidelity", "0-1"): records,
            ("t1", "0"): [{"value": 0.05, "unit": "ms", "timestamp": base.isoformat()}],
        },
    )
    ctx = context(fake)
    history = ctx.data["zx90_gate_fidelity"]["0-1"].history()
    assert [round(p.value.to("percent").magnitude, 6) for p in history] == [90.0, 95.0]
    assert history[0].task_id == "t1"
    assert history[0].timestamp == base
    with_excluded = ctx.data["zx90_gate_fidelity"]["0-1"].history(include_excluded=True)
    assert len(with_excluded) == 3
    # A compatible physical unit on the record wins over the catalog unit.
    assert ctx.data["t1"]["0"].history()[0].value.to("us").magnitude == pytest.approx(50)
    request = fake.ops("history")[0]
    assert request["start"] == START.isoformat() and request["end"] == END.isoformat()
    with pytest.raises(ValueError, match="timezone"):
        ctx.data["t1"]["0"].history(start="2026-01-01T00:00:00")
    with pytest.raises(ValueError, match="before end"):
        ctx.data["t1"]["0"].history(start=END, end=START)


def test_topology_queries():
    topology = sdk.Topology(
        grid_topology([24, 25, 26, 27, 28], [[24, 25], [24, 26], [25, 27], [26, 27], [25, 28]])
    )
    assert topology.qubits == ["24", "25", "26", "27", "28"]
    assert topology.neighbors("25") == ["24", "27", "28"]
    assert [p.target for p in topology.pairs(hops=(2,)) if p.source == "24"] == ["27", "28"]
    assert QubitPair("25", "24", 1) in topology.pairs(hops=(1,))
    assert len(topology.pairs(hops=(1,))) == 10
    assert topology.offset("24", col=1) == "25"
    assert topology.offset("24", row=-1) is None
    with pytest.raises(ValueError, match="duplicate"):
        sdk.Topology({"qubits": {"0": {"row": 0, "col": 0}, "1": {"row": 0, "col": 0}}})
