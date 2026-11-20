"""Schemas for metric script endpoints."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from qdash.datamodel.metric_script import (
    MetricCell,
    MetricInfo,
    MetricLegend,
    MetricPeriod,
    MetricScriptRevision,
    MetricScriptStatus,
    MetricScriptVisibility,
    ScriptDiagnostic,
    StrictRevision,
    default_period,
)

MAX_NAME_LENGTH = 120
MAX_DESCRIPTION_LENGTH = 2000
MAX_SOURCE_BYTES = 256 * 1024
MAX_REVISIONS = 50

ParamValues = dict[str, bool | int | float | str]


class MetricScriptCreateRequest(BaseModel):
    """Body for creating a script from source text or from a template."""

    name: str = Field(..., min_length=1, max_length=MAX_NAME_LENGTH)
    description: str = Field(default="", max_length=MAX_DESCRIPTION_LENGTH)
    visibility: MetricScriptVisibility = "private"
    source: str | None = Field(
        default=None, max_length=MAX_SOURCE_BYTES, description="Python source (≤ 256 KiB)"
    )
    template_id: str | None = Field(
        default=None, max_length=100, description="Template to copy when source is omitted"
    )


class MetricScriptUpdateRequest(BaseModel):
    """Body for updating a script; a new ``source`` is validated and saved as a revision."""

    name: str | None = Field(default=None, min_length=1, max_length=MAX_NAME_LENGTH)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)
    visibility: MetricScriptVisibility | None = None
    source: str | None = Field(default=None, max_length=MAX_SOURCE_BYTES)
    expected_revision: StrictRevision | None = Field(
        default=None,
        description="Reject with 409 unless the script is still at this revision",
    )


class MetricScriptValidateRequest(BaseModel):
    """Body for validating source text without saving it."""

    source: str = Field(..., max_length=MAX_SOURCE_BYTES)


class MetricScriptValidateResponse(BaseModel):
    """Validation outcome."""

    ok: bool
    metrics: list[MetricInfo]
    diagnostics: list[ScriptDiagnostic]


class MetricScriptDraftEvaluateRequest(BaseModel):
    """Body for previewing unsaved source text on a chip."""

    source: str = Field(..., max_length=MAX_SOURCE_BYTES)
    metric_id: str = Field(..., min_length=1, max_length=200)
    chip_id: str = Field(..., min_length=1, max_length=100)
    period: MetricPeriod = Field(default_factory=default_period)
    params: ParamValues = Field(default_factory=dict)


class MetricScriptEvaluateRequest(BaseModel):
    """Body for evaluating a saved revision on a chip."""

    metric_id: str = Field(..., min_length=1, max_length=200)
    chip_id: str = Field(..., min_length=1, max_length=100)
    period: MetricPeriod = Field(default_factory=default_period)
    params: ParamValues = Field(default_factory=dict)
    revision: StrictRevision | None = Field(
        default=None, description="Revision to evaluate; defaults to the active one"
    )


class MetricScriptEvaluateResponse(BaseModel):
    """Cells of one metric over a chip."""

    script_id: str | None = Field(..., description="None for a draft preview")
    revision: int | None = Field(..., description="Evaluated revision; None for a draft")
    metric: MetricInfo
    chip_id: str
    start: datetime = Field(..., description="Resolved period start")
    end: datetime = Field(..., description="Resolved period end")
    params: dict[str, Any] = Field(..., description="Effective parameter values")
    legend: MetricLegend | None
    cells: list[MetricCell]
    log: str = Field(default="", description="Script output (bounded to 16 KiB)")
    evaluated_at: datetime
    truncated: bool = Field(
        default=False,
        description="The log was truncated or a history span was clamped to the broker cap",
    )


class MetricScriptSummary(BaseModel):
    """A script in the list view (no source)."""

    script_id: str
    project_id: str
    name: str
    description: str
    visibility: MetricScriptVisibility
    status: MetricScriptStatus
    revision: int
    active_revision: int | None
    metrics: list[MetricInfo]
    template_id: str | None
    owner_username: str
    owner_user_id: str | None
    can_edit: bool = Field(..., description="Whether the caller may update or delete it")
    created_at: datetime
    updated_at: datetime


class MetricScriptResponse(MetricScriptSummary):
    """A script with its source, last-good source and revision list."""

    source: str
    active_source: str | None
    diagnostics: list[ScriptDiagnostic]
    revisions: list[MetricScriptRevision]


class ListMetricScriptsResponse(BaseModel):
    """Scripts visible to the caller."""

    scripts: list[MetricScriptSummary]
    total: int


class MetricScriptTemplateResponse(BaseModel):
    """A starter script."""

    template_id: str
    name: str
    description: str
    source: str


class ListMetricScriptTemplatesResponse(BaseModel):
    """Available starter scripts."""

    templates: list[MetricScriptTemplateResponse]


class MetricCatalogEntry(BaseModel):
    """A metric scripts can read with ``ctx.data[name]``."""

    name: str
    title: str
    unit: str
    scale: float
    description: str


class MetricScriptCatalogResponse(BaseModel):
    """The data catalog of ``ctx.data``."""

    qubit_metrics: list[MetricCatalogEntry]
    coupling_metrics: list[MetricCatalogEntry]
