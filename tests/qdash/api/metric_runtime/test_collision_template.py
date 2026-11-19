# ruff: noqa: RUF001
"""The collision template reproduces the checks of the removed collision service.

Ported from the deleted ``tests/qdash/api/services/test_collision_analysis.py`` (itself a
port of the qdash-playground reference tests); every expected number is kept. Inputs reach
the template through the broker protocol shapes: raw catalog values (GHz frequencies and
anharmonicities, μs coherence times, MHz coupling strengths).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from qdash.api.metric_runtime import executor, sdk, worker
from qdash.api.metric_runtime.executor import RuntimeSettings
from qdash.api.metric_runtime.template_library import TEMPLATES
from tests.qdash.api.metric_runtime.fakes import FakeBroker, grid_topology

COUPLINGS = [[24, 25], [24, 26], [25, 27], [26, 27], [25, 28]]
END = datetime(2026, 11, 20, tzinfo=UTC)
START = END - timedelta(days=30)
ADIABATIC_LIMIT = math.sqrt(0.05 / 2.474)
GRAY, BLUE, ORANGE, RED = "#737373", "#2563eb", "#d97706", "#dc2626"
Pair = sdk.QubitPair


def fixture_broker() -> FakeBroker:
    qubits = [str(i) for i in range(24, 29)]
    return FakeBroker(
        topology=grid_topology(
            list(range(24, 29)), COUPLINGS, muxes={"6": [24, 25, 26, 27], "7": [28]}
        ),
        latest={
            "qubit": {
                "qubit_frequency": {"24": 7.0, "25": 7.5, "26": 7.7, "27": 7.2, "28": 8.0},
                "qubit_anharmonicity": dict.fromkeys(qubits, -0.3),
                "resonator_frequency": dict.fromkeys(qubits, 8.3),
                "t1": dict.fromkeys(qubits, 50.0),
                "t2_echo": dict.fromkeys(qubits, 40.0),
            },
            "coupling": {
                "qubit_qubit_coupling_strength": {f"{c}-{t}": 8.0 for c, t in COUPLINGS},
            },
        },
    )


@pytest.fixture(scope="module")
def definitions() -> dict[str, sdk.Metric]:
    worker.install_public_module()
    return sdk.load_source(TEMPLATES["collision"].source)


@pytest.fixture
def evaluate(definitions):
    def run(
        kind: str,
        target: str | sdk.QubitPair,
        broker: FakeBroker | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        definition = definitions[kind]
        effective = sdk.resolve_parameters(definition.parameters, params)
        ctx = sdk.AnalysisContext(broker or fixture_broker(), "chip-1", START, END, effective)
        return worker.evaluate_cell(definition, target, ctx)

    return run


def estimates(cell: dict[str, Any]) -> list[str]:
    return list(cell["assessment"]["estimates"])


def test_all_thirteen_types_produce_finite_results(definitions, evaluate):
    assert len(definitions) == 13
    for name in definitions:
        cell = evaluate(name, "24" if name == "Type0A" else Pair("24", "25", 1))
        assert cell["status"] == "ok", (name, cell)
        assert cell["value"] is not None and math.isfinite(cell["value"]), (name, cell)


def test_mux_restriction_and_type2b_compatibility(evaluate):
    assert evaluate("Type1A", Pair("24", "28", 2))["status"] == "empty"
    assert evaluate("Type1A", Pair("24", "27", 2))["status"] == "ok"
    cell = evaluate("Type2B", Pair("24", "25", 1))
    d, a, g = -0.5, -0.3, 0.008
    drive = -(1 / (4 * 500)) * d * (d + a) / (g * a)
    expected = abs(math.sqrt(2) * drive * g / (1 / (d + a) - 1 / d) / (2 * d + a)) / ADIABATIC_LIMIT
    assert cell["value"] == pytest.approx(expected)
    assert any("Qubex-compatible" in note for note in estimates(cell))


@pytest.mark.parametrize(
    ("detuning", "color"),
    [(0, RED), (5, RED), (-5, RED), (10, ORANGE), (-10, ORANGE), (20, BLUE), (-20, BLUE)],
)
def test_type2c_signed_detuning_and_window(detuning, color, evaluate):
    broker = fixture_broker()
    # Only the control's resonator is needed.
    broker.latest["qubit"]["resonator_frequency"] = {"24": (8300.0 - detuning) / 1000}
    cell = evaluate("Type2C", Pair("24", "25", 1), broker)
    assert cell["value"] == pytest.approx(detuning, abs=1e-9)
    assert cell["color"] == color
    assert "screening only" in cell["label"]
    assert "leakage probability" in estimates(cell)[-1]
    # Type2C must not estimate the CR drive strength from couplings.
    assert not [a for a in broker.ops("latest") if a["kind"] == "coupling"]


def test_type2c_direction_window_and_hops(definitions, evaluate):
    forward = evaluate("Type2C", Pair("24", "25", 1))
    reverse = evaluate("Type2C", Pair("25", "24", 1))
    assert forward["value"] == pytest.approx(0, abs=1e-9)
    assert reverse["value"] == pytest.approx(-1500)
    widened = evaluate("Type2C", Pair("25", "24", 1), params={"two_photon_window": 2000.0})
    assert widened["color"] == RED
    assert evaluate("Type2C", Pair("24", "27", 2))["status"] == "empty"
    # Adjacent inter-MUX CR edges remain eligible.
    assert evaluate("Type2C", Pair("25", "28", 1))["value"] is not None
    metadata = definitions["Type2C"].metadata()
    assert metadata["unit"] == "MHz"
    assert metadata["target"] == "pair"
    assert metadata["parameters"]["two_photon_window"]["default"] == 10.0


@pytest.mark.parametrize("key", ["resonator_frequency", "qubit_frequency"])
def test_type2c_missing_frequency_is_unevaluated(key, evaluate):
    broker = fixture_broker()
    del broker.latest["qubit"][key]["24"]
    cell = evaluate("Type2C", Pair("24", "25", 1), broker)
    assert cell["status"] == "missing"
    assert cell["value"] is None
    assert cell["color"] == GRAY
    assert f"{key}[Q24] is missing" in cell["label"]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, 0])
def test_type2c_invalid_resonator_is_unevaluated(value, evaluate):
    broker = fixture_broker()
    broker.latest["qubit"]["resonator_frequency"]["24"] = value
    assert evaluate("Type2C", Pair("24", "25", 1), broker)["value"] is None


def test_default_coupling_and_parameter_override(evaluate):
    pair = Pair("24", "25", 1)
    measured = evaluate("Type3A", pair)
    assert measured["value"] is not None
    assert estimates(measured) == []
    broker = fixture_broker()
    broker.latest["coupling"] = {}
    fallback = evaluate("Type3A", pair, broker)
    assert fallback["value"] == pytest.approx(measured["value"])
    assert estimates(fallback) == [
        "Default coupling Q24–Q25: 0.008 GHz (default_coupling; measured coupling unavailable)"
    ]
    changed = evaluate("Type3A", pair, broker, params={"default_coupling": 0.012})
    assert changed["value"] == pytest.approx(measured["value"] * 1.5)
    assert "0.012 GHz" in estimates(changed)[0]


def test_defaults_and_anharmonicity_estimate_sources(evaluate):
    broker = fixture_broker()
    del broker.latest["qubit"]["t1"]["24"]
    del broker.latest["qubit"]["t2_echo"]["24"]
    quality = evaluate("Type0A", "24", broker, params={"default_t1": 12000, "default_t2": 15000})
    assert estimates(quality) == [
        "Default t1[Q24]: 12000 ns (default_t1; measured value unavailable)",
        "Default t2_echo[Q24]: 15000 ns (default_t2; measured value unavailable)",
    ]
    del broker.latest["qubit"]["qubit_anharmonicity"]["24"]
    cell = evaluate("Type1C", Pair("24", "25", 1), broker)
    note = next(n for n in estimates(cell) if n.startswith("Estimated qubit_anharmonicity[Q24]"))
    assert "α = −fGE/19; fGE = 7 GHz" in note
    assert f"{-7 / 19:g} GHz" in note


def test_calculated_coupling_and_drive_explain_inputs(evaluate):
    expected = sum(0.5 * 0.008**2 * (1 / (7 - fm) + 1 / (fm - 7.2)) for fm in (7.5, 7.7))
    cell = evaluate("Type1A", Pair("24", "27", 2))
    assert cell["value"] == pytest.approx(abs(2 * expected / (7 - 7.2)) / ADIABATIC_LIMIT)
    notes = estimates(cell)
    for mid, frequency in (("25", "7.5"), ("26", "7.7")):
        note = next(n for n in notes if f"via Q{mid}" in n)
        assert "gcm = 0.008, gmt = 0.008" in note
        assert f"fc = 7, fm = {frequency}, ft = 7.2" in note
        assert "1/(fc−fm) + 1/(fm−ft)" in note
    assert f"{expected:g} GHz" in notes[-1]

    drive_cell = evaluate("Type1C", Pair("24", "25", 1))
    drive = -(1 / (4 * 500)) * -0.5 * -0.8 / (0.008 * -0.3)
    assert drive_cell["value"] == pytest.approx(abs(drive / -0.5) / 0.75)
    last = estimates(drive_cell)[-1]
    assert f"{drive:g} GHz" in last
    assert "Ωd = −Δ(Δ+α)/(4×CNOT time×g×α)" in last
    assert "Δ = -0.5 GHz, α = -0.3 GHz, g = 0.008 GHz, CNOT time = 500 ns" in last


def test_notes_deduplicated_and_preserved_when_unevaluated(evaluate):
    broker = fixture_broker()
    broker.latest["coupling"] = {}
    cell = evaluate("Type2B", Pair("24", "25", 1), broker)
    assert sum(n.startswith("Default coupling") for n in estimates(cell)) == 1
    broker.latest["qubit"]["qubit_anharmonicity"]["24"] = 0.5
    cell = evaluate("Type2A", Pair("24", "25", 1), broker)
    assert cell["value"] is None
    assert any(n.startswith("Default coupling") for n in estimates(cell))
    assert any(n.startswith("Estimated CR drive") for n in estimates(cell))


def test_overflowing_drive_is_unevaluated(evaluate):
    broker = fixture_broker()
    # A vanishing measured coupling makes the estimated CR drive overflow when squared.
    broker.latest["coupling"]["qubit_qubit_coupling_strength"]["24-25"] = 1e-197
    cell = evaluate("Type2A", Pair("24", "25", 1), broker)
    assert cell["value"] is None
    assert cell["color"] == GRAY
    assert cell["label"].startswith("Not evaluated")


def test_zero_frequency_counts_as_missing(evaluate):
    broker = fixture_broker()
    broker.latest["qubit"]["qubit_frequency"]["24"] = 0.0
    cell = evaluate("Type0A", "24", broker)
    assert cell["value"] is None
    assert cell["label"] == "Not evaluated: qubit_frequency[Q24] is missing"


def test_qubit_quality_scores_and_colors(evaluate):
    cell = evaluate("Type0A", "24")
    assert cell["value"] == pytest.approx(6.5 / 7.0)
    assert cell["color"] == BLUE
    assert cell["label"] == "0.93× within limit"
    checks = cell["assessment"]["checks"]
    assert [c["label"] for c in checks] == ["min frequency", "max frequency", "T1", "T2"]
    assert checks[2]["value"] == pytest.approx(3000 / 50000)
    assert checks[3]["value"] == pytest.approx(3000 / 40000)
    broker = fixture_broker()
    broker.latest["qubit"]["qubit_frequency"]["24"] = 6.0
    assert evaluate("Type0A", "24", broker)["color"] == RED


def test_legends(definitions):
    legend = definitions["Type1A"].legend.serialize("dimensionless", "dimensionless")
    assert [item["color"] for item in legend["items"]] == [BLUE, ORANGE, RED, GRAY]
    assert definitions["Type2C"].legend.entries[0][1] == "Outside |δ₂γ| window"


def test_resolve_params_validates_names_and_ranges(definitions):
    parameters = definitions["Type1A"].parameters
    params = sdk.resolve_parameters(parameters, {"cnot_time": 300})
    assert params["cnot_time"] == 300
    assert params["min_frequency"] == 6.5
    with pytest.raises(ValueError, match="Unknown parameters"):
        sdk.resolve_parameters(definitions["Type2C"].parameters, {"cnot_time": 300})
    with pytest.raises(ValueError, match="cnot_time"):
        sdk.resolve_parameters(parameters, {"cnot_time": 0})


def test_whole_chip_through_the_real_worker(evaluate):
    settings = RuntimeSettings(timeout_seconds=60)

    def run(kind: str) -> dict[str, dict[str, Any]]:
        outcome = executor.evaluate(
            source=TEMPLATES["collision"].source,
            metric_id=kind,
            chip_id="chip-1",
            start=START.isoformat(),
            end=END.isoformat(),
            params={},
            broker=fixture_broker(),
            settings=settings,
        )
        assert outcome.result["legend"]["kind"] == "categorical"
        return {cell["key"]: cell for cell in outcome.result["cells"]}

    qubits = run("Type0A")
    assert list(qubits) == ["24", "25", "26", "27", "28"]
    assert qubits["24"]["value"] == pytest.approx(evaluate("Type0A", "24")["value"])
    pairs = run("Type1A")
    evaluated = {key for key, cell in pairs.items() if cell["status"] != "empty"}
    one_hop = {key for key, cell in pairs.items() if cell["hops"] == 1}
    assert len(one_hop) == 2 * len(COUPLINGS)
    assert one_hop <= evaluated
    # Only same-MUX hops-2 pairs are evaluated: 24<->27 and 25<->26.
    assert evaluated - one_hop == {"24>27", "27>24", "25>26", "26>25"}
    assert pairs["24>28"]["status"] == "empty"
