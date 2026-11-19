"""Schemas for custom dashboard endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field

from qdash.datamodel.custom_dashboard import DashboardPanelModel, DashboardVisibility

MAX_PANELS = 50


class CustomDashboardCreateRequest(BaseModel):
    """Body for creating a custom dashboard."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    visibility: DashboardVisibility = "private"
    chip_id: str | None = Field(default=None, max_length=100)
    panels: list[DashboardPanelModel] = Field(default_factory=list, max_length=MAX_PANELS)
    template_id: str | None = Field(
        default=None,
        max_length=100,
        description="Template whose panels are copied into the dashboard when panels is empty",
    )


class CustomDashboardUpdateRequest(BaseModel):
    """Body for updating a custom dashboard. ``panels`` replaces the whole list."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    visibility: DashboardVisibility | None = None
    chip_id: str | None = Field(default=None, max_length=100)
    panels: list[DashboardPanelModel] | None = Field(default=None, max_length=MAX_PANELS)


class DashboardPanelResponse(DashboardPanelModel):
    """A panel as returned to the caller.

    For ``metric_script`` panels whose script the caller can view, ``script_name`` and
    ``latest_revision`` (the script's active, last-good revision) let the UI offer to move
    the pinned ``config.script_revision`` forward. Both are null for other panels.
    """

    script_name: str | None = None
    latest_revision: int | None = None


class CustomDashboardResponse(BaseModel):
    """A custom dashboard as seen by the caller."""

    dashboard_id: str
    project_id: str
    name: str
    description: str
    visibility: DashboardVisibility
    chip_id: str | None
    panels: list[DashboardPanelResponse]
    owner_username: str
    owner_user_id: str | None
    can_edit: bool = Field(..., description="Whether the caller may update or delete it")
    created_at: datetime
    updated_at: datetime


class ListCustomDashboardsResponse(BaseModel):
    """Dashboards visible to the caller."""

    dashboards: list[CustomDashboardResponse]
    total: int


class CustomDashboardTemplateResponse(BaseModel):
    """A starter template; its panels are copied into a dashboard on creation."""

    template_id: str
    name: str
    description: str
    panel_count: int
    panel_types: list[str]


class ListCustomDashboardTemplatesResponse(BaseModel):
    """Available starter templates."""

    templates: list[CustomDashboardTemplateResponse]
