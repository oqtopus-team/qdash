"""Service layer for user-composed custom dashboards."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ValidationError
from starlette.exceptions import HTTPException

from qdash.api.schemas.custom_dashboard import (
    CustomDashboardCreateRequest,
    CustomDashboardResponse,
    CustomDashboardTemplateResponse,
    CustomDashboardUpdateRequest,
    DashboardPanelResponse,
    ListCustomDashboardsResponse,
    ListCustomDashboardTemplatesResponse,
)
from qdash.api.schemas.success import SuccessResponse
from qdash.api.services.custom_dashboard_templates import (
    TEMPLATES,
    DashboardTemplate,
    instantiate_panels,
)
from qdash.api.services.metric_script_service import check_params
from qdash.datamodel.custom_dashboard import (
    PANEL_CONFIG_MODELS,
    DashboardPanelModel,
    DashboardVisibility,
    MetricScriptPanelConfig,
)
from qdash.datamodel.project import ProjectRole
from qdash.dbmodel.custom_dashboard import CustomDashboardDocument

if TYPE_CHECKING:
    from qdash.api.lib.project import ProjectContext
    from qdash.api.services.metric_script_service import MetricScriptService
    from qdash.dbmodel.metric_script import MetricScriptDocument
    from qdash.repository.custom_dashboard import MongoCustomDashboardRepository
    from qdash.repository.metric_script import MongoMetricScriptRepository

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


def _invalid(panel: DashboardPanelModel, reason: str) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail=f"Invalid config for {panel.type} panel {_panel_name(panel)}: {reason}",
    )


def validate_panel_configs(panels: list[DashboardPanelModel]) -> list[BaseModel]:
    """Validate panel IDs and type-specific configs; return the parsed configs.

    Raises:
        HTTPException: 422 naming the first invalid panel.
    """
    seen: set[str] = set()
    configs: list[BaseModel] = []
    for panel in panels:
        if panel.panel_id in seen:
            raise HTTPException(
                status_code=422, detail=f"Duplicate panel_id '{panel.panel_id}' in dashboard"
            )
        seen.add(panel.panel_id)
        model = PANEL_CONFIG_MODELS[panel.type]
        try:
            configs.append(model.model_validate(panel.config))
        except ValidationError as exc:
            raise _invalid(panel, _format_validation_error(exc)) from exc
    return configs


class CustomDashboardService:
    """CRUD and sharing rules for CustomDashboardDocument."""

    def __init__(
        self,
        custom_dashboard_repository: MongoCustomDashboardRepository,
        metric_script_repository: MongoMetricScriptRepository,
        metric_script_service: MetricScriptService,
    ) -> None:
        self._repo = custom_dashboard_repository
        self._scripts = metric_script_repository
        self._script_service = metric_script_service

    @staticmethod
    def _is_owner(doc: CustomDashboardDocument, ctx: ProjectContext) -> bool:
        return doc.user_id is not None and doc.user_id == ctx.user.user_id

    @classmethod
    def _can_view(cls, doc: CustomDashboardDocument, ctx: ProjectContext) -> bool:
        return doc.visibility == "project" or cls._is_owner(doc, ctx)

    @classmethod
    def _can_edit(cls, doc: CustomDashboardDocument, ctx: ProjectContext) -> bool:
        return cls._is_owner(doc, ctx) or ctx.role == ProjectRole.OWNER

    def _visible_script(
        self,
        ctx: ProjectContext,
        script_id: str,
        cache: dict[str, MetricScriptDocument | None],
    ) -> MetricScriptDocument | None:
        if script_id not in cache:
            cache[script_id] = self._script_service.find_visible(ctx, script_id)
        return cache[script_id]

    def validate_panels(
        self,
        ctx: ProjectContext,
        panels: list[DashboardPanelModel],
        visibility: DashboardVisibility,
    ) -> None:
        """Validate configs and the scripts, revisions, metrics and params they reference.

        Raises:
            HTTPException: 422 naming the first invalid panel.
        """
        configs = validate_panel_configs(panels)
        cache: dict[str, MetricScriptDocument | None] = {}
        for panel, config in zip(panels, configs, strict=True):
            if not isinstance(config, MetricScriptPanelConfig):
                continue
            script = self._visible_script(ctx, config.script_id, cache)
            if script is None:
                raise _invalid(panel, f"metric script '{config.script_id}' not found")
            if visibility == "project" and script.visibility != "project":
                raise _invalid(
                    panel,
                    f"metric script '{script.name}' is private; share it with the project "
                    "before using it on a shared dashboard",
                )
            revision = script.find_revision(config.script_revision)
            if revision is None:
                raise _invalid(
                    panel, f"revision {config.script_revision} of '{script.name}' not found"
                )
            if revision.status != "valid":
                raise _invalid(
                    panel, f"revision {config.script_revision} of '{script.name}' is invalid"
                )
            metric = next((m for m in revision.metrics if m.id == config.metric_id), None)
            if metric is None:
                known = ", ".join(m.id for m in revision.metrics)
                raise _invalid(
                    panel,
                    f"unknown metric '{config.metric_id}' in revision "
                    f"{config.script_revision}; expected one of: {known}",
                )
            try:
                check_params(metric, dict(config.params))
            except ValueError as exc:
                raise _invalid(panel, str(exc)) from exc
            if metric.target == "pair" and not set(config.hops) <= set(metric.hops):
                raise _invalid(
                    panel,
                    f"hops {config.hops} are outside the metric's declared hops {metric.hops}",
                )

    def _to_response(
        self,
        doc: CustomDashboardDocument,
        ctx: ProjectContext,
        cache: dict[str, MetricScriptDocument | None] | None = None,
    ) -> CustomDashboardResponse:
        scripts = cache if cache is not None else {}
        panels = []
        for panel in doc.panels:
            item = DashboardPanelResponse(**panel.model_dump())
            script_id = panel.config.get("script_id")
            if panel.type == "metric_script" and isinstance(script_id, str):
                script = self._visible_script(ctx, script_id, scripts)
                if script is not None:
                    item.script_name = script.name
                    item.latest_revision = script.active_revision
            panels.append(item)
        return CustomDashboardResponse(
            dashboard_id=doc.dashboard_id,
            project_id=doc.project_id,
            name=doc.name,
            description=doc.description,
            visibility=doc.visibility,
            chip_id=doc.chip_id,
            panels=panels,
            owner_username=doc.username,
            owner_user_id=doc.user_id,
            can_edit=self._can_edit(doc, ctx),
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
        cache: dict[str, MetricScriptDocument | None] = {}
        dashboards = [self._to_response(doc, ctx, cache) for doc in docs]
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
                scripts = {}
                for script_template, metrics in template.script_requirements().items():
                    script = self._script_service.ensure_template_script(
                        ctx, script_template, metrics
                    )
                    assert script.active_revision is not None
                    scripts[script_template] = (script.script_id, script.active_revision)
                panels = instantiate_panels(template, scripts)
        self.validate_panels(ctx, panels, body.visibility)
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
        visibility = body.visibility if body.visibility is not None else doc.visibility
        if body.panels is not None:
            self.validate_panels(ctx, body.panels, visibility)
            doc.panels = body.panels
        elif visibility != doc.visibility:
            self.validate_panels(ctx, doc.panels, visibility)
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
