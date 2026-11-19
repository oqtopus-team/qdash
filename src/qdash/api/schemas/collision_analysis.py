"""Schemas for frequency collision analysis endpoints."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CollisionParameterInfo(BaseModel):
    """An adjustable numeric input of a collision check."""

    name: str
    default: float
    min: float | None = None
    unit: str = Field(default="", description="Display unit; values are not converted")
    label: str


class LegendEntry(BaseModel):
    """Meaning of one cell color."""

    color: str
    label: str


class CollisionCheckInfo(BaseModel):
    """Catalog entry of one collision check."""

    kind: str = Field(..., description="Check identifier, e.g. 'Type1A'")
    title: str = Field(..., description="e.g. 'Type0A — Qubit quality'")
    description: str
    target: Literal["qubit", "pair"]
    unit: str = Field(..., description="'dimensionless' (threshold ratio) or 'MHz' (Type2C)")
    parameters: list[CollisionParameterInfo]
    legend: list[LegendEntry]


class ListCollisionChecksResponse(BaseModel):
    """All collision checks in catalog order."""

    checks: list[CollisionCheckInfo]


class CollisionEvaluateRequest(BaseModel):
    """Body for evaluating one collision check on a chip."""

    check: str = Field(..., description="Check identifier from the catalog")
    params: dict[str, float] = Field(
        default_factory=dict, description="Overrides of the check's parameter defaults"
    )
    hops: list[int] = Field(
        default_factory=lambda: [1, 2], description="Pair distances to evaluate (subset of 1, 2)"
    )


class CollisionCheckItem(BaseModel):
    """One sub-check contributing to a cell's score."""

    label: str
    value: float | None = Field(..., description="Ratio to the limit, or null if not finite")


class CollisionCellResponse(BaseModel):
    """Result of a check for one qubit or one directed pair."""

    key: str = Field(..., description="'Q5' for a qubit, '5-6' for a directed pair")
    qid: str | None = Field(default=None, description="Qubit ID for qubit checks")
    source: str | None = Field(default=None, description="Control qubit of a pair")
    target: str | None = Field(default=None, description="Target qubit of a pair")
    hops: int | None = Field(default=None, description="Coupling-graph distance of a pair")
    value: float | None = Field(..., description="Score or detuning; null when not evaluated")
    color: str
    label: str
    checks: list[CollisionCheckItem]
    estimates: list[str] = Field(..., description="Defaults and approximations used")


class CollisionEvaluateResponse(BaseModel):
    """Cells of one collision check over a chip."""

    chip_id: str
    check: str
    title: str
    description: str
    target: Literal["qubit", "pair"]
    unit: str
    legend: list[LegendEntry]
    parameters: dict[str, float] = Field(..., description="Effective parameter values used")
    cells: list[CollisionCellResponse]
    evaluated_at: datetime
