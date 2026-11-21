"""Service layer for user-composed dashboards.

A metric_script panel pins a script revision. The pins are stored on the script document
(``MetricScriptDocument.pins``, keyed by dashboard ID), because only that document can be
updated atomically together with the script's revision history: every pin change increments
the script's ``version``, and a script save is a compare-and-set on that version.

Dashboard writes therefore follow one order:

1. Widen the pins on every script the new panels use (``add_pin``). The filter of that
   update refuses revisions that are gone and shared pins on unshared scripts, which is how
   a dashboard save loses to a script save that evicted or unshared first (422).
2. Store the dashboard (insert, or a compare-and-set on the dashboard's ``version``).
3. Narrow each pin to exactly the stored panels (``narrow_pin``), only if no other write of
   the same dashboard claimed the pin after step 1.

A pin is in the script document before any stored dashboard depends on it, so a concurrent
script save either sees the pin or fails its compare-and-set. A failed request, a lost race
or a crash between steps can leave a surplus pin, never a missing one; the next successful
save involving that script narrows it, and deleting the dashboard removes all its pins.
A crash before inserting a new dashboard may leave orphan pins requiring administrative
cleanup once no writer can still insert that dashboard.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from pydantic import BaseModel, ValidationError
from starlette.exceptions import HTTPException

from qdash.api.metric_runtime.template_library import TEMPLATES as SCRIPT_TEMPLATES
from qdash.api.schemas.dashboard import (
    DashboardCreateRequest,
    DashboardPanelResponse,
    DashboardResponse,
    DashboardTemplatePreviewResponse,
    DashboardTemplateResponse,
    DashboardUpdateRequest,
    ListDashboardsResponse,
    ListDashboardTemplatesResponse,
    TemplatePreviewPanel,
    TemplateScriptToCreate,
)
from qdash.api.schemas.success import SuccessResponse
from qdash.api.services.dashboard_templates import (
    TEMPLATES,
    DashboardTemplate,
    instantiate_panels,
)
from qdash.api.services.metric_script_service import check_params, normalize_targets
from qdash.datamodel.dashboard import (
    PANEL_CONFIG_MODELS,
    DashboardPanelModel,
    DashboardVisibility,
    MetricScriptPanelConfig,
)
from qdash.datamodel.project import ProjectRole
from qdash.dbmodel.dashboard import DashboardDocument

if TYPE_CHECKING:
    from qdash.api.lib.project import ProjectContext
    from qdash.api.services.metric_script_service import MetricScriptService
    from qdash.datamodel.metric_script import MetricInfo
    from qdash.dbmodel.metric_script import MetricScriptDocument
    from qdash.repository.dashboard import MongoDashboardRepository
    from qdash.repository.metric_script import MongoMetricScriptRepository

NOT_FOUND = "Dashboard not found"
STALE = "Dashboard was changed by another save; reload it before saving"
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


def script_pins(panels: list[DashboardPanelModel]) -> dict[str, list[int]]:
    """Script revisions the metric_script panels of a dashboard pin, by script ID."""
    pins: dict[str, set[int]] = {}
    for panel in panels:
        if panel.type != "metric_script":
            continue
        # Panels are validated before they are stored or pinned.
        config = MetricScriptPanelConfig.model_validate(panel.config)
        pins.setdefault(config.script_id, set()).add(config.script_revision)
    return {script_id: sorted(revisions) for script_id, revisions in pins.items()}


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
            config = model.model_validate(panel.config)
            # Keep unknown settings accepted by non-script panels, while normalizing
            # validated fields and materializing their defaults.
            panel.config = {**panel.config, **config.model_dump(mode="json")}
            configs.append(config)
        except ValidationError as exc:
            raise _invalid(panel, _format_validation_error(exc)) from exc
    return configs


class DashboardService:
    """CRUD and sharing rules for DashboardDocument."""

    def __init__(
        self,
        dashboard_repository: MongoDashboardRepository,
        metric_script_repository: MongoMetricScriptRepository,
        metric_script_service: MetricScriptService,
    ) -> None:
        self._repo = dashboard_repository
        self._scripts = metric_script_repository
        self._script_service = metric_script_service

    @staticmethod
    def _is_owner(doc: DashboardDocument, ctx: ProjectContext) -> bool:
        return doc.user_id is not None and doc.user_id == ctx.user.user_id

    @classmethod
    def _can_view(cls, doc: DashboardDocument, ctx: ProjectContext) -> bool:
        return doc.visibility == "project" or cls._is_owner(doc, ctx)

    @classmethod
    def _can_edit(cls, doc: DashboardDocument, ctx: ProjectContext) -> bool:
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
            self._check_view(panel, config, metric)

    @staticmethod
    def _check_view(
        panel: DashboardPanelModel, config: MetricScriptPanelConfig, metric: MetricInfo
    ) -> None:
        """Refuse a view that cannot show the metric's result kind, and check its targets.

        A series is never reduced to one value for a map or table, and a scalar metric has no
        time axis to draw. Targets are checked against the chip when the panel is evaluated.
        """
        if metric.result == "series":
            if config.view != "timeseries":
                raise _invalid(
                    panel,
                    f"metric '{metric.id}' returns a time series; set view to 'timeseries' "
                    "(map and table show one value per target)",
                )
            try:
                keys = normalize_targets(metric, list(config.targets))
            except ValueError as exc:
                raise _invalid(panel, str(exc)) from exc
            panel.config = {**panel.config, "targets": keys}
            return
        if config.view == "timeseries":
            raise _invalid(
                panel,
                f"metric '{metric.id}' returns one value per target; use view 'map' or 'table'",
            )
        if config.targets:
            raise _invalid(
                panel,
                f"targets apply only to series metrics; '{metric.id}' covers the whole chip",
            )

    def _to_response(
        self,
        doc: DashboardDocument,
        ctx: ProjectContext,
        cache: dict[str, MetricScriptDocument | None] | None = None,
    ) -> DashboardResponse:
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
        return DashboardResponse(
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
            version=doc.version,
            created_at=doc.system_info.created_at,
            updated_at=doc.system_info.updated_at,
        )

    def _get_visible(self, ctx: ProjectContext, dashboard_id: str) -> DashboardDocument:
        doc = self._repo.get(project_id=ctx.project_id, dashboard_id=dashboard_id)
        if doc is None or not self._can_view(doc, ctx):
            raise HTTPException(status_code=404, detail=NOT_FOUND)
        return doc

    def _get_editable(self, ctx: ProjectContext, dashboard_id: str) -> DashboardDocument:
        doc = self._get_visible(ctx, dashboard_id)
        if not self._can_edit(doc, ctx):
            raise HTTPException(
                status_code=403,
                detail="Only the dashboard owner or a project owner can modify this dashboard",
            )
        return doc

    # -- pins ----------------------------------------------------------------

    def _pin_conflict(
        self, ctx: ProjectContext, script_id: str, revisions: list[int], shared: bool
    ) -> HTTPException:
        """Explain why ``add_pin`` did not match: a revision is gone or the script unshared."""
        script = self._scripts.get(project_id=ctx.project_id, script_id=script_id)
        if script is None:
            reason = f"metric script '{script_id}' was deleted"
        else:
            missing = [r for r in revisions if script.find_revision(r) is None]
            if missing:
                numbers = ", ".join(str(r) for r in missing)
                noun = "revision" if len(missing) == 1 else "revisions"
                verb = "was" if len(missing) == 1 else "were"
                reason = f"{noun} {numbers} of metric script '{script.name}' {verb} removed"
            elif shared and script.visibility != "project":
                reason = f"metric script '{script.name}' is no longer shared"
            else:
                reason = f"metric script '{script.name}' changed"
        return HTTPException(status_code=422, detail=f"{reason} while saving; reload the dashboard")

    def _add_pins(
        self,
        ctx: ProjectContext,
        dashboard_id: str,
        pins: dict[str, list[int]],
        *,
        shared: bool,
        writer: str,
        claim: set[str] | None = None,
    ) -> None:
        """Widen the pins of ``dashboard_id`` on every script in ``pins`` (step 1).

        Scripts in ``claim`` that are not in ``pins`` only get their existing pin claimed
        for ``writer`` so that step 3 may remove it.

        Raises:
            HTTPException: 422 when a revision is gone or a script is no longer shared.
        """
        for script_id in sorted(set(pins) | (claim or set())):
            revisions = pins.get(script_id, [])
            added = self._scripts.add_pin(
                project_id=ctx.project_id,
                script_id=script_id,
                dashboard_id=dashboard_id,
                revisions=revisions,
                shared=shared and bool(revisions),
                writer=writer,
            )
            if not added and revisions:
                raise self._pin_conflict(ctx, script_id, revisions, shared)

    def _insert(self, ctx: ProjectContext, doc: DashboardDocument) -> None:
        """Pin the scripts of a new dashboard, then insert it."""
        try:
            self._add_pins(
                ctx,
                doc.dashboard_id,
                script_pins(doc.panels),
                shared=doc.visibility == "project",
                writer=uuid4().hex,
            )
        except Exception:
            # Insertion has not been attempted, so this ID cannot be persisted yet.
            self._scripts.clear_dashboard_pins(
                project_id=ctx.project_id, dashboard_id=doc.dashboard_id
            )
            raise
        # Any insert exception may mean the write committed but its acknowledgement was
        # lost. Do not infer absence from a subsequent read or an exception class.
        self._repo.insert(doc)

    # -- read --------------------------------------------------------------

    def list_visible(self, ctx: ProjectContext) -> ListDashboardsResponse:
        docs = self._repo.list_visible(project_id=ctx.project_id, user_id=ctx.user.user_id)
        cache: dict[str, MetricScriptDocument | None] = {}
        dashboards = [self._to_response(doc, ctx, cache) for doc in docs]
        return ListDashboardsResponse(dashboards=dashboards, total=len(dashboards))

    def get(self, ctx: ProjectContext, dashboard_id: str) -> DashboardResponse:
        return self._to_response(self._get_visible(ctx, dashboard_id), ctx)

    @staticmethod
    def _template_response(template: DashboardTemplate) -> DashboardTemplateResponse:
        return DashboardTemplateResponse(
            template_id=template.template_id,
            name=template.name,
            description=template.description,
            panel_count=len(template.panels),
            panel_types=sorted({panel.type for panel in template.panels}),
        )

    def list_templates(self) -> ListDashboardTemplatesResponse:
        return ListDashboardTemplatesResponse(
            templates=[self._template_response(t) for t in TEMPLATES.values()]
        )

    def preview_template(
        self, ctx: ProjectContext, template_id: str
    ) -> DashboardTemplatePreviewResponse:
        """The panels creating a dashboard from ``template_id`` would copy in now.

        Writes nothing. Script panels are pinned to the shared script creation would reuse;
        when there is none, they name the starter script creation would add instead.
        """
        template = TEMPLATES.get(template_id)
        if template is None:
            raise HTTPException(
                status_code=404, detail=f"Unknown dashboard template '{template_id}'"
            )
        found: dict[str, MetricScriptDocument] = {}
        pins: dict[str, tuple[str, int]] = {}
        missing: list[str] = []
        for script_template, metrics in template.script_requirements().items():
            script = self._script_service.find_template_script(ctx, script_template, metrics)
            if script is not None and script.active_revision is not None:
                found[script_template] = script
                pins[script_template] = (script.script_id, script.active_revision)
            else:
                missing.append(script_template)
        panels = []
        for blueprint, model in zip(
            template.panels,
            instantiate_panels(template, pins, partial=True),
            strict=True,
        ):
            item = TemplatePreviewPanel(**model.model_dump())
            if blueprint.script_template is not None:
                script = found.get(blueprint.script_template)
                if script is None:
                    item.script_template_id = blueprint.script_template
                else:
                    item.script_name = script.name
                    item.latest_revision = script.active_revision
            panels.append(item)
        return DashboardTemplatePreviewResponse(
            template_id=template.template_id,
            name=template.name,
            description=template.description,
            panels=panels,
            scripts_to_create=[
                TemplateScriptToCreate(
                    template_id=key,
                    name=SCRIPT_TEMPLATES[key].name,
                    source=SCRIPT_TEMPLATES[key].source,
                )
                for key in missing
            ],
        )

    def create(self, ctx: ProjectContext, body: DashboardCreateRequest) -> DashboardResponse:
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
        doc = DashboardDocument(
            project_id=ctx.project_id,
            user_id=ctx.user.user_id,
            username=ctx.user.username,
            name=body.name,
            description=body.description,
            visibility=body.visibility,
            chip_id=body.chip_id,
            panels=panels,
        )
        self._insert(ctx, doc)
        return self._to_response(doc, ctx)

    def update(
        self, ctx: ProjectContext, dashboard_id: str, body: DashboardUpdateRequest
    ) -> DashboardResponse:
        doc = self._get_editable(ctx, dashboard_id)
        # The stored state this update replaces; the save below is a compare-and-set on it.
        # A caller's expected_version names the state it edited; reject before any pin write
        # when that state is gone, and the compare-and-set below covers the rest of the race.
        read_version = doc.version
        if body.expected_version is not None and body.expected_version != read_version:
            raise HTTPException(status_code=409, detail=STALE)
        old_pins = script_pins(doc.panels)
        visibility = body.visibility if body.visibility is not None else doc.visibility
        if body.panels is not None:
            self.validate_panels(ctx, body.panels, visibility)
            doc.panels = body.panels
        elif visibility != doc.visibility:
            self.validate_panels(ctx, doc.panels, visibility)
        else:
            validate_panel_configs(doc.panels)
        if body.name is not None:
            doc.name = body.name
        if body.description is not None:
            doc.description = body.description
        if body.visibility is not None:
            doc.visibility = body.visibility
        if "chip_id" in body.model_fields_set:
            # An explicit null clears the default chip.
            doc.chip_id = body.chip_id
        new_pins = script_pins(doc.panels)
        new_shared = doc.visibility == "project"
        # Metadata saves also update the shared flag and narrow surplus pins.
        repin = bool(old_pins or new_pins)
        writer = uuid4().hex
        if repin:
            self._add_pins(
                ctx,
                doc.dashboard_id,
                new_pins,
                shared=new_shared,
                writer=writer,
                claim=set(old_pins),
            )
        if not self._repo.save_if_unchanged(doc, version=read_version):
            if self._repo.get(project_id=ctx.project_id, dashboard_id=doc.dashboard_id) is None:
                self._scripts.clear_dashboard_pins(
                    project_id=ctx.project_id, dashboard_id=doc.dashboard_id
                )
            raise HTTPException(status_code=409, detail=STALE)
        if repin:
            for script_id in sorted(set(old_pins) | set(new_pins)):
                self._scripts.narrow_pin(
                    project_id=ctx.project_id,
                    script_id=script_id,
                    dashboard_id=doc.dashboard_id,
                    revisions=new_pins.get(script_id, []),
                    shared=new_shared,
                    writer=writer,
                )
        return self._to_response(doc, ctx)

    def delete(self, ctx: ProjectContext, dashboard_id: str) -> SuccessResponse:
        doc = self._get_editable(ctx, dashboard_id)
        self._repo.delete(doc)
        self._scripts.clear_dashboard_pins(project_id=ctx.project_id, dashboard_id=dashboard_id)
        return SuccessResponse(message="Dashboard deleted")

    def duplicate(self, ctx: ProjectContext, dashboard_id: str) -> DashboardResponse:
        source = self._get_visible(ctx, dashboard_id)
        copy = DashboardDocument(
            project_id=ctx.project_id,
            user_id=ctx.user.user_id,
            username=ctx.user.username,
            name=_copy_name(source.name),
            description=source.description,
            visibility="private",
            chip_id=source.chip_id,
            panels=[panel.model_copy(deep=True) for panel in source.panels],
        )
        validate_panel_configs(copy.panels)
        self._insert(ctx, copy)
        return self._to_response(copy, ctx)
