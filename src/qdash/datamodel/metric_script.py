"""Shared models for metric scripts and their evaluation results."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MetricScriptVisibility = Literal["private", "project"]
MetricScriptStatus = Literal["valid", "invalid"]
MetricTarget = Literal["qubit", "pair"]
MetricResultKind = Literal["scalar", "series"]
CellStatus = Literal["ok", "missing", "empty", "error"]
SeriesPointStatus = Literal["ok", "no_data", "insufficient"]

MAX_SERIES_TARGETS = 16
"""Most targets of one series evaluation; equals ``MAX_SERIES_TARGETS`` in the worker's SDK."""
MAX_SERIES_POINTS = 1024
"""Most points per series; equals ``MAX_SERIES_POINTS`` in the worker's SDK."""
MAX_TOTAL_SERIES_POINTS = 8192
"""Most points of one series evaluation; equals ``MAX_TOTAL_SERIES_POINTS`` in the SDK."""

MAX_PERIOD_DAYS = 400
"""Longest relative period; matches the broker's history span cap."""
DEFAULT_PERIOD_DAYS = 14


StrictRevision = Annotated[int, Field(strict=True, ge=1)]
"""A script revision number in a request: a positive integer, never a bool, string or float."""


class RelativePeriod(BaseModel):
    """The last ``days`` days, resolved to ``[now - days, now]`` at evaluation."""

    kind: Literal["relative"] = "relative"
    days: int = Field(default=DEFAULT_PERIOD_DAYS, ge=1, le=MAX_PERIOD_DAYS)


class AbsolutePeriod(BaseModel):
    """A fixed ``[start, end]`` window; both bounds need a timezone."""

    kind: Literal["absolute"] = "absolute"
    start: datetime
    end: datetime

    @field_validator("start", "end")
    @classmethod
    def _timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("start and end must include a timezone")
        return value

    @model_validator(mode="after")
    def _order(self) -> AbsolutePeriod:
        if self.start > self.end:
            raise ValueError("start must be on or before end")
        return self


MetricPeriod = Annotated[RelativePeriod | AbsolutePeriod, Field(discriminator="kind")]


def default_period() -> RelativePeriod:
    return RelativePeriod()


def resolve_period(
    period: RelativePeriod | AbsolutePeriod, now: datetime
) -> tuple[datetime, datetime]:
    """Return the ``(start, end)`` the evaluation reads."""
    if isinstance(period, RelativePeriod):
        return now - timedelta(days=period.days), now
    return period.start, period.end


class ScriptDiagnostic(BaseModel):
    """A validation or runtime problem, located in the script when possible."""

    message: str
    line: int | None = None
    column: int | None = None
    function: str | None = None


class MetricParameterInfo(BaseModel):
    """A ``Parameter`` declared by a metric."""

    default: bool | int | float | str
    label: str = ""
    kind: Literal["integer", "number", "boolean", "choice"]
    min: float | None = None
    max: float | None = None
    step: float | None = None
    unit: str = ""
    choices: list[str] | None = None


class MetricInfo(BaseModel):
    """Catalog entry of one ``@metric`` function."""

    id: str
    title: str
    unit: str
    target: MetricTarget
    result: MetricResultKind = Field(
        default="scalar",
        description=(
            "scalar: one value per qubit or pair, shown as a map or table. series: a time "
            "series per selected target, shown as a chart"
        ),
    )
    hops: list[int] = Field(default_factory=lambda: [1, 2])
    parameters: dict[str, MetricParameterInfo] = Field(default_factory=dict)
    has_legend: bool = False


class MetricScriptRevision(BaseModel):
    """One saved source text of a script."""

    revision: int
    source: str
    created_at: datetime
    status: MetricScriptStatus
    metrics: list[MetricInfo] = Field(
        default_factory=list, description="Catalog of this revision (valid revisions only)"
    )


class ScriptPin(BaseModel):
    """Revisions of a script that one dashboard depends on.

    Stored on the script document, keyed by dashboard ID, so that the script save sees
    every pin in the same document it compares and replaces.
    """

    revisions: list[int] = Field(default_factory=list, description="Pinned revision numbers")
    shared: bool = Field(default=False, description="The dashboard is shared with the project")
    writer: str = Field(
        default="", description="Token of the dashboard write that last widened this pin"
    )


class CellReference(BaseModel):
    """An input value a cell was computed from."""

    metric: str
    target: str
    task_id: str | None = None
    execution_id: str | None = None
    timestamp: str | None = None
    value: float | None = None
    unit: str | None = None


class CellCheck(BaseModel):
    """One ``(label, value)`` row of a cell's details."""

    label: str
    value: float | str | None = None


class CellAssessment(BaseModel):
    """Details a metric attached to a cell."""

    checks: list[CellCheck] = Field(default_factory=list)
    estimates: list[str] = Field(default_factory=list)
    count: int | None = Field(default=None, description="Number of observations behind the value")


class MetricSeriesPoint(BaseModel):
    """One point of a series metric's result for one target."""

    timestamp: datetime = Field(..., description="Where the point is drawn, within the period")
    start: datetime | None = Field(default=None, description="Inclusive start of its time bin")
    end: datetime | None = Field(default=None, description="End of its time bin")
    value: float | None = Field(
        default=None, description="Value in the metric's unit; null for a gap, never joined"
    )
    count: int | None = Field(default=None, description="Observations behind the value")
    status: SeriesPointStatus = Field(
        ..., description="ok (has a value), no_data or insufficient (a gap)"
    )
    reason: str | None = Field(default=None, description="Why the point is a gap, or a note")


class MetricCell(BaseModel):
    """Result of a metric for one qubit or one directed pair.

    A series metric's cell has no ``value``; its ``series`` holds the points, and its status
    is ``missing`` when no point has a value.
    """

    key: str = Field(..., description="'5' for a qubit, '5>6' for a directed pair")
    qid: str | None = None
    source: str | None = None
    target: str | None = None
    hops: int | None = None
    status: CellStatus
    value: float | None = None
    color: str | None = None
    label: str | None = None
    message: str | None = None
    diagnostic: ScriptDiagnostic | None = None
    assessment: CellAssessment | None = None
    references: list[CellReference] = Field(default_factory=list)
    series: list[MetricSeriesPoint] | None = Field(
        default=None, description="Series metrics only: the points, oldest first"
    )
    references_truncated: bool = Field(
        default=False,
        description="Series metrics only: references holds the most recent inputs, not all",
    )


class LegendItem(BaseModel):
    """Categorical legend entry."""

    color: str
    label: str


class LegendStop(BaseModel):
    """Continuous color-scale stop in the metric's unit."""

    value: float
    color: str


class MetricLegend(BaseModel):
    """Legend declared by a metric."""

    kind: Literal["categorical", "continuous"]
    items: list[LegendItem] = Field(default_factory=list)
    stops: list[LegendStop] = Field(default_factory=list)


def parameter_values(params: dict[str, Any]) -> dict[str, bool | int | float | str]:
    """Narrow a parameter mapping to JSON scalar values."""
    return {
        key: value for key, value in params.items() if isinstance(value, (bool, int, float, str))
    }


def normalize_target_key(value: str, target: MetricTarget | None = None) -> str:
    """Normalize a selected target to its cell key: ``"5"`` for a qubit, ``"5>6"`` for a pair.

    Qubits accept ``"Q05"``, ``"05"`` and ``"5"``; pairs accept ``"0>1"`` and ``"0-1"`` and keep
    their direction. ``target`` restricts the kind; ``None`` accepts either.

    Raises:
        ValueError: If the value is not a qubit ID or directed pair of the requested kind.
    """

    def qubit(text: str) -> str:
        digits = text.strip().removeprefix("Q")
        if not digits.isdecimal():
            raise ValueError(f"Invalid target {value!r}")
        return str(int(digits))

    if not isinstance(value, str):
        raise ValueError(f"Invalid target {value!r}")
    ends = value.replace(">", "-").split("-")
    if len(ends) == 2:
        if target == "qubit":
            raise ValueError(f"Target {value!r} is a pair; this metric takes qubit IDs")
        return f"{qubit(ends[0])}>{qubit(ends[1])}"
    if len(ends) == 1:
        if target == "pair":
            raise ValueError(f"Target {value!r} is a qubit; write a directed pair such as '0>1'")
        return qubit(ends[0])
    raise ValueError(f"Invalid target {value!r}")
