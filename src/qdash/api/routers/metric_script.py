"""Metric script router.

Project editors write Python metric scripts that run in a bounded worker process and
produce per-qubit or per-pair cells for dashboard panels. A script is private to its owner
until shared with the project; the owner or a project owner may modify it. Validation and
draft previews execute unsaved code and therefore require editor rights; any member who
can view a saved script may evaluate its validated revisions.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from qdash.api.dependencies import get_metric_script_service
from qdash.api.lib.project import (
    ProjectContext,
    get_project_context,
    get_project_context_editor,
)
from qdash.api.schemas.metric_script import (
    ListMetricScriptsResponse,
    ListMetricScriptTemplatesResponse,
    MetricScriptCatalogResponse,
    MetricScriptCreateRequest,
    MetricScriptDraftEvaluateRequest,
    MetricScriptEvaluateRequest,
    MetricScriptEvaluateResponse,
    MetricScriptResponse,
    MetricScriptUpdateRequest,
    MetricScriptValidateRequest,
    MetricScriptValidateResponse,
)
from qdash.api.schemas.success import SuccessResponse
from qdash.api.services.metric_script_service import MetricScriptService

router = APIRouter()

ServiceDep = Annotated[MetricScriptService, Depends(get_metric_script_service)]
Viewer = Annotated[ProjectContext, Depends(get_project_context)]
Editor = Annotated[ProjectContext, Depends(get_project_context_editor)]


@router.get(
    "",
    summary="List metric scripts visible to the caller",
    operation_id="listMetricScripts",
    response_model=ListMetricScriptsResponse,
)
def list_metric_scripts(ctx: Viewer, service: ServiceDep) -> ListMetricScriptsResponse:
    """Return project-shared scripts and the caller's own, newest update first."""
    return service.list_visible(ctx)


@router.get(
    "/templates",
    summary="List starter metric scripts",
    operation_id="listMetricScriptTemplates",
    response_model=ListMetricScriptTemplatesResponse,
)
def list_metric_script_templates(
    _ctx: Viewer, service: ServiceDep
) -> ListMetricScriptTemplatesResponse:
    """Return the templates a new script can start from, with their source."""
    return service.list_templates()


@router.get(
    "/catalog",
    summary="List the metrics scripts can read",
    operation_id="getMetricScriptCatalog",
    response_model=MetricScriptCatalogResponse,
)
def get_metric_script_catalog(_ctx: Viewer, service: ServiceDep) -> MetricScriptCatalogResponse:
    """Return the qubit and coupling metrics available through ``ctx.data``."""
    return service.catalog()


@router.post(
    "/validate",
    summary="Validate metric script source without saving it",
    operation_id="validateMetricScript",
    response_model=MetricScriptValidateResponse,
)
def validate_metric_script(
    body: MetricScriptValidateRequest, _ctx: Editor, service: ServiceDep
) -> MetricScriptValidateResponse:
    """Compile the source in a worker and return its metrics or diagnostics."""
    return service.validate(body.source)


@router.post(
    "/evaluate",
    summary="Preview unsaved metric script source on a chip",
    operation_id="evaluateMetricScriptDraft",
    response_model=MetricScriptEvaluateResponse,
)
def evaluate_metric_script_draft(
    body: MetricScriptDraftEvaluateRequest, ctx: Editor, service: ServiceDep
) -> MetricScriptEvaluateResponse:
    """Evaluate one metric of the given source over the chip; nothing is saved."""
    return service.evaluate_draft(ctx, body)


@router.get(
    "/{script_id}",
    summary="Get a metric script",
    operation_id="getMetricScript",
    response_model=MetricScriptResponse,
)
def get_metric_script(script_id: str, ctx: Viewer, service: ServiceDep) -> MetricScriptResponse:
    """Return a script with its source, active source and revisions."""
    return service.get(ctx, script_id)


@router.post(
    "",
    summary="Create a metric script",
    operation_id="createMetricScript",
    response_model=MetricScriptResponse,
    status_code=201,
)
def create_metric_script(
    body: MetricScriptCreateRequest, ctx: Editor, service: ServiceDep
) -> MetricScriptResponse:
    """Create a script owned by the caller from source text or a template."""
    return service.create(ctx, body)


@router.patch(
    "/{script_id}",
    summary="Update a metric script",
    operation_id="updateMetricScript",
    response_model=MetricScriptResponse,
)
def update_metric_script(
    script_id: str, body: MetricScriptUpdateRequest, ctx: Editor, service: ServiceDep
) -> MetricScriptResponse:
    """Update settings or save new source; invalid source keeps the last good revision active."""
    return service.update(ctx, script_id, body)


@router.delete(
    "/{script_id}",
    summary="Delete a metric script",
    operation_id="deleteMetricScript",
    response_model=SuccessResponse,
)
def delete_metric_script(script_id: str, ctx: Editor, service: ServiceDep) -> SuccessResponse:
    """Delete a script no dashboard references."""
    return service.delete(ctx, script_id)


@router.post(
    "/{script_id}/copy",
    summary="Copy a metric script",
    operation_id="copyMetricScript",
    response_model=MetricScriptResponse,
    status_code=201,
)
def copy_metric_script(script_id: str, ctx: Editor, service: ServiceDep) -> MetricScriptResponse:
    """Copy the active source of a visible script into a private script of the caller."""
    return service.copy(ctx, script_id)


@router.post(
    "/{script_id}/evaluate",
    summary="Evaluate a saved metric script on a chip",
    operation_id="evaluateMetricScript",
    response_model=MetricScriptEvaluateResponse,
)
def evaluate_metric_script(
    script_id: str, body: MetricScriptEvaluateRequest, ctx: Viewer, service: ServiceDep
) -> MetricScriptEvaluateResponse:
    """Evaluate one metric of a validated revision (the active one by default)."""
    return service.evaluate_saved(ctx, script_id, body)
