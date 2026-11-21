"""Schemas for dashboard endpoints."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from qdash.datamodel.dashboard import DashboardPanelModel, DashboardVisibility

MAX_PANELS = 50


class DashboardCreateRequest(BaseModel):
    """Body for creating a dashboard."""

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


class DashboardUpdateRequest(BaseModel):
    """Body for updating a dashboard. ``panels`` replaces the whole list."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    visibility: DashboardVisibility | None = None
    chip_id: str | None = Field(default=None, max_length=100)
    panels: list[DashboardPanelModel] | None = Field(default=None, max_length=MAX_PANELS)
    expected_version: Annotated[int, Field(strict=True, ge=0)] | None = Field(
        default=None,
        description=(
            "Reject with 409 unless the dashboard is still at this version; "
            "omit to update whatever is stored"
        ),
    )


class DashboardPanelResponse(DashboardPanelModel):
    """A panel as returned to the caller.

    For ``metric_script`` panels whose script the caller can view, ``script_name`` and
    ``latest_revision`` (the script's active, last-good revision) let the UI offer to move
    the pinned ``config.script_revision`` forward. Both are null for other panels.
    """

    script_name: str | None = None
    latest_revision: int | None = None


class DashboardResponse(BaseModel):
    """A dashboard as seen by the caller."""

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
    version: int = Field(
        ..., description="Write counter; send it as expected_version to guard an update"
    )
    created_at: datetime
    updated_at: datetime


class ListDashboardsResponse(BaseModel):
    """Dashboards visible to the caller."""

    dashboards: list[DashboardResponse]
    total: int


class DashboardTemplateResponse(BaseModel):
    """A starter template; its panels are copied into a dashboard on creation."""

    template_id: str
    name: str
    description: str
    panel_count: int
    panel_types: list[str]


class ListDashboardTemplatesResponse(BaseModel):
    """Available starter templates."""

    templates: list[DashboardTemplateResponse]


class TemplatePreviewPanel(DashboardPanelResponse):
    """A template panel as it would be created now.

    A ``metric_script`` panel whose project script exists is pinned to it as on creation.
    When the project has no such script yet, ``config`` has no script reference and
    ``script_template_id`` names the starter script that creating the dashboard adds.
    """

    script_template_id: str | None = None


class TemplateScriptToCreate(BaseModel):
    """A shared metric script that creating a dashboard from the template adds."""

    template_id: str
    name: str
    source: str = Field(..., description="The starter source, for an unsaved preview")


class DashboardTemplatePreviewResponse(BaseModel):
    """What a dashboard created from a template now would hold. Reading it writes nothing."""

    template_id: str
    name: str
    description: str
    panels: list[TemplatePreviewPanel]
    scripts_to_create: list[TemplateScriptToCreate] = Field(
        ...,
        description=(
            "Project-visible metric scripts creation adds because the project has no "
            "script from that starter that still defines the panels' metrics"
        ),
    )
