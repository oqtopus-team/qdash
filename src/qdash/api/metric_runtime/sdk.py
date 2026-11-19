"""The ``qdash_metrics`` public API for metric scripts.

Scripts import from ``qdash_metrics`` only; the worker registers a module of that name whose
attributes are the names in :data:`PUBLIC_NAMES`. The API follows qdash-playground
(https://github.com/msk-ono/qdash-playground, Apache License 2.0), with these intentional
differences:

- The module is named ``qdash_metrics``.
- ``@metric`` accepts ``hops``: the pair distances a pair metric is evaluated for.
- ``CellResult.assessment`` may carry ``count`` (the sample count behind the value).
- Coupling metrics are read through ``ctx.data[name][pair]`` with a directed coupling ID
  (``"0-1"`` or a :class:`QubitPair`); there is no reverse-direction fallback.
  ``ctx.coupling_strength`` is the one deliberate undirected lookup.
- There is no ``ctx.api``: scripts have no network or API access. All data comes from the
  data broker in the API process.
- ``history()`` reads the explicit period ``[ctx.start, ctx.end]`` on the server instead of
  approximating it with ``within_days``. Explicit ``start``/``end`` arguments are still capped
  by the broker.

The data accessors call a *broker function* ``broker(op, args) -> data`` that the worker
connects to the parent process. Unit tests can pass any callable with that signature.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Literal

import pint

units: Any = pint.UnitRegistry()
"""Shared pint unit registry; use ``units.us`` or ``Quantity(value, unit)``."""
units.define("arbitrary_unit = [arbitrary] = au")
Quantity = units.Quantity
"""Quantity class bound to :data:`units`."""

BrokerFunction = Callable[[str, dict[str, Any]], Any]
"""``broker(op, args)`` returns the answer data or raises :class:`BrokerError`."""

MetricTarget = Literal["qubit", "pair"]
ALLOWED_HOPS = frozenset({1, 2})


class MissingData(ValueError):
    """A measured value required by a metric is not available in the period.

    Raising it marks the cell as missing. Return ``None`` instead to leave a target
    deliberately unevaluated.
    """


class BrokerError(RuntimeError):
    """The data broker refused or failed a request (for example a cap was exceeded)."""


# ---------------------------------------------------------------------------
# Identifiers, timestamps and units
# ---------------------------------------------------------------------------


def timestamp(value: str | datetime) -> datetime:
    """Parse an ISO 8601 string or datetime with a timezone and return it in UTC.

    Raises:
        ValueError: If the value has no timezone or cannot be parsed.
    """
    parsed = (
        datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    )
    if not isinstance(parsed, datetime):
        raise ValueError(f"Invalid timestamp: {value!r}")
    if parsed.tzinfo is None:
        raise ValueError("Timestamps must include a timezone")
    return parsed.astimezone(UTC)


def qid(value: str | int) -> str:
    """Normalize a qubit ID such as ``"Q05"``, ``"05"`` or ``5`` to ``"5"``.

    Raises:
        ValueError: If the value is not a qubit ID.
    """
    if isinstance(value, bool):
        raise ValueError(f"Invalid qubit ID: {value}")
    text = str(value).strip().removeprefix("Q")
    if not text.isdecimal():
        raise ValueError(f"Invalid qubit ID: {value}")
    return str(int(text))


_UNIT_ALIASES = {
    "": "dimensionless",
    "%": "percent",
    "μs": "us",
    "µs": "us",
    "a.u.": "au",
    "KHz": "kHz",
}


def unit_name(value: str) -> str:
    """Normalize QDash unit labels to pint names (``%`` → ``percent``, ``μs`` → ``us``)."""
    text = value.strip()
    if text in _UNIT_ALIASES:
        return _UNIT_ALIASES[text]
    for alias, name in (("a.u.", "au"), ("μs", "us"), ("µs", "us"), ("KHz", "kHz")):
        text = text.replace(alias, name)
    return text


@dataclass(frozen=True)
class QubitPair:
    """A directed qubit pair passed to pair metrics.

    Attributes:
        source: Normalized ID of the first (control) qubit.
        target: Normalized ID of the second (target) qubit.
        hops: Coupling-graph distance, 1 or 2.

    The reverse direction is a separate pair and a separate evaluation.
    """

    source: str
    target: str
    hops: int


def coupling_id(value: str | QubitPair) -> str:
    """Normalize a directed coupling ID (``"Q00-Q01"`` → ``"0-1"``)."""
    if isinstance(value, QubitPair):
        return f"{qid(value.source)}-{qid(value.target)}"
    if not isinstance(value, str):
        raise ValueError(f"Invalid coupling ID: {value!r}")
    ends = value.split("-")
    if len(ends) != 2:
        raise ValueError(f"Invalid coupling ID: {value!r}; use 'source-target'")
    return f"{qid(ends[0])}-{qid(ends[1])}"


# ---------------------------------------------------------------------------
# Presentation (ported from qdash-playground presentation.py)
# ---------------------------------------------------------------------------


def color(value: str) -> str:
    """Validate a ``#RGB`` or ``#RRGGBB`` color and return it as ``#RRGGBB``."""
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?", value):
        raise ValueError("Colors must be #RGB or #RRGGBB")
    return "#" + "".join(c * 2 for c in value[1:]) if len(value) == 4 else value


@dataclass(frozen=True)
class Parameter:
    """An input of a metric that each dashboard panel can adjust.

    Attributes:
        default: Required default: an int, float, bool, or a string from ``choices``.
        label: Input label.
        min: Inclusive numeric lower bound, or ``None``.
        max: Inclusive numeric upper bound, or ``None``.
        step: Positive input step; values are not rounded to it.
        unit: Unit label shown next to the input; values are not converted.
        choices: Allowed strings; requires a default from the list.

    Raises:
        ValueError: If the default, bounds, step or choices are invalid.
    """

    default: float | int | str | bool
    label: str = ""
    min: float | None = None
    max: float | None = None
    step: float | None = None
    unit: str = ""
    choices: tuple[str, ...] | list[str] | None = None

    def __post_init__(self) -> None:
        if self.choices is not None:
            object.__setattr__(self, "choices", tuple(self.choices))
            if not self.choices or any(not isinstance(v, str) for v in self.choices):
                raise ValueError("Choices must contain strings")
        for bound in (self.min, self.max, self.step):
            if bound is not None and (
                isinstance(bound, bool)
                or not isinstance(bound, (int, float))
                or not math.isfinite(bound)
            ):
                raise ValueError("Parameter bounds must be finite numbers")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("Parameter minimum exceeds maximum")
        if self.step is not None and self.step <= 0:
            raise ValueError("Parameter step must be positive")
        if not isinstance(self.label, str) or not isinstance(self.unit, str):
            raise ValueError("Parameter label and unit must be strings")
        self.validate(self.default)

    @property
    def kind(self) -> str:
        """Input kind: ``integer``, ``number``, ``boolean`` or ``choice``."""
        if self.choices is not None:
            return "choice"
        return {bool: "boolean", int: "integer", float: "number"}.get(type(self.default), "invalid")

    def validate(self, value: Any) -> Any:
        """Check type, finiteness, range and choices; return integers as ``int``.

        Raises:
            ValueError: If the value does not match the declaration.
        """
        if self.kind == "choice":
            valid = isinstance(value, str) and value in (self.choices or ())
        elif self.kind == "boolean":
            valid = type(value) is bool
        else:
            valid = type(value) in (int, float) and math.isfinite(value)
            if self.kind == "integer":
                valid = valid and float(value).is_integer()
            if self.kind == "invalid":
                valid = False
            if valid:
                valid = (self.min is None or value >= self.min) and (
                    self.max is None or value <= self.max
                )
        if not valid:
            raise ValueError(f"Invalid {self.kind} parameter value: {value!r}")
        return int(value) if self.kind == "integer" else value

    def metadata(self) -> dict[str, Any]:
        """Default, kind and constraints for building an input form."""
        return {
            "default": self.default,
            "label": self.label,
            "kind": self.kind,
            "min": self.min,
            "max": self.max,
            "step": self.step,
            "unit": self.unit,
            "choices": list(self.choices) if self.choices is not None else None,
        }

    @classmethod
    def from_metadata(cls, data: Mapping[str, Any]) -> Parameter:
        """Rebuild a parameter from :meth:`metadata` output (used by the API process)."""
        default = data.get("default")
        if data.get("kind") == "number" and type(default) is int:
            # JSON round trips may turn 3.0 into 3; keep the declared kind.
            default = float(default)
        return cls(
            default=default,  # type: ignore[arg-type]
            label=str(data.get("label") or ""),
            min=data.get("min"),
            max=data.get("max"),
            step=data.get("step"),
            unit=str(data.get("unit") or ""),
            choices=data.get("choices"),
        )


def resolve_parameters(
    parameters: Mapping[str, Parameter], overrides: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Merge overrides with defaults and validate every value.

    Raises:
        ValueError: If an override names an unknown parameter or has an invalid value.
    """
    supplied = dict(overrides or {})
    unknown = sorted(supplied.keys() - parameters.keys())
    if unknown:
        known = ", ".join(parameters) or "none"
        raise ValueError(f"Unknown parameters: {', '.join(unknown)}; expected one of: {known}")
    effective: dict[str, Any] = {}
    for key, parameter in parameters.items():
        value = supplied.get(key, parameter.default)
        if parameter.kind == "number" and type(value) is int:
            value = float(value)
        try:
            effective[key] = parameter.validate(value)
        except ValueError as exc:
            raise ValueError(f"Parameter {key}: {exc}") from exc
    return effective


@dataclass(frozen=True)
class CellResult:
    """A metric value with an optional color and details.

    Attributes:
        value: A number in the declared unit, a pint Quantity, or ``None``.
        color: ``#RGB`` or ``#RRGGBB``; the renderer picks a color when omitted.
        assessment: Details shown for the cell. Optional keys: ``label`` (str),
            ``checks`` (list of ``(label, value)``), ``estimates`` (list of str) and
            ``count`` (int sample count). A ``None`` value with an assessment is shown
            as missing together with its explanation.
    """

    value: Any
    color: str | None = None
    assessment: dict[str, Any] | None = None


@dataclass(frozen=True)
class Legend:
    """Explains cell colors. Build it with :meth:`categorical` or :meth:`continuous`.

    A categorical legend does not assign colors; set them with ``CellResult.color``. A
    continuous legend is a color scale the renderer interpolates over the value.

    Raises:
        ValueError: If the kind, entries, colors or stop order are invalid.
    """

    kind: Literal["categorical", "continuous"]
    entries: tuple[tuple[Any, ...], ...]

    def __post_init__(self) -> None:
        if self.kind not in ("categorical", "continuous") or not self.entries:
            raise ValueError("Invalid legend")
        previous = -math.inf
        for entry in self.entries:
            if len(entry) != 2:
                raise ValueError("Legend entries must have two items")
            if self.kind == "categorical":
                color(entry[0])
                if not isinstance(entry[1], str):
                    raise ValueError("Legend labels must be strings")
            else:
                if (
                    type(entry[0]) not in (int, float)
                    or not math.isfinite(entry[0])
                    or entry[0] <= previous
                ):
                    raise ValueError("Color stops must be finite and strictly increasing")
                previous = entry[0]
                color(entry[1])
        if self.kind == "continuous" and len(self.entries) < 2:
            raise ValueError("A continuous legend needs at least two stops")

    @classmethod
    def categorical(cls, items: list[tuple[str, str]]) -> Legend:
        """Build a categorical legend from non-empty ``(color, label)`` items."""
        return cls("categorical", tuple(tuple(item) for item in items))

    @classmethod
    def continuous(cls, stops: list[tuple[float, str]]) -> Legend:
        """Build a color scale from at least two ``(value, color)`` stops.

        Values are finite, strictly increasing and in the metric's declared unit.
        """
        return cls("continuous", tuple(tuple(stop) for stop in stops))

    def serialize(self, declared: str, output: str) -> dict[str, Any]:
        """Return the legend for display, converting continuous stops to ``output``."""
        if self.kind == "categorical":
            return {
                "kind": self.kind,
                "items": [{"color": color(c), "label": label} for c, label in self.entries],
                "stops": [],
            }
        stops = []
        previous = -math.inf
        for value, shade in self.entries:
            converted = float(Quantity(value, unit_name(declared)).to(unit_name(output)).magnitude)
            if not math.isfinite(converted) or converted <= previous:
                raise ValueError("Converted legend stops must be finite and strictly increasing")
            previous = converted
            stops.append({"value": converted, "color": color(shade)})
        return {"kind": self.kind, "items": [], "stops": stops}


# ---------------------------------------------------------------------------
# Topology and data access
# ---------------------------------------------------------------------------


class Topology:
    """Positions, couplings and MUXes of the evaluated chip.

    Attributes:
        raw: ``{"qubits": {qid: {"row", "col"}}, "couplings": [[a, b], ...], "muxes": {...}}``.
        positions: Normalized qubit ID → ``(row, col)``.
    """

    def __init__(self, raw: dict[str, Any]) -> None:
        self.raw = raw
        self.positions: dict[str, tuple[int, int]] = {
            qid(key): (int(value["row"]), int(value["col"]))
            for key, value in raw.get("qubits", {}).items()
        }
        self._at = {position: key for key, position in self.positions.items()}
        if len(self._at) != len(self.positions):
            raise ValueError("Topology has duplicate qubit coordinates")
        adjacency: dict[str, set[str]] = {}
        for a, b in raw.get("couplings", []):
            first, second = qid(a), qid(b)
            adjacency.setdefault(first, set()).add(second)
            adjacency.setdefault(second, set()).add(first)
        self._neighbors = {key: sorted(values, key=int) for key, values in adjacency.items()}

    @property
    def qubits(self) -> list[str]:
        """Qubit IDs in numeric order."""
        return sorted(self.positions, key=int)

    def neighbors(self, target: str | int) -> list[str]:
        """Coupled qubits of ``target`` in numeric order (whole chip)."""
        return list(self._neighbors.get(qid(target), []))

    def pairs(self, hops: Iterable[int] = (1, 2)) -> list[QubitPair]:
        """Directed pairs in both directions at the requested distances (1 and/or 2)."""
        allowed = set(hops)
        positions = set(self.positions)
        adjacency = {
            key: set(self._neighbors.get(key, [])) & positions - {key} for key in self.qubits
        }
        result: list[QubitPair] = []
        for source in self.qubits:
            first = adjacency[source]
            second: set[str] = set().union(*(adjacency[mid] for mid in first)) - first - {source}
            for distance, targets in ((1, first), (2, second)):
                if distance in allowed:
                    result.extend(
                        QubitPair(source, target, distance) for target in sorted(targets, key=int)
                    )
        return result

    def offset(self, target: str | int, *, row: int = 0, col: int = 0) -> str | None:
        """ID of the qubit ``row``/``col`` steps away on the grid, or ``None``.

        Raises:
            KeyError: If ``target`` is not on the chip.
        """
        r, c = self.positions[qid(target)]
        return self._at.get((r + row, c + col))


@dataclass(frozen=True)
class Measurement:
    """One raw observation (one task result) from :meth:`MetricSeries.history`.

    Attributes:
        value: Pint Quantity.
        timestamp: Task start time in UTC.
        task_id: Task identifier, if known.
        execution_id: Execution identifier, if known.
        excluded: Whether the result was excluded from calibration statistics.
        raw: The record as sent by the broker.
    """

    value: Any
    timestamp: datetime
    task_id: str | None
    execution_id: str | None
    excluded: bool
    raw: dict[str, Any] = field(repr=False)


class AnalysisContext:
    """The ``ctx`` passed to metric functions.

    Attributes:
        chip_id: Evaluated chip.
        start: Period start (UTC).
        end: Period end (UTC).
        params: Effective parameter values (read-only mapping).
        data: ``data[metric_name][target]`` reads latest values and history.
        references: Input provenance recorded for the current cell.
    """

    def __init__(
        self,
        broker: BrokerFunction,
        chip_id: str,
        start: datetime,
        end: datetime,
        params: Mapping[str, Any] | None = None,
    ) -> None:
        if start > end:
            raise ValueError("Start must be before end")
        self._broker = broker
        self.chip_id, self.start, self.end = chip_id, start, end
        self.params: MappingProxyType[str, Any] = MappingProxyType(dict(params or {}))
        self._cache: dict[str, Any] = {}
        self.references: list[dict[str, Any]] = []
        self.data = MetricStore(self)
        self.notices: list[str] = []

    def _call(self, op: str, **args: Any) -> Any:
        return self._broker(op, args)

    @property
    def catalog(self) -> dict[str, dict[str, Any]]:
        """``{"qubit_metrics": {...}, "coupling_metrics": {...}}`` with title/unit/scale."""
        if "catalog" not in self._cache:
            self._cache["catalog"] = self._call("metrics_config")
        return self._cache["catalog"]  # type: ignore[no-any-return]

    @property
    def config(self) -> dict[str, Any]:
        """Qubit metric catalog entries (playground compatibility)."""
        return self.catalog.get("qubit_metrics", {})

    @property
    def topology(self) -> Topology:
        """Topology of the evaluated chip."""
        if "topology" not in self._cache:
            self._cache["topology"] = Topology(self._call("topology"))
        return self._cache["topology"]  # type: ignore[no-any-return]

    def _latest(self, kind: str, metric: str) -> dict[str, Any]:
        key = f"latest:{kind}:{metric}"
        if key not in self._cache:
            self._cache[key] = self._call("latest", kind=kind, metric=metric)
        return self._cache[key]  # type: ignore[no-any-return]

    def metric_kind(self, metric: str) -> str:
        """``"qubit"`` or ``"coupling"`` for a catalog metric.

        Raises:
            KeyError: If the metric is not in the QDash metrics catalog.
        """
        if metric in self.catalog.get("qubit_metrics", {}):
            return "qubit"
        if metric in self.catalog.get("coupling_metrics", {}):
            return "coupling"
        raise KeyError(
            f"Unknown metric '{metric}'; scripts read the QDash metrics catalog "
            "(qubit_metrics and coupling_metrics in config/domain/metrics.yaml, "
            "listed by GET /metric-scripts/catalog)"
        )

    def coupling_strength(self, source: str | int, target: str | int) -> Any:
        """Measured coupling strength as a Quantity, or ``None``.

        Both directions are tried; this is the one deliberate undirected lookup.
        """
        metric = "qubit_qubit_coupling_strength"
        config = self.catalog.get("coupling_metrics", {}).get(metric)
        if not config:
            return None
        records = self._latest("coupling", metric)
        s, t = qid(source), qid(target)
        for pair in (f"{s}-{t}", f"{t}-{s}"):
            raw = records.get(pair)
            value = raw.get("value") if raw else None
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                continue
            quantity = Quantity(value * config.get("scale", 1), unit_name(config["unit"]))
            self.record(
                metric,
                pair,
                task_id=raw.get("task_id") if raw else None,
                execution_id=raw.get("execution_id") if raw else None,
                timestamp=None,
                value=float(quantity.magnitude),
                unit=str(quantity.units),
            )
            return quantity
        return None

    def record(self, metric: str, target: str, **details: Any) -> None:
        """Add an input reference for the current cell; identical references are kept once."""
        reference = {"metric": metric, "target": target, **details}
        if reference not in self.references:
            self.references.append(reference)


class MetricStore:
    """``ctx.data``: select a catalog metric by name."""

    def __init__(self, ctx: AnalysisContext) -> None:
        self.ctx = ctx

    def __getitem__(self, metric: str) -> MetricTargets:
        """Return the target selector of ``metric``; unknown names raise ``KeyError``."""
        return MetricTargets(self.ctx, metric, self.ctx.metric_kind(metric))

    def __contains__(self, metric: object) -> bool:
        try:
            self.ctx.metric_kind(str(metric))
        except KeyError:
            return False
        return True


class MetricTargets:
    """``ctx.data[metric_name]``: select a qubit or a directed coupling."""

    def __init__(self, ctx: AnalysisContext, metric: str, kind: str) -> None:
        self.ctx, self.metric, self.kind = ctx, metric, kind

    def __getitem__(self, target: str | int | QubitPair) -> MetricSeries:
        """Normalize ``target`` and return its series.

        Qubit metrics take a qubit ID (``0``, ``"0"`` and ``"Q00"`` are the same target).
        Coupling metrics take ``"0-1"`` or a :class:`QubitPair`; the direction matters.
        """
        if self.kind == "qubit":
            if isinstance(target, QubitPair):
                raise TypeError(
                    f"{self.metric} is a qubit metric; index it with a qubit ID, "
                    "for example pair.source"
                )
            return MetricSeries(self.ctx, self.metric, self.kind, qid(target))
        if isinstance(target, int):
            raise TypeError(f"{self.metric} is a coupling metric; index it with 'a-b' or a pair")
        return MetricSeries(self.ctx, self.metric, self.kind, coupling_id(target))


class MetricSeries:
    """``ctx.data[metric_name][target]``: latest value and history of one target.

    Units and the catalog scale are applied here; do not apply the scale again.
    """

    def __init__(self, ctx: AnalysisContext, metric: str, kind: str, target: str) -> None:
        self.ctx, self.metric, self.kind, self.target = ctx, metric, kind, target

    @property
    def _label(self) -> str:
        return f"Q{self.target}" if self.kind == "qubit" else self.target

    def _config(self) -> dict[str, Any]:
        section = "qubit_metrics" if self.kind == "qubit" else "coupling_metrics"
        return self.ctx.catalog[section][self.metric]  # type: ignore[no-any-return]

    def _finite(self, value: Any) -> float:
        if (
            isinstance(value, bool)
            or not isinstance(value, (float, int))
            or not math.isfinite(value)
        ):
            raise MissingData(f"No finite {self.metric} for {self._label}")
        return float(value)

    def _catalog_quantity(self, value: float) -> Any:
        config = self._config()
        return Quantity(value * config.get("scale", 1), unit_name(config["unit"]))

    def _record_quantity(self, value: float, native_unit: Any) -> Any:
        """Use the record's own unit when it is a physical unit compatible with the catalog.

        Records with no unit, ``a.u.`` or an incompatible unit hold raw catalog values
        (for example fidelities stored as 0.99 ``a.u.``), so the catalog scale applies.
        """
        catalog = self._catalog_quantity(value)
        if not isinstance(native_unit, str) or not native_unit.strip():
            return catalog
        try:
            native = Quantity(value, unit_name(native_unit))
        except Exception:
            return catalog
        if native.dimensionless or "[arbitrary]" in str(native.dimensionality):
            return catalog
        if native.dimensionality != catalog.dimensionality:
            return catalog
        return native

    def latest(self) -> Any:
        """Latest accepted value within the period as a Quantity.

        Completed, not excluded results only; the catalog unit and scale are applied.
        There is no fallback to values outside the period.

        Raises:
            MissingData: If the period holds no value for this target.
        """
        raw = self.ctx._latest(self.kind, self.metric).get(self.target)
        if not raw:
            raise MissingData(f"No {self.metric} for {self._label} in this period")
        quantity = self._catalog_quantity(self._finite(raw.get("value")))
        self.ctx.record(
            self.metric,
            self.target,
            task_id=raw.get("task_id"),
            execution_id=raw.get("execution_id"),
            timestamp=None,
            value=float(quantity.magnitude),
            unit=str(quantity.units),
        )
        return quantity

    def history(
        self,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        include_excluded: bool = False,
    ) -> list[Measurement]:
        """Raw observations within ``[start, end]`` (inclusive), oldest first.

        Args:
            start: Lower bound; defaults to ``ctx.start``. Needs a timezone.
            end: Upper bound; defaults to ``ctx.end``. Needs a timezone.
            include_excluded: Also return results excluded from statistics.

        Returns:
            One :class:`Measurement` per task result. Non-finite values are skipped.

        Raises:
            ValueError: If a bound has no timezone or ``start`` is after ``end``.
            BrokerError: If the request exceeds a broker cap.
        """
        lower = timestamp(start) if start is not None else self.ctx.start
        upper = timestamp(end) if end is not None else self.ctx.end
        if lower > upper:
            raise ValueError("Start must be before end")
        key = f"history:{self.kind}:{self.metric}:{self.target}:{lower.isoformat()}:{upper.isoformat()}"
        if key not in self.ctx._cache:
            answer = self.ctx._call(
                "history",
                kind=self.kind,
                metric=self.metric,
                target=self.target,
                start=lower.isoformat(),
                end=upper.isoformat(),
            )
            if answer.get("clamped"):
                notice = (
                    f"history({self.metric}) span was clamped to {answer.get('start')} .. "
                    f"{answer.get('end')}"
                )
                if notice not in self.ctx.notices:
                    self.ctx.notices.append(notice)
            self.ctx._cache[key] = answer.get("records", [])
        records: list[Measurement] = []
        for raw in self.ctx._cache[key]:
            excluded = bool(raw.get("excluded", False))
            if excluded and not include_excluded:
                continue
            try:
                quantity = self._record_quantity(self._finite(raw.get("value")), raw.get("unit"))
            except MissingData:
                continue
            observed = timestamp(raw["timestamp"])
            record = Measurement(
                quantity,
                observed,
                raw.get("task_id"),
                raw.get("execution_id"),
                excluded,
                raw,
            )
            records.append(record)
            self.ctx.record(
                self.metric,
                self.target,
                task_id=record.task_id,
                execution_id=record.execution_id,
                timestamp=observed.isoformat(),
                value=float(quantity.magnitude),
                unit=str(quantity.units),
            )
        return sorted(records, key=lambda record: record.timestamp)


# ---------------------------------------------------------------------------
# Registry (ported from qdash-playground registry.py)
# ---------------------------------------------------------------------------

LegendSpec = Legend | Callable[[AnalysisContext], Legend] | None


@dataclass
class Metric:
    """A function registered with :func:`metric`."""

    id: str
    title: str
    unit: str
    function: Callable[..., Any]
    target: MetricTarget = "qubit"
    hops: tuple[int, ...] = (1, 2)
    parameters: dict[str, Parameter] = field(default_factory=dict)
    legend: LegendSpec = None

    def metadata(self) -> dict[str, Any]:
        """Catalog entry stored with a script revision."""
        return {
            "id": self.id,
            "title": self.title,
            "unit": self.unit,
            "target": self.target,
            "hops": list(self.hops),
            "parameters": {key: value.metadata() for key, value in self.parameters.items()},
            "has_legend": self.legend is not None,
        }


def metric(
    *,
    title: str,
    unit: str,
    target: str = "qubit",
    hops: Iterable[int] = (1, 2),
    parameters: dict[str, Parameter] | None = None,
    legend: LegendSpec = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Expose a function ``(target, ctx)`` as a metric.

    ``target`` is a normalized qubit ID, or a :class:`QubitPair` for pair metrics. Return a
    number in ``unit``, a Quantity, ``None`` (not evaluated) or a :class:`CellResult`.

    Args:
        title: Display name; must not be empty.
        unit: Declared output unit; use ``dimensionless`` for ratios.
        target: ``qubit`` or ``pair``. Pair metrics run for both directions of every pair
            whose distance is in ``hops``, over the whole chip.
        hops: Pair distances the metric is meaningful for, a non-empty subset of ``(1, 2)``.
        parameters: Name → :class:`Parameter`; read effective values from ``ctx.params``.
        legend: A :class:`Legend`, or a function ``legend(ctx) -> Legend``.

    Raises:
        ValueError: If ``target`` or ``hops`` is invalid.
        pint.errors.UndefinedUnitError: If ``unit`` is unknown.
    """
    if target not in ("qubit", "pair"):
        raise ValueError("target must be 'qubit' or 'pair'")
    hop_values = tuple(sorted(set(hops)))
    if not hop_values or not set(hop_values) <= ALLOWED_HOPS:
        raise ValueError("hops must be a non-empty subset of (1, 2)")
    units.Unit(unit_name(unit))
    declared_target: MetricTarget = "qubit" if target == "qubit" else "pair"

    def decorate(function: Callable[..., Any]) -> Callable[..., Any]:
        function.__qdash_metric__ = Metric(  # type: ignore[attr-defined]
            function.__name__,
            title,
            unit,
            function,
            declared_target,
            hop_values,
            dict(parameters or {}),
            legend,
        )
        return function

    return decorate


SCRIPT_FILENAME = "script:metric_script.py"
"""Filename given to compiled scripts; diagnostics look for frames with this prefix."""


def load_source(source: str, filename: str = SCRIPT_FILENAME) -> dict[str, Metric]:
    """Compile a script under the import/builtin policy and collect its metrics.

    Raises:
        SyntaxError: If the script does not compile.
        ScriptPolicyError: If it imports a module outside the allowlist.
        ValueError: If no metric is defined or a declaration is invalid.
    """
    from qdash.api.metric_runtime.policy import script_builtins, validate_imports

    validate_imports(source, filename)
    namespace: dict[str, Any] = {
        "__name__": "qdash_user_metrics",
        "__file__": filename,
        "__builtins__": script_builtins(),
    }
    exec(compile(source, filename, "exec"), namespace)  # noqa: S102 - the purpose of the runtime
    definitions: dict[str, Metric] = {}
    for value in list(namespace.values()):
        definition = getattr(value, "__qdash_metric__", None)
        if not isinstance(definition, Metric):
            continue
        if definition.id in definitions and definitions[definition.id] is not definition:
            raise ValueError(f"Duplicate metric function: {definition.id}")
        if not isinstance(definition.title, str) or not definition.title.strip():
            raise ValueError("Metric titles must not be empty")
        if isinstance(definition.legend, Legend):
            definition.legend.serialize(definition.unit, definition.unit)
        elif definition.legend is not None and not callable(definition.legend):
            raise ValueError("legend must be a Legend or a function returning one")
        for key, parameter in definition.parameters.items():
            if not isinstance(key, str) or not key or not isinstance(parameter, Parameter):
                raise ValueError("Metric parameters must map names to Parameter values")
            parameter.validate(parameter.default)
        definitions[definition.id] = definition
    if not definitions:
        raise ValueError("No metrics found. Add a function decorated with @metric.")
    return definitions


PUBLIC_NAMES = (
    "CellResult",
    "Legend",
    "Measurement",
    "MissingData",
    "Parameter",
    "Quantity",
    "QubitPair",
    "metric",
    "unit_name",
    "units",
)
"""Names exported by the ``qdash_metrics`` module."""
