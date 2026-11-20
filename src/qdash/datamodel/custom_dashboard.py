"""Shared models for user-composed custom dashboards."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from qdash.datamodel.metric_script import MetricPeriod, StrictRevision, default_period

GRID_COLUMNS = 12
"""Width of the dashboard grid in columns."""

PanelType = Literal["qubit_metric", "coupling_metric", "metric_script", "markdown"]
DashboardVisibility = Literal["private", "project"]


class PanelLayoutModel(BaseModel):
    """Position and size of a panel on the 12-column grid."""

    x: int = Field(..., ge=0, lt=GRID_COLUMNS, description="Column of the left edge")
    y: int = Field(..., ge=0, description="Row of the top edge")
    w: int = Field(..., ge=1, le=GRID_COLUMNS, description="Width in columns")
    h: int = Field(..., ge=1, le=12, description="Height in rows")

    @model_validator(mode="after")
    def _fits_grid(self) -> PanelLayoutModel:
        if self.x + self.w > GRID_COLUMNS:
            raise ValueError(f"Panel exceeds the {GRID_COLUMNS}-column grid (x + w > 12)")
        return self


class DashboardPanelModel(BaseModel):
    """One panel of a custom dashboard.

    ``config`` is normalized when saved; its shape depends on ``type`` and is validated
    against the matching ``*PanelConfig`` model when the dashboard is saved.
    """

    panel_id: str = Field(..., min_length=1, max_length=64, description="Dashboard-unique ID")
    type: PanelType = Field(..., description="Panel kind")
    title: str = Field(default="", max_length=200, description="Panel heading")
    layout: PanelLayoutModel
    config: dict[str, Any] = Field(default_factory=dict, description="Type-specific settings")


class QubitMetricPanelConfig(BaseModel):
    """Config of a ``qubit_metric`` panel."""

    metric: str = Field(..., min_length=1, max_length=100)


class CouplingMetricPanelConfig(BaseModel):
    """Config of a ``coupling_metric`` panel."""

    metric: str = Field(..., min_length=1, max_length=100)


class MetricScriptPanelConfig(BaseModel):
    """Config of a ``metric_script`` panel.

    The panel pins ``script_revision``: saving a newer revision of the script never
    changes what the panel shows until an editor updates the pin. The service checks the
    script, revision, metric and parameters when the dashboard is saved.
    """

    model_config = ConfigDict(extra="forbid")

    script_id: str = Field(..., min_length=1, max_length=64)
    script_revision: StrictRevision = Field(..., le=2**63 - 1, description="Pinned script revision")
    metric_id: str = Field(..., min_length=1, max_length=200)
    period: MetricPeriod = Field(default_factory=default_period)
    params: dict[str, bool | int | float | str] = Field(default_factory=dict)
    view: Literal["map", "table"] = "map"
    direction: Literal["both", "forward", "reverse"] = Field(
        default="both", description="Pair maps: which edge directions to draw"
    )
    hops: list[int] = Field(
        default_factory=lambda: [1, 2], description="Pair distances shown (within declared)"
    )

    @field_validator("hops")
    @classmethod
    def _valid_hops(cls, value: list[int]) -> list[int]:
        if not value:
            raise ValueError("hops must not be empty")
        if not set(value) <= {1, 2}:
            raise ValueError("hops must be a subset of [1, 2]")
        return sorted(set(value))


class MarkdownPanelConfig(BaseModel):
    """Config of a ``markdown`` panel."""

    content: str = Field(default="", max_length=20000)


PANEL_CONFIG_MODELS: dict[str, type[BaseModel]] = {
    "qubit_metric": QubitMetricPanelConfig,
    "coupling_metric": CouplingMetricPanelConfig,
    "metric_script": MetricScriptPanelConfig,
    "markdown": MarkdownPanelConfig,
}
