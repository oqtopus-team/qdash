"""Shared models for user-composed custom dashboards."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

GRID_COLUMNS = 12
"""Width of the dashboard grid in columns."""

PanelType = Literal["qubit_metric", "coupling_metric", "collision_check", "markdown"]
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

    ``config`` is stored as given; its shape depends on ``type`` and is validated
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


class CollisionPanelConfig(BaseModel):
    """Config of a ``collision_check`` panel.

    ``check`` must name a registered collision check; the service verifies it
    together with the parameter names.
    """

    check: str = Field(..., min_length=1)
    params: dict[str, float] = Field(default_factory=dict)
    hops: list[int] = Field(default_factory=lambda: [1, 2])

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
    "collision_check": CollisionPanelConfig,
    "markdown": MarkdownPanelConfig,
}
