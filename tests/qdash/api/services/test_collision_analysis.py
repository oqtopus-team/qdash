# ruff: noqa: RUF001
"""Tests for the qubex-compatible collision checks.

Ported from the qdash-playground reference tests; every expected number is kept.
"""

import math

import pytest

from qdash.api.services.collision_analysis import (
    CHECKS,
    PARAMS,
    TYPE2C_PARAMS,
    CollisionContext,
    CollisionTopology,
    Inputs,
    Measurement,
    QubitPair,
    convert_unit,
    evaluate,
    evaluate_check,
    resolve_params,
)

COUPLINGS = [[24, 25], [24, 26], [25, 27], [26, 27], [25, 28]]


def context() -> CollisionContext:
    values: dict[str, dict[str, float]] = {
        "qubit_frequency": {"24": 7.0, "25": 7.5, "26": 7.7, "27": 7.2, "28": 8.0},
        "qubit_anharmonicity": {str(i): -0.3 for i in range(24, 29)},
        "resonator_frequency": {str(i): 8.3 for i in range(24, 29)},
        "t1": {str(i): 50 for i in range(24, 29)},
        "t2_echo": {str(i): 40 for i in range(24, 29)},
    }
    data: dict[str, dict[str, Measurement]] = {
        key: {
            q: (float(value), "us" if key in ("t1", "t2_echo") else "GHz")
            for q, value in entries.items()
        }
        for key, entries in values.items()
    }
    topology = CollisionTopology(
        qubits=range(24, 29),
        couplings=COUPLINGS,
        muxes={6: [24, 25, 26, 27], 7: [28]},
    )
    return CollisionContext(
        topology=topology,
        params={k: p.default for k, p in {**PARAMS, **TYPE2C_PARAMS}.items()},
        data=data,
        couplings={f"{c}-{t}": (8.0, "MHz") for c, t in COUPLINGS},
    )


def without_couplings(ctx: CollisionContext) -> CollisionContext:
    ctx.couplings = {}
    return ctx


def test_all_thirteen_types_produce_finite_results():
    assert len(CHECKS) == 13
    for name in CHECKS:
        result = evaluate(name, "24" if name == "Type0A" else QubitPair("24", "25", 1), context())
        assert result is not None, name
        assert result.value is not None and math.isfinite(result.value), (name, result)


def test_mux_restriction_and_type2b_compatibility():
    ctx = context()
    assert evaluate("Type1A", QubitPair("24", "28", 2), ctx) is None
    assert evaluate("Type1A", QubitPair("24", "27", 2), ctx) is not None
    result = evaluate("Type2B", QubitPair("24", "25", 1), ctx)
    assert result is not None
    d, a, g = -0.5, -0.3, 0.008
    drive = -(1 / (4 * 500)) * d * (d + a) / (g * a)
    expected = (
        abs(math.sqrt(2) * drive * g / (1 / (d + a) - 1 / d) / (2 * d + a))
        / ctx.params["adiabatic_limit"]
    )
    assert result.value == pytest.approx(expected)
    assert any("Qubex-compatible" in note for note in result.assessment["estimates"])


@pytest.mark.parametrize(
    "detuning, color",
    [
        (0, "#dc2626"),
        (5, "#dc2626"),
        (-5, "#dc2626"),
        (10, "#d97706"),
        (-10, "#d97706"),
        (20, "#2563eb"),
        (-20, "#2563eb"),
    ],
)
def test_type2c_signed_detuning_and_window(detuning, color, monkeypatch):
    ctx = context()
    # Mix units to check conversion. Only the control's resonator is needed.
    ctx.data["resonator_frequency"] = {"24": (8300.0 - detuning, "MHz")}

    def fail(*_args: object) -> None:
        pytest.fail("Type2C must not estimate CR drive strength")

    monkeypatch.setattr(ctx, "coupling_strength", fail)
    result = evaluate("Type2C", QubitPair("24", "25", 1), ctx)
    assert result is not None
    assert result.value == pytest.approx(detuning, abs=1e-9)
    assert result.color == color
    assert "screening only" in result.assessment["label"]
    assert "leakage probability" in result.assessment["estimates"][-1]


def test_type2c_direction_window_and_hops():
    ctx = context()
    forward = evaluate("Type2C", QubitPair("24", "25", 1), ctx)
    reverse = evaluate("Type2C", QubitPair("25", "24", 1), ctx)
    assert forward is not None and reverse is not None
    assert forward.value == pytest.approx(0, abs=1e-9)
    assert reverse.value == pytest.approx(-1500)
    ctx.params["two_photon_window"] = 2000.0
    widened = evaluate("Type2C", QubitPair("25", "24", 1), ctx)
    assert widened is not None and widened.color == "#dc2626"
    assert evaluate("Type2C", QubitPair("24", "27", 2), ctx) is None
    # Adjacent inter-MUX CR edges remain eligible.
    inter_mux = evaluate("Type2C", QubitPair("25", "28", 1), ctx)
    assert inter_mux is not None and inter_mux.value is not None
    definition = CHECKS["Type2C"]
    assert definition.unit == "MHz"
    assert definition.target == "pair"
    assert definition.parameters["two_photon_window"].default == 10.0


@pytest.mark.parametrize("key", ["resonator_frequency", "qubit_frequency"])
def test_type2c_missing_frequency_is_unevaluated(key):
    ctx = context()
    del ctx.data[key]["24"]
    result = evaluate("Type2C", QubitPair("24", "25", 1), ctx)
    assert result is not None
    assert result.value is None
    assert result.color == "#737373"
    assert f"{key}[Q24] is missing" in result.assessment["label"]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, 0])
def test_type2c_invalid_resonator_is_unevaluated(value):
    ctx = context()
    ctx.data["resonator_frequency"]["24"] = (value, "GHz")
    result = evaluate("Type2C", QubitPair("24", "25", 1), ctx)
    assert result is not None and result.value is None


def test_default_coupling_and_parameter_override():
    ctx = context()
    pair = QubitPair("24", "25", 1)
    measured = evaluate("Type3A", pair, ctx)
    assert measured is not None and measured.value is not None
    assert measured.assessment["estimates"] == []
    without_couplings(ctx)
    fallback = evaluate("Type3A", pair, ctx)
    assert fallback is not None
    assert fallback.value == measured.value
    assert fallback.assessment["estimates"] == [
        "Default coupling Q24–Q25: 0.008 GHz (default_coupling; measured coupling unavailable)"
    ]
    ctx.params["default_coupling"] = 0.012
    changed = evaluate("Type3A", pair, ctx)
    assert changed is not None
    assert changed.value == pytest.approx(measured.value * 1.5)
    assert "0.012 GHz" in changed.assessment["estimates"][0]


def test_defaults_and_anharmonicity_estimate_sources():
    ctx = context()
    del ctx.data["t1"]["24"]
    del ctx.data["t2_echo"]["24"]
    ctx.params.update(default_t1=12000, default_t2=15000)
    quality = evaluate("Type0A", "24", ctx)
    assert quality is not None
    assert quality.assessment["estimates"] == [
        "Default t1[Q24]: 12000 ns (default_t1; measured value unavailable)",
        "Default t2_echo[Q24]: 15000 ns (default_t2; measured value unavailable)",
    ]
    del ctx.data["qubit_anharmonicity"]["24"]
    inputs = Inputs(ctx)
    assert inputs.a("24") == pytest.approx(-7 / 19)
    assert "Estimated qubit_anharmonicity[Q24]" in inputs.notes[0]
    assert "α = −fGE/19; fGE = 7 GHz" in inputs.notes[0]
    assert f"{-7 / 19:g} GHz" in inputs.notes[0]


def test_calculated_coupling_and_drive_explain_inputs():
    inputs = Inputs(context())
    expected = sum(0.5 * 0.008**2 * (1 / (7 - fm) + 1 / (fm - 7.2)) for fm in (7.5, 7.7))
    assert inputs.coupling("24", "27", 2) == pytest.approx(expected)
    for mid, frequency in (("25", "7.5"), ("26", "7.7")):
        note = next(n for n in inputs.notes if f"via Q{mid}" in n)
        assert "gcm = 0.008, gmt = 0.008" in note
        assert f"fc = 7, fm = {frequency}, ft = 7.2" in note
        assert "1/(fc−fm) + 1/(fm−ft)" in note
    assert f"{expected:g} GHz" in inputs.notes[-1]
    drive = inputs.drive("24", "25")
    assert drive == pytest.approx(-(1 / (4 * 500)) * -0.5 * -0.8 / (0.008 * -0.3))
    assert f"{drive:g} GHz" in inputs.notes[-1]
    assert "Ωd = −Δ(Δ+α)/(4×CNOT time×g×α)" in inputs.notes[-1]
    assert "Δ = -0.5 GHz, α = -0.3 GHz, g = 0.008 GHz, CNOT time = 500 ns" in inputs.notes[-1]


def test_notes_deduplicated_and_preserved_when_unevaluated():
    ctx = without_couplings(context())
    result = evaluate("Type2B", QubitPair("24", "25", 1), ctx)
    assert result is not None
    assert sum(n.startswith("Default coupling") for n in result.assessment["estimates"]) == 1
    ctx.data["qubit_anharmonicity"]["24"] = (0.5, "GHz")
    result = evaluate("Type2A", QubitPair("24", "25", 1), ctx)
    assert result is not None
    assert result.value is None
    assert any(n.startswith("Default coupling") for n in result.assessment["estimates"])
    assert any(n.startswith("Estimated CR drive") for n in result.assessment["estimates"])


# --- QDash-specific additions -------------------------------------------------


def test_overflowing_drive_is_unevaluated():
    ctx = context()
    # A vanishing measured coupling makes the estimated CR drive overflow when squared.
    ctx.couplings["24-25"] = (1e-200, "GHz")
    result = evaluate("Type2A", QubitPair("24", "25", 1), ctx)
    assert result is not None
    assert result.value is None
    assert result.color == "#737373"
    assert result.assessment["label"].startswith("Not evaluated")


def test_catalog_order_titles_and_legends():
    assert list(CHECKS)[:3] == ["Type0A", "Type0B", "Type1A"]
    assert list(CHECKS)[-1] == "Type9"
    assert CHECKS["Type0A"].title == "Type0A — Qubit quality"
    assert CHECKS["Type0A"].target == "qubit"
    assert CHECKS["Type1A"].unit == "dimensionless"
    assert [color for color, _ in CHECKS["Type1A"].legend] == [
        "#2563eb",
        "#d97706",
        "#dc2626",
        "#737373",
    ]


def test_topology_pairs_neighbors_and_mux():
    topology = context().topology
    assert topology.neighbors("25") == ["24", "27", "28"]
    hop2_from_24 = [p.target for p in topology.pairs(hops=(2,)) if p.source == "24"]
    assert hop2_from_24 == ["27", "28"]
    assert QubitPair("25", "24", 1) in topology.pairs(hops=(1,))
    assert topology.same_mux("24", "27")
    assert not topology.same_mux("24", "28")


def test_evaluate_check_covers_targets_and_respects_hops():
    ctx = context()
    qubit_cells = evaluate_check("Type0A", ctx)
    assert [cell.key for cell in qubit_cells] == ["Q24", "Q25", "Q26", "Q27", "Q28"]
    one_hop = evaluate_check("Type1A", ctx, hops=(1,))
    assert len(one_hop) == 2 * len(COUPLINGS)
    both = evaluate_check("Type1A", ctx, hops=(1, 2))
    # Only same-MUX hops-2 pairs are evaluated: 24<->27 and 25<->26.
    assert {cell.key for cell in both} - {cell.key for cell in one_hop} == {
        "24-27",
        "27-24",
        "25-26",
        "26-25",
    }


def test_unit_conversion():
    assert convert_unit(8300, "MHz", "GHz") == pytest.approx(8.3)
    assert convert_unit(1, "KHz", "MHz") == pytest.approx(0.001)
    assert convert_unit(5e9, "Hz", "GHz") == pytest.approx(5)
    assert convert_unit(50, "μs", "ns") == pytest.approx(50000)
    assert convert_unit(50, "µs", "ns") == pytest.approx(50000)
    assert convert_unit(1, "ms", "us") == pytest.approx(1000)
    assert convert_unit(1, "s", "ns") == pytest.approx(1e9)
    with pytest.raises(ValueError):
        convert_unit(1, "GHz", "ns")
    with pytest.raises(ValueError):
        convert_unit(1, "furlong", "ns")


def test_resolve_params_validates_names_and_ranges():
    params = resolve_params("Type1A", {"cnot_time": 300})
    assert params["cnot_time"] == 300
    assert params["min_frequency"] == 6.5
    with pytest.raises(ValueError, match="Unknown parameter"):
        resolve_params("Type2C", {"cnot_time": 300})
    with pytest.raises(ValueError, match=">="):
        resolve_params("Type1A", {"cnot_time": 0})
    with pytest.raises(KeyError):
        resolve_params("TypeX")
