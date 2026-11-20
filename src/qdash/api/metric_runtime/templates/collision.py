# ruff: noqa: RUF001
"""Qubex-compatible frequency collision checks.

Adapted from qdash-playground examples/collission.py (Apache License 2.0).
Frequencies are GHz and times are ns inside the computation.

Type2B intentionally retains the upstream (qubex) division formula.
Type2C is a viewer extension: static e0-f1 resonance screening, not a leakage rate.

Inputs are the latest values within the panel period. A stored zero counts as missing
(older calibrations stored NaN as 0). Missing coupling strengths, T1 and T2 fall back to
the default parameters and the fallback is listed in the cell details.
"""

import math

from qdash_metrics import CellResult, Legend, MissingData, Parameter, metric

BLUE = "#2563eb"
ORANGE = "#d97706"
RED = "#dc2626"
GRAY = "#737373"

PARAMS = {
    "min_frequency": Parameter(default=6.5, unit="GHz"),
    "max_frequency": Parameter(default=9.5, unit="GHz"),
    "max_detuning": Parameter(default=1.5, min=0.001, unit="GHz"),
    "min_t1": Parameter(default=3000.0, min=1, unit="ns"),
    "min_t2": Parameter(default=3000.0, min=1, unit="ns"),
    "adiabatic_limit": Parameter(default=math.sqrt(0.05 / 2.474), min=0.000001),
    "cr_control_limit": Parameter(default=0.75, min=0.000001),
    "cnot_time": Parameter(default=500.0, min=1, unit="ns"),
    "default_coupling": Parameter(default=0.008, min=0.000001, unit="GHz"),
    "default_t1": Parameter(default=10000.0, min=1, unit="ns"),
    "default_t2": Parameter(default=10000.0, min=1, unit="ns"),
}
LEGEND = Legend.categorical(
    [
        (BLUE, "< 1×"),
        (ORANGE, "1× boundary"),
        (RED, "> 1× exceeded"),
        (GRAY, "Not evaluated"),
    ]
)
TYPE2C_PARAMS = {
    "two_photon_window": Parameter(
        default=10.0,
        label="Type2C |δ₂γ| window (screening only)",
        min=0.000001,
        unit="MHz",
    ),
}
TYPE2C_LEGEND = Legend.categorical(
    [
        (BLUE, "Outside |δ₂γ| window"),
        (ORANGE, "Window boundary"),
        (RED, "Inside |δ₂γ| window"),
        (GRAY, "Not evaluated"),
    ]
)


class Inputs:
    """Reads check inputs and records the defaults and estimates used."""

    def __init__(self, ctx):
        self.ctx, self.notes = ctx, []
        self.p = ctx.params

    def read(self, key, q, unit, default=None, note=None):
        try:
            value = float(self.ctx.data[key][q].latest().to(unit).magnitude)
            if value == 0:
                raise MissingData(f"{key}[Q{q}] is zero")
            return value
        except (MissingData, KeyError):
            if default is None:
                raise MissingData(f"{key}[Q{q}] is missing") from None
            self.notes.append(note or f"Default {key}[Q{q}]: {default:g} {unit}")
            return default

    def f(self, q):
        return self.read("qubit_frequency", q, "GHz")

    def a(self, q):
        f = self.f(q)
        return self.read(
            "qubit_anharmonicity",
            q,
            "GHz",
            -f / 19,
            f"Estimated qubit_anharmonicity[Q{q}]: {-f / 19:g} GHz "
            f"(fallback approximation α = −fGE/19; fGE = {f:g} GHz)",
        )

    def g(self, c, t):
        value = self.ctx.coupling_strength(c, t)
        if value is not None:
            ghz = float(value.to("GHz").magnitude)
            if ghz != 0:
                return ghz
        self.notes.append(
            f"Default coupling Q{c}–Q{t}: {self.p['default_coupling']:g} GHz "
            "(default_coupling; measured coupling unavailable)"
        )
        return self.p["default_coupling"]

    def coupling(self, c, t, hops):
        if hops == 1:
            return self.g(c, t)
        topology = self.ctx.topology
        mids = set(topology.neighbors(c)) & set(topology.neighbors(t))
        terms = []
        for m in sorted(mids, key=int):
            gcm, gmt = self.g(c, m), self.g(m, t)
            fc, fm, ft = self.f(c), self.f(m), self.f(t)
            term = 0.5 * gcm * gmt * (1 / (fc - fm) + 1 / (fm - ft))
            terms.append(term)
            self.notes.append(
                f"Estimated effective coupling Q{c}–Q{t} via Q{m}: {term:g} GHz "
                f"(gcm×gmt/2 × [1/(fc−fm) + 1/(fm−ft)]; "
                f"gcm = {gcm:g}, gmt = {gmt:g}, fc = {fc:g}, fm = {fm:g}, ft = {ft:g}; all GHz)"
            )
        value = sum(terms)
        self.notes.append(
            f"Estimated effective coupling Q{c}–Q{t}: {value:g} GHz "
            "(sum of intermediate-qubit contributions)"
        )
        return value

    def drive(self, c, t):
        d, a = self.f(c) - self.f(t), self.a(c)
        g, time = self.g(c, t), self.p["cnot_time"]
        value = -(1 / (4 * time)) * d * (d + a) / (g * a)
        self.notes.append(
            f"Estimated CR drive Q{c}→Q{t}: {value:g} GHz "
            f"(Ωd = −Δ(Δ+α)/(4×CNOT time×g×α); Δ = {d:g} GHz, "
            f"α = {a:g} GHz, g = {g:g} GHz, CNOT time = {time:g} ns)"
        )
        return value


def same_mux(ctx, a, b):
    """Whether qubits ``a`` and ``b`` are members of the same MUX."""
    return any(
        a in map(str, members) and b in map(str, members)
        for members in ctx.topology.raw.get("muxes", {}).values()
    )


def dedupe(notes):
    return list(dict.fromkeys(notes))


def type2c(x, ctx, c, t):
    # Static approximation to 2 fd = f_ef,c + f_r,c, with fd = f_ge,t.
    # No CR drive-amplitude/coupling estimate is needed for this screen.
    fd = x.f(t)
    ef = x.f(c) + x.a(c)
    fr = x.read("resonator_frequency", c, "GHz")
    detuning = (2 * fd - ef - fr) * 1000
    window = ctx.params["two_photon_window"]
    if not all(math.isfinite(v) for v in (fd, ef, fr, detuning, window)):
        raise ValueError("Nonfinite Type2C input")
    if min(fd, ef, fr, window) <= 0:
        raise ValueError("Type2C frequencies and window must be positive")
    boundary = math.isclose(abs(detuning), window, rel_tol=1e-12, abs_tol=1e-9)
    near = abs(detuning) < window
    verdict = "boundary" if boundary else "inside window" if near else "outside window"
    return CellResult(
        detuning,
        color=ORANGE if boundary else RED if near else BLUE,
        assessment={
            "label": f"δ₂γ = {detuning:+.3f} MHz; {verdict} (screening only)",
            "checks": [
                (f"CR Q{c}→Q{t}: assumed drive frequency (GHz)", fd),
                (f"Control Q{c} EF frequency (GHz)", ef),
                (f"Control Q{c} resonator frequency (GHz)", fr),
                ("Two-photon resonance drive frequency (GHz)", (ef + fr) / 2),
                ("Signed δ₂γ = 2fd − (fEF + fr) (MHz)", detuning),
                ("Screening half-width in δ₂γ (MHz)", window),
            ],
            "estimates": dedupe(
                [
                    *x.notes,
                    "Static resonance screening only; fd = target GE. "
                    "No Stark/dispersive corrections, effective two-photon coupling, "
                    "pulse-duration dependence or leakage probability are modeled. "
                    "The default 10 MHz window is illustrative, not a calibrated tolerance.",
                ]
            ),
        },
    )


def evaluate(kind, target, ctx):
    """Evaluate one check for a qubit (Type0A) or a directed pair.

    Returns None when the pair is outside the check's scope (hops 2 is only evaluated
    for Type1A/Type3A within a MUX).
    """
    x = Inputs(ctx)
    params = ctx.params
    checks = []
    try:
        if kind == "Type0A":
            q = target
            f = x.f(q)
            checks = [
                ("min frequency", params["min_frequency"] / f),
                ("max frequency", f / params["max_frequency"]),
                (
                    "T1",
                    params["min_t1"]
                    / x.read(
                        "t1",
                        q,
                        "ns",
                        params["default_t1"],
                        f"Default t1[Q{q}]: {params['default_t1']:g} ns "
                        "(default_t1; measured value unavailable)",
                    ),
                ),
                (
                    "T2",
                    params["min_t2"]
                    / x.read(
                        "t2_echo",
                        q,
                        "ns",
                        params["default_t2"],
                        f"Default t2_echo[Q{q}]: {params['default_t2']:g} ns "
                        "(default_t2; measured value unavailable)",
                    ),
                ),
            ]
        else:
            c, t, h = target.source, target.target, target.hops
            if h == 2 and (kind not in ("Type1A", "Type3A") or not same_mux(ctx, c, t)):
                return None
            if kind == "Type2C":
                return type2c(x, ctx, c, t)
            d, a = x.f(c) - x.f(t), x.a(c)
            limit = params["adiabatic_limit"]
            topology = ctx.topology

            def add(label, value, threshold=limit):
                checks.append((f"{label}: {value:g}; limit {threshold:g}", abs(value) / threshold))

            if kind == "Type0B":
                add("Detuning GHz", d, params["max_detuning"])
            elif kind == "Type1A":
                add("|2g/Δ|", 2 * x.coupling(c, t, h) / d)
            elif kind == "Type3A":
                add("|2√2g/(Δ+α)|", 2**1.5 * x.coupling(c, t, h) / (d + a))
            elif kind == "Type1B":
                for s in topology.neighbors(c):
                    if s != t and same_mux(ctx, t, s):
                        add(
                            f"target Q{t}, spectator Q{s}",
                            1 / (4 * params["cnot_time"]) / (x.f(t) - x.f(s)),
                        )
            else:
                drive = x.drive(c, t)
                if kind == "Type1C":
                    add("|Ωd/Δ|", drive / d, params["cr_control_limit"])
                elif kind == "Type2A":
                    add("|Ωeff/(2Δ+α)|", 2**-1.5 * drive**2 * (1 / (d + a) - 1 / d) / (2 * d + a))
                elif kind == "Type2B":
                    x.notes.append(
                        "Qubex-compatible Type2B: inverse-detuning difference is a divisor; "
                        "units are not dimensionless."
                    )
                    add(
                        "Qubex Type2B ratio",
                        math.sqrt(2) * drive * x.g(c, t) / (1 / (d + a) - 1 / d) / (2 * d + a),
                    )
                elif kind == "Type3B":
                    add(
                        "|√2Ωd/(Δ+α)|",
                        math.sqrt(2) * drive / (d + a),
                        params["cr_control_limit"],
                    )
                elif kind == "Type7":
                    for driven in topology.neighbors(c):
                        if driven == t:
                            continue
                        dt = x.f(c) - x.f(driven)
                        add(
                            f"Driven Q{c}→Q{driven}, spectator Q{t}",
                            2**-0.5
                            * x.g(c, t)
                            * x.drive(c, driven)
                            * (1 / (dt + a) - 1 / dt + 1 / (d + a) - 1 / d)
                            / (2 * d + a),
                        )
                elif kind in ("Type8", "Type9"):
                    shift = drive**2 * a / (2 * d * (d + a))
                    spectators = set(topology.neighbors(c)) - {t}
                    spectators.update(
                        p.target
                        for p in topology.pairs(hops=(2,))
                        if p.source == c and same_mux(ctx, c, p.target)
                    )
                    for s in sorted(spectators, key=int):
                        before = x.f(c) - x.f(s) - (x.a(s) if kind == "Type9" else 0)
                        checks.append(
                            (
                                f"Spectator Q{s}: {before * 1000:g} → "
                                f"{(before + shift) * 1000:g} MHz",
                                max(0, -shift / before),
                            )
                        )
        if not checks:
            return None
        score = max(v for _, v in checks)
        if not math.isfinite(score):
            raise ValueError("Nonfinite approximation")
        verdict = "exceeded" if score > 1 else "boundary" if score == 1 else "within limit"
        return CellResult(
            score,
            color=RED if score > 1 else ORANGE if score == 1 else BLUE,
            assessment={
                "label": f"{score:.2f}× {verdict}",
                "checks": checks,
                "estimates": dedupe(x.notes),
            },
        )
    except (MissingData, ZeroDivisionError, ValueError, OverflowError) as exc:
        return CellResult(
            None,
            color=GRAY,
            assessment={
                "label": f"Not evaluated: {exc}",
                "checks": checks,
                "estimates": dedupe(x.notes),
            },
        )


def register(kind, description):
    def function(target, ctx):
        return evaluate(kind, target, ctx)

    function.__name__ = kind
    return metric(
        title=f"{kind} — {description}",
        unit="MHz" if kind == "Type2C" else "dimensionless",
        target="qubit" if kind == "Type0A" else "pair",
        hops=(1, 2),
        parameters=TYPE2C_PARAMS if kind == "Type2C" else PARAMS,
        legend=TYPE2C_LEGEND if kind == "Type2C" else LEGEND,
    )(function)


CHECKS = [
    ("Type0A", "Qubit quality"),
    ("Type0B", "Excessive detuning"),
    ("Type1A", "GE–GE proximity"),
    ("Type1B", "CR selectivity"),
    ("Type1C", "CR causes GE"),
    ("Type2A", "Two-photon GF"),
    ("Type2B", "FG–GE"),
    ("Type2C", "Two-photon e0–f1 detuning (screening)"),
    ("Type3A", "EF–GE proximity"),
    ("Type3B", "CR causes EF"),
    ("Type7", "Spectator FG–GE"),
    ("Type8", "Stark GE–GE crossing"),
    ("Type9", "Stark GE–EF crossing"),
]

for _kind, _description in CHECKS:
    globals()[_kind] = register(_kind, _description)
