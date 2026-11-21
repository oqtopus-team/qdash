"""Service layer for metric scripts: persistence, validation and evaluation."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, NoReturn

from fastapi import HTTPException

from qdash.api.lib.python_format import format_source_for_save
from qdash.api.metric_runtime import executor
from qdash.api.metric_runtime.broker import (
    MetricDataBroker,
    metrics_catalog,
    topology_payload,
)
from qdash.api.metric_runtime.executor import (
    MetricRuntimeError,
    QueueFullError,
    RunnerUnavailableError,
    ScriptFailure,
    WorkerFailure,
)
from qdash.api.metric_runtime.sdk import Parameter, resolve_parameters
from qdash.api.metric_runtime.template_library import TEMPLATES
from qdash.api.schemas.metric_script import (
    MAX_NAME_LENGTH,
    MAX_REVISIONS,
    MAX_SOURCE_BYTES,
    ListMetricScriptsResponse,
    ListMetricScriptTemplatesResponse,
    MetricCatalogEntry,
    MetricScriptCatalogResponse,
    MetricScriptCreateRequest,
    MetricScriptDraftEvaluateRequest,
    MetricScriptEvaluateRequest,
    MetricScriptEvaluateResponse,
    MetricScriptResponse,
    MetricScriptSummary,
    MetricScriptTemplateResponse,
    MetricScriptUpdateRequest,
    MetricScriptValidateResponse,
)
from qdash.api.schemas.success import SuccessResponse
from qdash.common.config.topology import load_topology
from qdash.common.utils.datetime import now
from qdash.datamodel.metric_script import (
    AbsolutePeriod,
    MetricCell,
    MetricInfo,
    MetricLegend,
    MetricScriptRevision,
    RelativePeriod,
    ScriptDiagnostic,
    resolve_period,
)
from qdash.datamodel.project import ProjectRole
from qdash.dbmodel.metric_script import MetricScriptDocument

if TYPE_CHECKING:
    from qdash.api.lib.project import ProjectContext
    from qdash.api.services.metrics_service import MetricsService
    from qdash.repository.chip import MongoChipRepository
    from qdash.repository.dashboard import MongoDashboardRepository
    from qdash.repository.metric_script import MongoMetricScriptRepository
    from qdash.repository.task_result_history import MongoTaskResultHistoryRepository

logger = logging.getLogger(__name__)

NOT_FOUND = "Metric script not found"
COPY_SUFFIX = " (copy)"
CONFLICT = "Script was changed by another save; reload it before saving"


@dataclass
class ValidationResult:
    """Outcome of compiling a script in ``catalog`` mode."""

    ok: bool
    metrics: list[MetricInfo] = field(default_factory=list)
    diagnostics: list[ScriptDiagnostic] = field(default_factory=list)


_template_validation_cache: dict[str, ValidationResult] = {}


def _copy_name(name: str) -> str:
    return f"{name[: MAX_NAME_LENGTH - len(COPY_SUFFIX)]}{COPY_SUFFIX}"


def _check_source_size(source: str) -> None:
    if len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise HTTPException(
            status_code=422,
            detail=f"Script source exceeds {MAX_SOURCE_BYTES // 1024} KiB",
        )


def _source_to_store(source: str) -> str:
    """Check the size of ``source`` and return the text a save stores.

    The stored text is the source formatted with Ruff; a source Ruff cannot parse, or a
    formatter failure, stores the source as written (see ``format_source_for_save``).
    """
    _check_source_size(source)
    formatted = format_source_for_save(source)
    if len(formatted.encode("utf-8")) > MAX_SOURCE_BYTES:
        return source
    return formatted


def _raise_runtime(exc: MetricRuntimeError) -> NoReturn:
    if isinstance(exc, QueueFullError):
        raise HTTPException(status_code=429, detail="Metric script evaluation queue is full")
    if isinstance(exc, RunnerUnavailableError):
        raise HTTPException(
            status_code=503,
            detail={"message": exc.message, "diagnostics": [], "log": ""},
        )
    raise HTTPException(
        status_code=422,
        detail={
            "message": exc.message,
            "diagnostics": exc.diagnostics,
            "log": exc.log,
        },
    )


def validate_source(source: str) -> ValidationResult:
    """Compile ``source`` in a worker and return its catalog or diagnostics.

    Nothing is returned when the script did not run, so a save never records an invalid
    revision because the runner was busy or down.

    Raises:
        HTTPException: 429 when the evaluation queue is full, 503 when the metric runner
            is not available.
    """
    is_template = any(source == template.source for template in TEMPLATES.values())
    key = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if is_template and key in _template_validation_cache:
        return _template_validation_cache[key]
    try:
        outcome = executor.catalog(source)
    except (QueueFullError, RunnerUnavailableError) as exc:
        _raise_runtime(exc)
    except ScriptFailure as exc:
        diagnostics = [ScriptDiagnostic.model_validate(d) for d in exc.diagnostics] or [
            ScriptDiagnostic(message=exc.message)
        ]
        return ValidationResult(ok=False, diagnostics=diagnostics)
    except WorkerFailure as exc:
        return ValidationResult(ok=False, diagnostics=[ScriptDiagnostic(message=exc.message)])
    result = ValidationResult(
        ok=True,
        metrics=[MetricInfo.model_validate(m) for m in outcome.result.get("metrics", [])],
    )
    if is_template:
        _template_validation_cache[key] = result
    return result


def metric_parameters(metric: MetricInfo) -> dict[str, Parameter]:
    """Rebuild the declared parameters of a stored catalog entry."""
    return {
        name: Parameter.from_metadata(info.model_dump()) for name, info in metric.parameters.items()
    }


def check_params(metric: MetricInfo, params: dict[str, Any]) -> dict[str, Any]:
    """Validate overrides against a metric's declared parameters.

    Raises:
        ValueError: On unknown names or invalid values.
    """
    return resolve_parameters(metric_parameters(metric), params)


class MetricScriptService:
    """CRUD, sharing rules, validation and evaluation of metric scripts."""

    def __init__(
        self,
        metric_script_repository: MongoMetricScriptRepository,
        dashboard_repository: MongoDashboardRepository,
        chip_repository: MongoChipRepository,
        metrics_service: MetricsService,
        task_result_repository: MongoTaskResultHistoryRepository,
    ) -> None:
        self._repo = metric_script_repository
        self._dashboards = dashboard_repository
        self._chips = chip_repository
        self._metrics = metrics_service
        self._task_results = task_result_repository

    # -- permissions -------------------------------------------------------

    @staticmethod
    def is_owner(doc: MetricScriptDocument, ctx: ProjectContext) -> bool:
        return doc.user_id is not None and doc.user_id == ctx.user.user_id

    @classmethod
    def can_view(cls, doc: MetricScriptDocument, ctx: ProjectContext) -> bool:
        return doc.visibility == "project" or cls.is_owner(doc, ctx)

    @classmethod
    def can_edit(cls, doc: MetricScriptDocument, ctx: ProjectContext) -> bool:
        return cls.is_owner(doc, ctx) or ctx.role == ProjectRole.OWNER

    def find_visible(self, ctx: ProjectContext, script_id: str) -> MetricScriptDocument | None:
        """Return the script if it exists in the project and the caller may view it."""
        doc = self._repo.get(project_id=ctx.project_id, script_id=script_id)
        if doc is None or not self.can_view(doc, ctx):
            return None
        return doc

    def _get_visible(self, ctx: ProjectContext, script_id: str) -> MetricScriptDocument:
        doc = self.find_visible(ctx, script_id)
        if doc is None:
            raise HTTPException(status_code=404, detail=NOT_FOUND)
        return doc

    def _get_editable(self, ctx: ProjectContext, script_id: str) -> MetricScriptDocument:
        doc = self._get_visible(ctx, script_id)
        if not self.can_edit(doc, ctx):
            raise HTTPException(
                status_code=403,
                detail="Only the script owner or a project owner can modify this script",
            )
        return doc

    # -- responses ---------------------------------------------------------

    @classmethod
    def _summary_fields(cls, doc: MetricScriptDocument, ctx: ProjectContext) -> dict[str, Any]:
        return {
            "script_id": doc.script_id,
            "project_id": doc.project_id,
            "name": doc.name,
            "description": doc.description,
            "visibility": doc.visibility,
            "status": doc.status,
            "revision": doc.revision,
            "active_revision": doc.active_revision,
            "metrics": doc.metrics,
            "template_id": doc.template_id,
            "owner_username": doc.username,
            "owner_user_id": doc.user_id,
            "can_edit": cls.can_edit(doc, ctx),
            "created_at": doc.system_info.created_at,
            "updated_at": doc.system_info.updated_at,
        }

    @classmethod
    def _to_response(cls, doc: MetricScriptDocument, ctx: ProjectContext) -> MetricScriptResponse:
        return MetricScriptResponse(
            **cls._summary_fields(doc, ctx),
            source=doc.source,
            active_source=doc.active_source,
            diagnostics=doc.diagnostics,
            revisions=doc.revisions,
        )

    # -- read --------------------------------------------------------------

    def list_visible(self, ctx: ProjectContext) -> ListMetricScriptsResponse:
        docs = self._repo.list_visible(project_id=ctx.project_id, user_id=ctx.user.user_id)
        scripts = [MetricScriptSummary(**self._summary_fields(doc, ctx)) for doc in docs]
        return ListMetricScriptsResponse(scripts=scripts, total=len(scripts))

    def get(self, ctx: ProjectContext, script_id: str) -> MetricScriptResponse:
        return self._to_response(self._get_visible(ctx, script_id), ctx)

    @staticmethod
    def list_templates() -> ListMetricScriptTemplatesResponse:
        return ListMetricScriptTemplatesResponse(
            templates=[
                MetricScriptTemplateResponse(
                    template_id=t.template_id,
                    name=t.name,
                    description=t.description,
                    source=t.source,
                )
                for t in TEMPLATES.values()
            ]
        )

    @staticmethod
    def catalog() -> MetricScriptCatalogResponse:
        data = metrics_catalog()

        def entries(section: dict[str, dict[str, Any]]) -> list[MetricCatalogEntry]:
            return [MetricCatalogEntry(name=name, **meta) for name, meta in section.items()]

        return MetricScriptCatalogResponse(
            qubit_metrics=entries(data["qubit_metrics"]),
            coupling_metrics=entries(data["coupling_metrics"]),
        )

    # -- validation and revisions -------------------------------------------

    @staticmethod
    def validate(source: str) -> MetricScriptValidateResponse:
        _check_source_size(source)
        result = validate_source(source)
        return MetricScriptValidateResponse(
            ok=result.ok, metrics=result.metrics, diagnostics=result.diagnostics
        )

    @staticmethod
    def _apply_source(doc: MetricScriptDocument, source: str, result: ValidationResult) -> None:
        """Record ``source`` as a new revision; advance ``active_*`` only when it validated.

        Old revisions beyond ``MAX_REVISIONS`` are evicted, except the new and active ones
        and every revision in ``doc.pins``. The caller saves ``doc`` with a compare-and-set
        on its ``version``, so the pins read here are the pins of the state it replaces.

        Raises:
            HTTPException: 409 when the pinned revisions leave no room for the new one.
        """
        revision = doc.revision + 1
        doc.revision = revision
        doc.source = source
        doc.status = "valid" if result.ok else "invalid"
        doc.diagnostics = result.diagnostics
        doc.revisions.append(
            MetricScriptRevision(
                revision=revision,
                source=source,
                created_at=now(),
                status=doc.status,
                metrics=result.metrics if result.ok else [],
            )
        )
        if result.ok:
            doc.active_revision = revision
            doc.active_source = source
            doc.metrics = result.metrics
        pinned = doc.pinned_revisions()
        keep = {revision, *pinned}
        if doc.active_revision is not None:
            keep.add(doc.active_revision)
        excess = len(doc.revisions) - MAX_REVISIONS
        if excess > 0:
            # Revisions are stored oldest first: evict the oldest unprotected ones.
            evict = {r.revision for r in doc.revisions if r.revision not in keep}
            evict = set(sorted(evict)[:excess])
            doc.revisions = [r for r in doc.revisions if r.revision not in evict]
        if len(doc.revisions) > MAX_REVISIONS:
            # Everything left is pinned: refuse rather than grow the document without bound.
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Dashboards pin {len(pinned)} revisions of this script, which leaves no "
                    f"room in its {MAX_REVISIONS}-revision history; unpin dashboards from old "
                    "revisions before saving"
                ),
            )

    # -- write -------------------------------------------------------------

    def create_document(
        self,
        ctx: ProjectContext,
        *,
        name: str,
        description: str,
        visibility: str,
        source: str,
        template_id: str | None = None,
    ) -> MetricScriptDocument:
        """Format, validate and insert a new script owned by the caller."""
        source = _source_to_store(source)
        result = validate_source(source)
        doc = MetricScriptDocument(
            project_id=ctx.project_id,
            user_id=ctx.user.user_id,
            username=ctx.user.username,
            name=name,
            description=description,
            visibility="project" if visibility == "project" else "private",
            source=source,
            revision=0,
            status="invalid",
            template_id=template_id,
        )
        self._apply_source(doc, source, result)
        self._repo.insert(doc)
        return doc

    def create(self, ctx: ProjectContext, body: MetricScriptCreateRequest) -> MetricScriptResponse:
        source = body.source
        template_id = None
        if source is None:
            if body.template_id is None:
                raise HTTPException(status_code=422, detail="Provide source or template_id")
            template = TEMPLATES.get(body.template_id)
            if template is None:
                raise HTTPException(
                    status_code=422, detail=f"Unknown metric script template '{body.template_id}'"
                )
            source = template.source
            template_id = template.template_id
        doc = self.create_document(
            ctx,
            name=body.name,
            description=body.description,
            visibility=body.visibility,
            source=source,
            template_id=template_id,
        )
        return self._to_response(doc, ctx)

    def find_template_script(
        self, ctx: ProjectContext, template_id: str, required_metrics: set[str]
    ) -> MetricScriptDocument | None:
        """The project's shared script from ``template_id`` that defines ``required_metrics``.

        Reads only; ``ensure_template_script`` reuses the same choice.
        """
        for doc in self._repo.find_by_template(project_id=ctx.project_id, template_id=template_id):
            if doc.visibility != "project" or doc.active_revision is None:
                continue
            if required_metrics <= {metric.id for metric in doc.metrics}:
                return doc
        return None

    def ensure_template_script(
        self, ctx: ProjectContext, template_id: str, required_metrics: set[str]
    ) -> MetricScriptDocument:
        """Reuse the project's shared script from ``template_id`` or create one.

        A script qualifies when it is project-visible and its active revision still defines
        every metric in ``required_metrics``.
        """
        existing = self.find_template_script(ctx, template_id, required_metrics)
        if existing is not None:
            return existing
        template = TEMPLATES[template_id]
        doc = self.create_document(
            ctx,
            name=template.name,
            description=template.description,
            visibility="project",
            source=template.source,
            template_id=template.template_id,
        )
        if doc.active_revision is None:
            raise HTTPException(
                status_code=500, detail=f"Metric script template '{template_id}' is invalid"
            )
        return doc

    def _pinning_dashboards(
        self, ctx: ProjectContext, doc: MetricScriptDocument, *, shared_only: bool
    ) -> list[str]:
        """Describe the dashboards that pin ``doc`` for an error message.

        The decision comes from ``doc.pins``; dashboard documents only supply names. Private
        dashboards of other members are counted, not named.
        """
        pinned = {
            dashboard_id
            for dashboard_id, pin in doc.pins.items()
            if pin.revisions and (pin.shared or not shared_only)
        }
        dashboards = {
            d.dashboard_id: d
            for d in self._dashboards.find_referencing_script(
                project_id=ctx.project_id, script_id=doc.script_id
            )
        }
        names: list[str] = []
        hidden = 0
        for dashboard_id in sorted(pinned):
            dashboard = dashboards.get(dashboard_id)
            if dashboard is None:
                names.append(f"({dashboard_id})")
            elif dashboard.visibility == "project" or dashboard.user_id == ctx.user.user_id:
                names.append(f"'{dashboard.name}' ({dashboard_id})")
            else:
                hidden += 1
        if hidden:
            names.append(f"{hidden} private dashboard(s) of other members")
        return names

    def update(
        self, ctx: ProjectContext, script_id: str, body: MetricScriptUpdateRequest
    ) -> MetricScriptResponse:
        doc = self._get_editable(ctx, script_id)
        # The stored state this update builds on; the save below is a compare-and-set on it.
        # ``version`` also covers pins, so the pin checks below hold for the state replaced.
        read_version = doc.version
        if body.expected_revision is not None and body.expected_revision != doc.revision:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Script was saved as revision {doc.revision} since revision "
                    f"{body.expected_revision}; reload it before saving"
                ),
            )
        if body.visibility == "private" and doc.visibility == "project":
            if any(pin.shared and pin.revisions for pin in doc.pins.values()):
                names = ", ".join(self._pinning_dashboards(ctx, doc, shared_only=True))
                raise HTTPException(
                    status_code=409,
                    detail=f"Project dashboards use this script: {names}; it must stay shared",
                )
        if body.source is not None and body.source != doc.source:
            source = _source_to_store(body.source)
            # Text that formats to the stored source is not a new revision.
            if source != doc.source:
                result = validate_source(source)
                self._apply_source(doc, source, result)
        if body.name is not None:
            doc.name = body.name
        if body.description is not None:
            doc.description = body.description
        if body.visibility is not None:
            doc.visibility = body.visibility
        if not self._repo.save_if_unchanged(doc, version=read_version):
            raise HTTPException(status_code=409, detail=CONFLICT)
        return self._to_response(doc, ctx)

    def delete(self, ctx: ProjectContext, script_id: str) -> SuccessResponse:
        doc = self._get_editable(ctx, script_id)
        if any(pin.revisions for pin in doc.pins.values()):
            names = ", ".join(self._pinning_dashboards(ctx, doc, shared_only=False))
            raise HTTPException(
                status_code=409, detail=f"Dashboards still use this script: {names}"
            )
        # A dashboard that pinned the script after the read above changed its version.
        if not self._repo.delete_if_unchanged(doc, version=doc.version):
            raise HTTPException(status_code=409, detail=CONFLICT)
        return SuccessResponse(message="Metric script deleted")

    def copy(self, ctx: ProjectContext, script_id: str) -> MetricScriptResponse:
        source = self._get_visible(ctx, script_id)
        if source.active_source is None or source.active_revision is None:
            raise HTTPException(status_code=422, detail="The script has no valid revision to copy")
        doc = MetricScriptDocument(
            project_id=ctx.project_id,
            user_id=ctx.user.user_id,
            username=ctx.user.username,
            name=_copy_name(source.name),
            description=source.description,
            visibility="private",
            source=source.active_source,
            revision=0,
            status="invalid",
        )
        self._apply_source(
            doc,
            source.active_source,
            ValidationResult(ok=True, metrics=list(source.metrics)),
        )
        self._repo.insert(doc)
        return self._to_response(doc, ctx)

    # -- evaluation --------------------------------------------------------

    def _topology(self, project_id: str, chip_id: str) -> dict[str, Any]:
        chip = self._chips.find_one_document({"project_id": project_id, "chip_id": chip_id})
        if chip is None:
            raise HTTPException(status_code=404, detail=f"Chip '{chip_id}' not found")
        if not chip.topology_id:
            raise HTTPException(
                status_code=409,
                detail=f"Chip '{chip_id}' has no topology; set its topology to evaluate metrics",
            )
        try:
            definition = load_topology(chip.topology_id)
        except Exception as exc:
            logger.warning("Failed to load topology %s: %s", chip.topology_id, exc)
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Topology '{chip.topology_id}' of chip '{chip_id}' could not be loaded; "
                    "metric scripts need a valid topology"
                ),
            ) from exc
        return topology_payload(definition)

    def _evaluate(
        self,
        ctx: ProjectContext,
        *,
        source: str,
        metric_id: str,
        chip_id: str,
        period: RelativePeriod | AbsolutePeriod,
        params: dict[str, Any],
        script_id: str | None,
        revision: int | None,
    ) -> MetricScriptEvaluateResponse:
        start, end = resolve_period(period, now())
        topology = self._topology(ctx.project_id, chip_id)
        broker = MetricDataBroker(
            project_id=ctx.project_id,
            username=ctx.user.username,
            chip_id=chip_id,
            start=start,
            end=end,
            topology=topology,
            metrics_service=self._metrics,
            task_result_repository=self._task_results,
        )
        try:
            outcome = executor.evaluate(
                source=source,
                metric_id=metric_id,
                chip_id=chip_id,
                start=start.isoformat(),
                end=end.isoformat(),
                params=params,
                broker=broker,
            )
        except MetricRuntimeError as exc:
            _raise_runtime(exc)
        result = outcome.result
        notices = [str(notice) for notice in result.get("notices") or []]
        log = "".join(f"[notice] {notice}\n" for notice in notices) + outcome.log
        legend = result.get("legend")
        return MetricScriptEvaluateResponse(
            script_id=script_id,
            revision=revision,
            metric=MetricInfo.model_validate(result["metric"]),
            chip_id=chip_id,
            start=start,
            end=end,
            params=dict(result.get("params") or {}),
            legend=MetricLegend.model_validate(legend) if legend else None,
            cells=[MetricCell.model_validate(cell) for cell in result.get("cells", [])],
            log=log,
            evaluated_at=now(),
            truncated=outcome.log_truncated or bool(notices),
        )

    def evaluate_draft(
        self, ctx: ProjectContext, body: MetricScriptDraftEvaluateRequest
    ) -> MetricScriptEvaluateResponse:
        _check_source_size(body.source)
        return self._evaluate(
            ctx,
            source=body.source,
            metric_id=body.metric_id,
            chip_id=body.chip_id,
            period=body.period,
            params=dict(body.params),
            script_id=None,
            revision=None,
        )

    def evaluate_saved(
        self, ctx: ProjectContext, script_id: str, body: MetricScriptEvaluateRequest
    ) -> MetricScriptEvaluateResponse:
        doc = self._get_visible(ctx, script_id)
        number = body.revision if body.revision is not None else doc.active_revision
        if number is None:
            raise HTTPException(status_code=422, detail="The script has no valid revision")
        revision = doc.find_revision(number)
        if revision is None:
            raise HTTPException(
                status_code=404, detail=f"Revision {number} of this script was not found"
            )
        if revision.status != "valid":
            raise HTTPException(
                status_code=422, detail=f"Revision {number} did not validate and cannot run"
            )
        metric = next((m for m in revision.metrics if m.id == body.metric_id), None)
        if metric is None:
            known = ", ".join(m.id for m in revision.metrics)
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Metric '{body.metric_id}' is not defined in revision {number}; "
                    f"expected one of: {known}"
                ),
            )
        try:
            params = check_params(metric, dict(body.params))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return self._evaluate(
            ctx,
            source=revision.source,
            metric_id=metric.id,
            chip_id=body.chip_id,
            period=body.period,
            params=params,
            script_id=doc.script_id,
            revision=number,
        )
