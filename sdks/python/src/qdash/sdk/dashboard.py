"""Metric scripts and dashboards, defined locally and saved through a QDash session.

A :class:`Script` is the text of a metric script with its name and settings; a
:class:`Dashboard` is a list of panels. Building either sends no request and never runs the
source: the server validates a script when it is saved and returns its metric catalog.
``QDash.scripts`` saves scripts and returns a :class:`~qdash.sdk.SavedScript` bound to the saved
revision, whose ``metric(id)`` gives the :class:`ScriptMetric` a dashboard panel pins.
``QDash.dashboards`` saves dashboards.

Metric script source is Python written against the ``qdash_metrics`` API, which exists only in
the server's metric worker; this module treats it as text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from qdash.client.services.models import (
    AbsolutePeriod,
    DashboardCreateRequest,
    DashboardPanelModel,
    DashboardUpdateRequest,
    MetricInfo,
    MetricScriptCreateRequest,
    MetricScriptPanelConfig,
    MetricScriptUpdateRequest,
    PanelLayoutModel,
    RelativePeriod,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from qdash.client.services.models import DashboardResponse

Visibility = Literal["private", "project"]
PeriodInput = int | RelativePeriod | AbsolutePeriod
LayoutInput = PanelLayoutModel | tuple[int, int, int, int]
ParamValue = bool | int | float | str

# Pair distances the API knows; a metric's declared hops are limited to these.
_KNOWN_HOPS = (1, 2)
# Default panel sizes (w, h) on the 12-column grid, as the dashboard editor uses them.
_PANEL_SIZES = {"metric_script": (6, 4), "markdown": (12, 2)}
_DEFAULT_SIZE = (6, 3)
_MAX_PANEL_ID = 64
_ID_UNSAFE = re.compile(r"[^a-z0-9_-]+")


class MetricScriptError(ValueError):
    """A saved script revision cannot back a panel: it is invalid or lacks the metric.

    ``script_id`` and ``revision`` name what was saved, so a caller can report or fix it.
    """

    def __init__(
        self,
        message: str,
        *,
        script_id: str,
        revision: int | None,
        diagnostics: Sequence[str] = (),
    ) -> None:
        super().__init__(message)
        self.script_id = script_id
        self.revision = revision
        self.diagnostics = list(diagnostics)


@dataclass(frozen=True)
class Script:
    """A metric script to save: its name, source text and optional settings.

    ``description`` and ``visibility`` left as None are not sent: a new script gets the
    server's defaults (empty, ``private``) and an update keeps the stored values.
    """

    name: str
    source: str
    description: str | None = None
    visibility: Visibility | None = None

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        name: str | None = None,
        description: str | None = None,
        visibility: Visibility | None = None,
    ) -> Script:
        """Read the source text of ``path``; the name defaults to the file's stem.

        The file is read as UTF-8 text, never imported or executed.
        """
        file = Path(path)
        return cls(
            name=name if name is not None else file.stem,
            source=file.read_text(encoding="utf-8"),
            description=description,
            visibility=visibility,
        )

    def _fields(self) -> dict[str, str]:
        fields = {"name": self.name, "source": self.source}
        if self.description is not None:
            fields["description"] = self.description
        if self.visibility is not None:
            fields["visibility"] = self.visibility
        return fields

    def create_request(self) -> MetricScriptCreateRequest:
        """The ``POST /metric-scripts`` body."""
        return MetricScriptCreateRequest.model_validate(self._fields())

    def update_request(self, *, expected_revision: int | None = None) -> MetricScriptUpdateRequest:
        """The ``PATCH /metric-scripts/{id}`` body; unchanged source adds no revision."""
        fields: dict[str, object] = dict(self._fields())
        if expected_revision is not None:
            fields["expected_revision"] = expected_revision
        return MetricScriptUpdateRequest.model_validate(fields)


@dataclass(frozen=True)
class ScriptMetric:
    """One metric of a saved, validated script revision, as its catalog declares it.

    Get it from :meth:`SavedScript.metric`; a dashboard panel built from it pins
    ``script_revision``, so later saves of the script do not change the panel.
    """

    script_id: str
    revision: int
    info: MetricInfo

    @property
    def id(self) -> str:
        return self.info.id

    @property
    def title(self) -> str:
        return self.info.title

    @property
    def unit(self) -> str:
        return self.info.unit

    @property
    def target(self) -> str:
        return str(self.info.target.value)

    @property
    def hops(self) -> list[int]:
        """Declared pair distances within the ones the API knows; both when none are."""
        declared = [hop for hop in (self.info.hops or _KNOWN_HOPS) if hop in _KNOWN_HOPS]
        return declared or list(_KNOWN_HOPS)


def _period(period: PeriodInput | None) -> RelativePeriod | AbsolutePeriod:
    if period is None:
        return RelativePeriod()
    if isinstance(period, bool) or not isinstance(period, (int, RelativePeriod, AbsolutePeriod)):
        raise TypeError("period must be a number of days, RelativePeriod or AbsolutePeriod")
    if isinstance(period, int):
        return RelativePeriod(days=period)
    return period


def _layout(layout: LayoutInput) -> PanelLayoutModel:
    if isinstance(layout, PanelLayoutModel):
        return layout
    x, y, w, h = layout
    return PanelLayoutModel(x=x, y=y, w=w, h=h)


class Dashboard:
    """A dashboard to save: name, settings and panels on a 12-column grid.

    ``add_metric`` and ``add_markdown`` place a new panel at the left edge below every
    existing panel, sized as the dashboard editor sizes new panels, and give it a readable ID
    unique within the dashboard. ``panels`` is a plain list of the API's panel models and may
    be edited directly. ``description``, ``visibility`` and ``chip_id`` left as None are not
    sent: a new dashboard gets the server's defaults and an update keeps the stored values.
    """

    def __init__(
        self,
        name: str,
        *,
        description: str | None = None,
        visibility: Visibility | None = None,
        chip_id: str | None = None,
        panels: Iterable[DashboardPanelModel] = (),
    ) -> None:
        self.name = name
        self.description = description
        self.visibility = visibility
        self.chip_id = chip_id
        self.panels: list[DashboardPanelModel] = list(panels)

    @classmethod
    def from_response(cls, response: DashboardResponse) -> Dashboard:
        """A definition holding a saved dashboard's settings and panels, ready to edit."""
        fields = {"panel_id", "type", "title", "layout", "config"}
        return cls(
            response.name,
            description=response.description,
            visibility=response.visibility.value,
            chip_id=response.chip_id,
            panels=[
                DashboardPanelModel.model_validate(panel.model_dump(include=fields))
                for panel in response.panels
            ],
        )

    def __repr__(self) -> str:
        return f"Dashboard(name={self.name!r}, panels={len(self.panels)})"

    def _next_layout(self, panel_type: str) -> PanelLayoutModel:
        bottom = max((panel.layout.y + panel.layout.h for panel in self.panels), default=0)
        w, h = _PANEL_SIZES.get(panel_type, _DEFAULT_SIZE)
        return PanelLayoutModel(x=0, y=bottom, w=w, h=h)

    def _panel_id(self, base: str) -> str:
        slug = _ID_UNSAFE.sub("-", base.lower()).strip("-") or "panel"
        taken = {panel.panel_id for panel in self.panels}
        candidate = slug[:_MAX_PANEL_ID]
        number = 2
        while candidate in taken:
            suffix = f"-{number}"
            candidate = f"{slug[: _MAX_PANEL_ID - len(suffix)]}{suffix}"
            number += 1
        return candidate

    def _add(self, panel: DashboardPanelModel) -> DashboardPanelModel:
        if any(existing.panel_id == panel.panel_id for existing in self.panels):
            raise ValueError(f"panel_id {panel.panel_id!r} is already on the dashboard")
        self.panels.append(panel)
        return panel

    def add_metric(
        self,
        metric: ScriptMetric,
        *,
        title: str | None = None,
        period: PeriodInput | None = None,
        params: Mapping[str, ParamValue] | None = None,
        view: Literal["map", "table"] = "map",
        direction: Literal["both", "forward", "reverse"] = "both",
        hops: Sequence[int] | None = None,
        layout: LayoutInput | None = None,
        panel_id: str | None = None,
    ) -> DashboardPanelModel:
        """Add a ``metric_script`` panel pinned to ``metric``'s script revision.

        ``period`` is a number of days back from evaluation time, or a period model; the
        default is the last 14 days. ``params`` override the metric's parameter defaults.
        ``hops`` defaults to the distances the metric declares. The server checks the script,
        revision, metric, parameters and hops when the dashboard is saved.
        """
        if not isinstance(metric, ScriptMetric):
            raise TypeError("metric must be a ScriptMetric from SavedScript.metric(...)")
        config = MetricScriptPanelConfig(
            script_id=metric.script_id,
            script_revision=metric.revision,
            metric_id=metric.id,
            period=_period(period),
            params=dict(params or {}),
            view=view,  # type: ignore[arg-type]
            direction=direction,  # type: ignore[arg-type]
            hops=list(hops) if hops is not None else metric.hops,
        )
        return self._add(
            DashboardPanelModel(
                panel_id=panel_id if panel_id is not None else self._panel_id(metric.id),
                type="metric_script",  # type: ignore[arg-type]
                title=title if title is not None else metric.title,
                layout=_layout(layout)
                if layout is not None
                else self._next_layout("metric_script"),
                config=config.model_dump(mode="json"),
            )
        )

    def add_markdown(
        self,
        content: str,
        *,
        title: str = "",
        layout: LayoutInput | None = None,
        panel_id: str | None = None,
    ) -> DashboardPanelModel:
        """Add a ``markdown`` note panel."""
        return self._add(
            DashboardPanelModel(
                panel_id=panel_id if panel_id is not None else self._panel_id("markdown"),
                type="markdown",  # type: ignore[arg-type]
                title=title,
                layout=_layout(layout) if layout is not None else self._next_layout("markdown"),
                config={"content": content},
            )
        )

    def _fields(self) -> dict[str, object]:
        fields: dict[str, object] = {"name": self.name, "panels": list(self.panels)}
        for key in ("description", "visibility", "chip_id"):
            value = getattr(self, key)
            if value is not None:
                fields[key] = value
        return fields

    def create_request(self) -> DashboardCreateRequest:
        """The ``POST /dashboards`` body."""
        return DashboardCreateRequest.model_validate(self._fields())

    def update_request(self, *, expected_version: int | None = None) -> DashboardUpdateRequest:
        """The ``PATCH /dashboards/{id}`` body; its panels replace the stored ones."""
        fields = self._fields()
        if expected_version is not None:
            fields["expected_version"] = expected_version
        return DashboardUpdateRequest.model_validate(fields)
