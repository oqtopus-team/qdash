"""Dashboard router.

Project members compose dashboards from panels. A dashboard is private to its
owner until shared with the project; the owner or a project owner may modify it.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from qdash.api.dependencies import get_dashboard_service
from qdash.api.lib.project import (
    ProjectContext,
    get_project_context,
    get_project_context_editor,
)
from qdash.api.schemas.dashboard import (
    DashboardCreateRequest,
    DashboardResponse,
    DashboardTemplatePreviewResponse,
    DashboardUpdateRequest,
    ListDashboardsResponse,
    ListDashboardTemplatesResponse,
)
from qdash.api.schemas.success import SuccessResponse
from qdash.api.services.dashboard_service import DashboardService

router = APIRouter()

ServiceDep = Annotated[DashboardService, Depends(get_dashboard_service)]


@router.get(
    "",
    summary="List dashboards visible to the caller",
    operation_id="listDashboards",
    response_model=ListDashboardsResponse,
)
def list_dashboards(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: ServiceDep,
) -> ListDashboardsResponse:
    """Return project-shared dashboards and the caller's own, newest update first."""
    return service.list_visible(ctx)


@router.get(
    "/templates",
    summary="List starter templates for dashboards",
    operation_id="listDashboardTemplates",
    response_model=ListDashboardTemplatesResponse,
)
def list_dashboard_templates(
    _ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: ServiceDep,
) -> ListDashboardTemplatesResponse:
    """Return the templates a new dashboard can copy its panels from."""
    return service.list_templates()


@router.get(
    "/templates/{template_id}/preview",
    summary="Preview the panels a starter template would create",
    operation_id="previewDashboardTemplate",
    response_model=DashboardTemplatePreviewResponse,
)
def preview_dashboard_template(
    template_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: ServiceDep,
) -> DashboardTemplatePreviewResponse:
    """Return the panels a dashboard created from the template now would hold.

    Nothing is created: script panels point at the shared script creation would reuse, or,
    when the project has none yet, name the starter script creation would add.
    """
    return service.preview_template(ctx, template_id)


@router.get(
    "/{dashboard_id}",
    summary="Get a dashboard",
    operation_id="getDashboard",
    response_model=DashboardResponse,
)
def get_dashboard(
    dashboard_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: ServiceDep,
) -> DashboardResponse:
    """Return a dashboard the caller owns or that is shared with the project."""
    return service.get(ctx, dashboard_id)


@router.post(
    "",
    summary="Create a dashboard",
    operation_id="createDashboard",
    response_model=DashboardResponse,
    status_code=201,
)
def create_dashboard(
    body: DashboardCreateRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: ServiceDep,
) -> DashboardResponse:
    """Create a dashboard owned by the caller."""
    return service.create(ctx, body)


@router.patch(
    "/{dashboard_id}",
    summary="Update a dashboard",
    operation_id="updateDashboard",
    response_model=DashboardResponse,
)
def update_dashboard(
    dashboard_id: str,
    body: DashboardUpdateRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: ServiceDep,
) -> DashboardResponse:
    """Update a dashboard. A provided ``panels`` list replaces the previous one."""
    return service.update(ctx, dashboard_id, body)


@router.delete(
    "/{dashboard_id}",
    summary="Delete a dashboard",
    operation_id="deleteDashboard",
    response_model=SuccessResponse,
)
def delete_dashboard(
    dashboard_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: ServiceDep,
) -> SuccessResponse:
    """Delete a dashboard owned by the caller, or any dashboard as project owner."""
    return service.delete(ctx, dashboard_id)


@router.post(
    "/{dashboard_id}/duplicate",
    summary="Duplicate a dashboard",
    operation_id="duplicateDashboard",
    response_model=DashboardResponse,
    status_code=201,
)
def duplicate_dashboard(
    dashboard_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: ServiceDep,
) -> DashboardResponse:
    """Copy a visible dashboard into a private dashboard owned by the caller."""
    return service.duplicate(ctx, dashboard_id)
