"""Service layer for user-composed custom dashboards."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import ValidationError
from starlette.exceptions import HTTPException

from qdash.api.schemas.custom_dashboard import (
    CustomDashboardCreateRequest,
    CustomDashboardResponse,
    CustomDashboardTemplateResponse,
    CustomDashboardUpdateRequest,
    ListCustomDashboardsResponse,
    ListCustomDashboardTemplatesResponse,
)
from qdash.api.schemas.success import SuccessResponse
from qdash.api.services.collision_analysis import CHECKS, resolve_params
from qdash.api.services.custom_dashboard_templates import (
    TEMPLATES,
    DashboardTemplate,
    instantiate_panels,
)
from qdash.datamodel.custom_dashboard import (
    PANEL_CONFIG_MODELS,
    CollisionPanelConfig,
    DashboardPanelModel,
)
from qdash.datamodel.project import ProjectRole
from qdash.dbmodel.custom_dashboard import CustomDashboardDocument

if TYPE_CHECKING:
    from qdash.api.lib.project import ProjectContext
    from qdash.repository.custom_dashboard import MongoCustomDashboardRepository

NOT_FOUND = "Custom dashboard not found"
MAX_NAME_LENGTH = 200
COPY_SUFFIX = " (copy)"


def _copy_name(name: str) -> str:
    """Name of a duplicate, kept within the request schema's name length."""
    return f"{name[: MAX_NAME_LENGTH - len(COPY_SUFFIX)]}{COPY_SUFFIX}"


def _panel_name(panel: DashboardPanelModel) -> str:
    return f"'{panel.title}' ({panel.panel_id})" if panel.title else f"'{panel.panel_id}'"


def _format_validation_error(exc: ValidationError) -> str:
    parts = []
    for error in exc.errors():
        location = ".".join(str(item) for item in error.get("loc", ()))
        message = error.get("msg", "invalid value")
        parts.append(f"{location}: {message}" if location else message)
    return "; ".join(parts)


def validate_panels(panels: list[DashboardPanelModel]) -> None:
    """Validate panel IDs and type-specific configs.

    Raises:
        HTTPException: 422 naming the first invalid panel.
    """
    seen: set[str] = set()
    for panel in panels:
        if panel.panel_id in seen:
            raise HTTPException(
                status_code=422, detail=f"Duplicate panel_id '{panel.panel_id}' in dashboard"
            )
        seen.add(panel.panel_id)
        model = PANEL_CONFIG_MODELS[panel.type]
        try:
            config = model.model_validate(panel.config)
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Invalid config for {panel.type} panel {_panel_name(panel)}: "
                    f"{_format_validation_error(exc)}"
                ),
            ) from exc
        if isinstance(config, CollisionPanelConfig):
            if config.check not in CHECKS:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Invalid config for collision_check panel {_panel_name(panel)}: "
                        f"unknown check '{config.check}'"
                    ),
                )
            try:
                resolve_params(config.check, config.params)
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Invalid config for collision_check panel {_panel_name(panel)}: {exc}"
                    ),
                ) from exc


class CustomDashboardService:
    """CRUD and sharing rules for CustomDashboardDocument."""

    def __init__(self, custom_dashboard_repository: MongoCustomDashboardRepository) -> None:
        self._repo = custom_dashboard_repository

    @staticmethod
    def _is_owner(doc: CustomDashboardDocument, ctx: ProjectContext) -> bool:
        return doc.user_id is not None and doc.user_id == ctx.user.user_id

    @classmethod
    def _can_view(cls, doc: CustomDashboardDocument, ctx: ProjectContext) -> bool:
        return doc.visibility == "project" or cls._is_owner(doc, ctx)

    @classmethod
    def _can_edit(cls, doc: CustomDashboardDocument, ctx: ProjectContext) -> bool:
        return cls._is_owner(doc, ctx) or ctx.role == ProjectRole.OWNER

    @classmethod
    def _to_response(
        cls, doc: CustomDashboardDocument, ctx: ProjectContext
    ) -> CustomDashboardResponse:
        return CustomDashboardResponse(
            dashboard_id=doc.dashboard_id,
            project_id=doc.project_id,
            name=doc.name,
            description=doc.description,
            visibility=doc.visibility,
            chip_id=doc.chip_id,
            panels=doc.panels,
            owner_username=doc.username,
            owner_user_id=doc.user_id,
            can_edit=cls._can_edit(doc, ctx),
            created_at=doc.system_info.created_at,
            updated_at=doc.system_info.updated_at,
        )

    def _get_visible(self, ctx: ProjectContext, dashboard_id: str) -> CustomDashboardDocument:
        doc = self._repo.get(project_id=ctx.project_id, dashboard_id=dashboard_id)
        if doc is None or not self._can_view(doc, ctx):
            raise HTTPException(status_code=404, detail=NOT_FOUND)
        return doc

    def _get_editable(self, ctx: ProjectContext, dashboard_id: str) -> CustomDashboardDocument:
        doc = self._get_visible(ctx, dashboard_id)
        if not self._can_edit(doc, ctx):
            raise HTTPException(
                status_code=403,
                detail="Only the dashboard owner or a project owner can modify this dashboard",
            )
        return doc

    def list_visible(self, ctx: ProjectContext) -> ListCustomDashboardsResponse:
        docs = self._repo.list_visible(project_id=ctx.project_id, user_id=ctx.user.user_id)
        dashboards = [self._to_response(doc, ctx) for doc in docs]
        return ListCustomDashboardsResponse(dashboards=dashboards, total=len(dashboards))

    def get(self, ctx: ProjectContext, dashboard_id: str) -> CustomDashboardResponse:
        return self._to_response(self._get_visible(ctx, dashboard_id), ctx)

    @staticmethod
    def _template_response(template: DashboardTemplate) -> CustomDashboardTemplateResponse:
        return CustomDashboardTemplateResponse(
            template_id=template.template_id,
            name=template.name,
            description=template.description,
            panel_count=len(template.panels),
            panel_types=sorted({panel.type for panel in template.panels}),
        )

    def list_templates(self) -> ListCustomDashboardTemplatesResponse:
        return ListCustomDashboardTemplatesResponse(
            templates=[self._template_response(t) for t in TEMPLATES.values()]
        )

    def create(
        self, ctx: ProjectContext, body: CustomDashboardCreateRequest
    ) -> CustomDashboardResponse:
        panels = body.panels
        if body.template_id is not None:
            template = TEMPLATES.get(body.template_id)
            if template is None:
                raise HTTPException(
                    status_code=422, detail=f"Unknown dashboard template '{body.template_id}'"
                )
            if not panels:
                # Copy on create: the dashboard owns its panels from now on.
                panels = instantiate_panels(template)
        validate_panels(panels)
        doc = CustomDashboardDocument(
            project_id=ctx.project_id,
            user_id=ctx.user.user_id,
            username=ctx.user.username,
            name=body.name,
            description=body.description,
            visibility=body.visibility,
            chip_id=body.chip_id,
            panels=panels,
        )
        self._repo.insert(doc)
        return self._to_response(doc, ctx)

    def update(
        self, ctx: ProjectContext, dashboard_id: str, body: CustomDashboardUpdateRequest
    ) -> CustomDashboardResponse:
        doc = self._get_editable(ctx, dashboard_id)
        if body.panels is not None:
            validate_panels(body.panels)
            doc.panels = body.panels
        if body.name is not None:
            doc.name = body.name
        if body.description is not None:
            doc.description = body.description
        if body.visibility is not None:
            doc.visibility = body.visibility
        if "chip_id" in body.model_fields_set:
            # An explicit null clears the default chip.
            doc.chip_id = body.chip_id
        self._repo.save(doc)
        return self._to_response(doc, ctx)

    def delete(self, ctx: ProjectContext, dashboard_id: str) -> SuccessResponse:
        doc = self._get_editable(ctx, dashboard_id)
        self._repo.delete(doc)
        return SuccessResponse(message="Custom dashboard deleted")

    def duplicate(self, ctx: ProjectContext, dashboard_id: str) -> CustomDashboardResponse:
        source = self._get_visible(ctx, dashboard_id)
        copy = CustomDashboardDocument(
            project_id=ctx.project_id,
            user_id=ctx.user.user_id,
            username=ctx.user.username,
            name=_copy_name(source.name),
            description=source.description,
            visibility="private",
            chip_id=source.chip_id,
            panels=[panel.model_copy(deep=True) for panel in source.panels],
        )
        self._repo.insert(copy)
        return self._to_response(copy, ctx)
