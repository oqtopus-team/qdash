"""Qubex-compatible frequency collision checks.

Frequencies are GHz and times are ns inside the computation.

Type2B intentionally retains the upstream (qubex) division formula.
Type2C is a viewer extension: static e0–f1 resonance screening, not a leakage rate.

This module performs no database access. Build a :class:`CollisionContext` from
plain dictionaries and a :class:`CollisionTopology`, then call :func:`evaluate`
for one target or :func:`evaluate_check` for every target on the chip.
"""

# ruff: noqa: RUF001, RUF002
# Notes and labels use physics notation (α, Δ, Ω, −, ×, –) and must match the
# reference implementation character for character.

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, TypedDict

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from qdash.common.config.topology import TopologyDefinition


class MissingData(ValueError):
    """A measured value required by a check is unavailable."""


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------

_FREQUENCY_TO_GHZ: dict[str, float] = {
    "hz": 1e-9,
    "khz": 1e-6,
    "mhz": 1e-3,
    "ghz": 1.0,
}
_TIME_TO_NS: dict[str, float] = {
    "ns": 1.0,
    "us": 1e3,
    "µs": 1e3,
    "μs": 1e3,
    "ms": 1e6,
    "s": 1e9,
}


def _unit_scale(unit: str) -> tuple[str, float]:
    """Return ``(dimension, factor to the base unit)`` for a supported unit."""
    key = unit.strip()
    # Case-sensitive time units first so that "ms" stays milliseconds.
    if key in _TIME_TO_NS:
        return "time", _TIME_TO_NS[key]
    lowered = key.lower()
    if lowered in _FREQUENCY_TO_GHZ:
        return "frequency", _FREQUENCY_TO_GHZ[lowered]
    if lowered in _TIME_TO_NS:
        return "time", _TIME_TO_NS[lowered]
    raise ValueError(f"Unsupported unit: {unit!r}")


def convert_unit(value: float, from_unit: str, to_unit: str) -> float:
    """Convert a frequency (Hz–GHz) or time (ns–s) value between units.

    Raises:
        ValueError: If a unit is unknown or the dimensions differ.
    """
    source_dim, source_factor = _unit_scale(from_unit)
    target_dim, target_factor = _unit_scale(to_unit)
    if source_dim != target_dim:
        raise ValueError(f"Cannot convert {from_unit} to {to_unit}")
    return value * source_factor / target_factor


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Parameter:
    """An adjustable numeric input of a check."""

    default: float
    label: str = ""
    min: float | None = None
    unit: str = ""


PARAMS: dict[str, Parameter] = {
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
LEGEND: list[tuple[str, str]] = [
    ("#2563eb", "< 1×"),
    ("#d97706", "1× boundary"),
    ("#dc2626", "> 1× exceeded"),
    ("#737373", "Not evaluated"),
]
TYPE2C_PARAMS: dict[str, Parameter] = {
    "two_photon_window": Parameter(
        default=10.0,
        label="Type2C |δ₂γ| window (screening only)",
        min=0.000001,
        unit="MHz",
    ),
}
TYPE2C_LEGEND: list[tuple[str, str]] = [
    ("#2563eb", "Outside |δ₂γ| window"),
    ("#d97706", "Window boundary"),
    ("#dc2626", "Inside |δ₂γ| window"),
    ("#737373", "Not evaluated"),
]

BLUE = "#2563eb"
ORANGE = "#d97706"
RED = "#dc2626"
GRAY = "#737373"

CheckTarget = Literal["qubit", "pair"]


@dataclass(frozen=True)
class CheckDefinition:
    """Static description of one collision check."""

    kind: str
    description: str
    title: str
    unit: str
    target: CheckTarget
    parameters: Mapping[str, Parameter]
    legend: Sequence[tuple[str, str]]


def _define(kind: str, description: str) -> CheckDefinition:
    return CheckDefinition(
        kind=kind,
        description=description,
        title=f"{kind} — {description}",
        unit="MHz" if kind == "Type2C" else "dimensionless",
        target="qubit" if kind == "Type0A" else "pair",
        parameters=TYPE2C_PARAMS if kind == "Type2C" else PARAMS,
        legend=TYPE2C_LEGEND if kind == "Type2C" else LEGEND,
    )


CHECKS: dict[str, CheckDefinition] = {
    kind: _define(kind, description)
    for kind, description in [
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
}


def resolve_params(kind: str, overrides: Mapping[str, float] | None = None) -> dict[str, float]:
    """Merge parameter overrides with the defaults of ``kind``.

    Raises:
        KeyError: If ``kind`` is not a registered check.
        ValueError: If an override names an unknown parameter or is out of range.
    """
    definition = CHECKS[kind]
    params = {name: float(p.default) for name, p in definition.parameters.items()}
    for name, value in (overrides or {}).items():
        spec = definition.parameters.get(name)
        if spec is None:
            known = ", ".join(definition.parameters)
            raise ValueError(f"Unknown parameter '{name}' for {kind}; expected one of: {known}")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"Parameter '{name}' must be finite")
        if spec.min is not None and number < spec.min:
            raise ValueError(f"Parameter '{name}' must be >= {spec.min:g}")
        params[name] = number
    return params


# ---------------------------------------------------------------------------
# Topology and data context
# ---------------------------------------------------------------------------


def qid(value: str | int) -> str:
    """Normalize a qubit ID such as ``"Q05"`` or ``5`` to ``"5"``."""
    text = str(value).removeprefix("Q")
    if not text.isdecimal():
        raise ValueError(f"Invalid qubit ID: {value}")
    return str(int(text))


@dataclass(frozen=True)
class QubitPair:
    """A directed qubit pair at coupling-graph distance ``hops``."""

    source: str
    target: str
    hops: int


class CollisionTopology:
    """Neighbour, pair and MUX queries over a chip topology."""

    def __init__(
        self,
        qubits: Iterable[str | int],
        couplings: Iterable[Sequence[str | int]],
        muxes: Mapping[Any, Iterable[str | int]] | None = None,
    ) -> None:
        self.qubits: list[str] = sorted({qid(q) for q in qubits}, key=int)
        self.couplings: list[tuple[str, str]] = [(qid(c[0]), qid(c[1])) for c in couplings]
        self.muxes: dict[str, list[str]] = {
            str(mux_id): [qid(m) for m in members] for mux_id, members in (muxes or {}).items()
        }
        adjacency: dict[str, set[str]] = {}
        for a, b in self.couplings:
            adjacency.setdefault(a, set()).add(b)
            adjacency.setdefault(b, set()).add(a)
        self._neighbors = {k: sorted(v, key=int) for k, v in adjacency.items()}
        self._mux_of = {member: mux for mux, members in self.muxes.items() for member in members}
        self._pairs = self._build_pairs()

    @classmethod
    def from_definition(cls, definition: TopologyDefinition) -> CollisionTopology:
        """Build from a QDash topology template."""
        return cls(
            qubits=definition.qubits.keys(),
            couplings=definition.couplings,
            muxes=definition.muxes,
        )

    def neighbors(self, target: str | int) -> list[str]:
        """Coupled qubits of ``target`` in numeric order."""
        return list(self._neighbors.get(qid(target), []))

    def _build_pairs(self) -> list[QubitPair]:
        positions = set(self.qubits)
        adjacency = {
            key: set(self._neighbors.get(key, [])) & positions - {key} for key in self.qubits
        }
        result: list[QubitPair] = []
        for source in self.qubits:
            first = adjacency[source]
            second: set[str] = set().union(*(adjacency[mid] for mid in first)) - first - {source}
            for hops, targets in ((1, first), (2, second)):
                result.extend(QubitPair(source, t, hops) for t in sorted(targets, key=int))
        return result

    def pairs(self, hops: Iterable[int] = (1, 2)) -> list[QubitPair]:
        """Directed pairs (both directions) at the requested distances."""
        allowed = set(hops)
        return [p for p in self._pairs if p.hops in allowed]

    def same_mux(self, a: str | int, b: str | int) -> bool:
        """Whether both qubits are members of the same MUX."""
        mux = self._mux_of.get(qid(a))
        return mux is not None and mux == self._mux_of.get(qid(b))


Measurement = tuple[float | None, str]


@dataclass
class CollisionContext:
    """Inputs for collision checks.

    Attributes:
        topology: Chip topology.
        params: Effective check parameters (see :func:`resolve_params`).
        data: ``{parameter: {qid: (value, unit)}}`` for qubit parameters.
        couplings: ``{"c-t": (value, unit)}`` measured coupling strengths.
    """

    topology: CollisionTopology
    params: dict[str, float]
    data: dict[str, dict[str, Measurement]] = field(default_factory=dict)
    couplings: dict[str, Measurement] = field(default_factory=dict)

    def value(self, key: str, target: str | int, unit: str) -> float:
        """Return a measured qubit value in ``unit``.

        Raises:
            MissingData: If the value is absent or not finite.
            ValueError: If the stored unit cannot be converted to ``unit``.
        """
        q = qid(target)
        entry = self.data.get(key, {}).get(q)
        if entry is None:
            raise MissingData(f"No {key} for Q{q}")
        raw, raw_unit = entry
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
            raise MissingData(f"No finite {key} for Q{q}")
        return convert_unit(float(raw), raw_unit, unit)

    def coupling_strength(self, source: str | int, target: str | int) -> float | None:
        """Measured coupling strength in GHz, looked up in both directions."""
        s, t = qid(source), qid(target)
        for pair in (f"{s}-{t}", f"{t}-{s}"):
            entry = self.couplings.get(pair)
            if entry is None:
                continue
            raw, raw_unit = entry
            if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
                continue
            return convert_unit(float(raw), raw_unit, "GHz")
        return None


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


class Assessment(TypedDict):
    """Detail of a cell: summary label, ``(label, value)`` checks and notes."""

    label: str
    checks: list[tuple[str, float]]
    estimates: list[str]


@dataclass(frozen=True)
class CellResult:
    """Result of one check for one target."""

    value: float | None
    color: str
    assessment: Assessment


@dataclass(frozen=True)
class CollisionCell:
    """A :class:`CellResult` together with its target."""

    target: str | QubitPair
    result: CellResult

    @property
    def key(self) -> str:
        if isinstance(self.target, QubitPair):
            return f"{self.target.source}-{self.target.target}"
        return f"Q{self.target}"


class Inputs:
    """Reads check inputs and records the defaults and estimates used."""

    def __init__(self, ctx: CollisionContext) -> None:
        self.ctx = ctx
        self.notes: list[str] = []
        self.p = ctx.params

    def read(
        self,
        key: str,
        q: str,
        unit: str,
        default: float | None = None,
        note: str | None = None,
    ) -> float:
        try:
            return self.ctx.value(key, q, unit)
        except (MissingData, KeyError):
            if default is None:
                raise MissingData(f"{key}[Q{q}] is missing") from None
            self.notes.append(note or f"Default {key}[Q{q}]: {default:g} {unit}")
            return default

    def f(self, q: str) -> float:
        return self.read("qubit_frequency", q, "GHz")

    def a(self, q: str) -> float:
        f = self.f(q)
        return self.read(
            "qubit_anharmonicity",
            q,
            "GHz",
            -f / 19,
            f"Estimated qubit_anharmonicity[Q{q}]: {-f / 19:g} GHz "
            f"(fallback approximation α = −fGE/19; fGE = {f:g} GHz)",
        )

    def g(self, c: str, t: str) -> float:
        value = self.ctx.coupling_strength(c, t)
        if value is not None:
            return float(value)
        self.notes.append(
            f"Default coupling Q{c}–Q{t}: {self.p['default_coupling']:g} GHz "
            "(default_coupling; measured coupling unavailable)"
        )
        return self.p["default_coupling"]

    def coupling(self, c: str, t: str, hops: int) -> float:
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

    def drive(self, c: str, t: str) -> float:
        d, a = self.f(c) - self.f(t), self.a(c)
        g, time = self.g(c, t), self.p["cnot_time"]
        value = -(1 / (4 * time)) * d * (d + a) / (g * a)
        self.notes.append(
            f"Estimated CR drive Q{c}→Q{t}: {value:g} GHz "
            f"(Ωd = −Δ(Δ+α)/(4×CNOT time×g×α); Δ = {d:g} GHz, "
            f"α = {a:g} GHz, g = {g:g} GHz, CNOT time = {time:g} ns)"
        )
        return value


def same_mux(ctx: CollisionContext, a: str, b: str) -> bool:
    """Whether ``a`` and ``b`` share a MUX on the context's topology."""
    return ctx.topology.same_mux(a, b)


def _dedupe(notes: list[str]) -> list[str]:
    return list(dict.fromkeys(notes))


def _type2c(x: Inputs, ctx: CollisionContext, c: str, t: str) -> CellResult:
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
            "estimates": _dedupe(
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


def evaluate(kind: str, target: str | QubitPair, ctx: CollisionContext) -> CellResult | None:
    """Evaluate one check for a qubit (Type0A) or a directed pair.

    Returns ``None`` when the target is outside the check's scope (for example a
    hops-2 pair for a check other than Type1A/Type3A, or across MUXes).
    Missing data and singular formulas produce a grey "Not evaluated" cell.

    Raises:
        KeyError: If ``kind`` is not a registered check.
    """
    if kind not in CHECKS:
        raise KeyError(kind)
    x = Inputs(ctx)
    params = ctx.params
    checks: list[tuple[str, float]] = []
    try:
        if kind == "Type0A":
            if isinstance(target, QubitPair):
                raise TypeError("Type0A evaluates a qubit, not a pair")
            q = qid(target)
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
            if not isinstance(target, QubitPair):
                raise TypeError(f"{kind} evaluates a pair, not a qubit")
            c, t, h = qid(target.source), qid(target.target), target.hops
            if h == 2 and (kind not in ("Type1A", "Type3A") or not same_mux(ctx, c, t)):
                return None
            if kind == "Type2C":
                return _type2c(x, ctx, c, t)
            d, a = x.f(c) - x.f(t), x.a(c)
            limit = params["adiabatic_limit"]
            topology = ctx.topology

            def add(label: str, value: float, threshold: float = limit) -> None:
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
                "estimates": _dedupe(x.notes),
            },
        )
    except (MissingData, ZeroDivisionError, ValueError, OverflowError) as exc:
        return CellResult(
            None,
            color=GRAY,
            assessment={
                "label": f"Not evaluated: {exc}",
                "checks": checks,
                "estimates": _dedupe(x.notes),
            },
        )


def evaluate_check(
    kind: str,
    ctx: CollisionContext,
    hops: Iterable[int] = (1, 2),
) -> list[CollisionCell]:
    """Evaluate ``kind`` for every qubit or directed pair of the topology.

    Pairs outside the check's scope are omitted.

    Raises:
        KeyError: If ``kind`` is not a registered check.
    """
    definition = CHECKS[kind]
    targets: list[str | QubitPair]
    if definition.target == "qubit":
        targets = list(ctx.topology.qubits)
    else:
        targets = list(ctx.topology.pairs(hops))
    cells: list[CollisionCell] = []
    for target in targets:
        result = evaluate(kind, target, ctx)
        if result is not None:
            cells.append(CollisionCell(target=target, result=result))
    return cells
