"""Custom dashboard router.

Project members compose dashboards from panels. A dashboard is private to its
owner until shared with the project; the owner or a project owner may modify it.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from qdash.api.dependencies import get_custom_dashboard_service
from qdash.api.lib.project import (
    ProjectContext,
    get_project_context,
    get_project_context_editor,
)
from qdash.api.schemas.custom_dashboard import (
    CustomDashboardCreateRequest,
    CustomDashboardResponse,
    CustomDashboardUpdateRequest,
    ListCustomDashboardsResponse,
    ListCustomDashboardTemplatesResponse,
)
from qdash.api.schemas.success import SuccessResponse
from qdash.api.services.custom_dashboard_service import CustomDashboardService

router = APIRouter()

ServiceDep = Annotated[CustomDashboardService, Depends(get_custom_dashboard_service)]


@router.get(
    "",
    summary="List custom dashboards visible to the caller",
    operation_id="listCustomDashboards",
    response_model=ListCustomDashboardsResponse,
)
def list_custom_dashboards(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: ServiceDep,
) -> ListCustomDashboardsResponse:
    """Return project-shared dashboards and the caller's own, newest update first."""
    return service.list_visible(ctx)


@router.get(
    "/templates",
    summary="List starter templates for custom dashboards",
    operation_id="listCustomDashboardTemplates",
    response_model=ListCustomDashboardTemplatesResponse,
)
def list_custom_dashboard_templates(
    _ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: ServiceDep,
) -> ListCustomDashboardTemplatesResponse:
    """Return the templates a new dashboard can copy its panels from."""
    return service.list_templates()


@router.get(
    "/{dashboard_id}",
    summary="Get a custom dashboard",
    operation_id="getCustomDashboard",
    response_model=CustomDashboardResponse,
)
def get_custom_dashboard(
    dashboard_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: ServiceDep,
) -> CustomDashboardResponse:
    """Return a dashboard the caller owns or that is shared with the project."""
    return service.get(ctx, dashboard_id)


@router.post(
    "",
    summary="Create a custom dashboard",
    operation_id="createCustomDashboard",
    response_model=CustomDashboardResponse,
    status_code=201,
)
def create_custom_dashboard(
    body: CustomDashboardCreateRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: ServiceDep,
) -> CustomDashboardResponse:
    """Create a dashboard owned by the caller."""
    return service.create(ctx, body)


@router.patch(
    "/{dashboard_id}",
    summary="Update a custom dashboard",
    operation_id="updateCustomDashboard",
    response_model=CustomDashboardResponse,
)
def update_custom_dashboard(
    dashboard_id: str,
    body: CustomDashboardUpdateRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: ServiceDep,
) -> CustomDashboardResponse:
    """Update a dashboard. A provided ``panels`` list replaces the previous one."""
    return service.update(ctx, dashboard_id, body)


@router.delete(
    "/{dashboard_id}",
    summary="Delete a custom dashboard",
    operation_id="deleteCustomDashboard",
    response_model=SuccessResponse,
)
def delete_custom_dashboard(
    dashboard_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: ServiceDep,
) -> SuccessResponse:
    """Delete a dashboard owned by the caller, or any dashboard as project owner."""
    return service.delete(ctx, dashboard_id)


@router.post(
    "/{dashboard_id}/duplicate",
    summary="Duplicate a custom dashboard",
    operation_id="duplicateCustomDashboard",
    response_model=CustomDashboardResponse,
    status_code=201,
)
def duplicate_custom_dashboard(
    dashboard_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: ServiceDep,
) -> CustomDashboardResponse:
    """Copy a visible dashboard into a private dashboard owned by the caller."""
    return service.duplicate(ctx, dashboard_id)
