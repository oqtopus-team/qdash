# ruff: noqa: RUF001
"""Starter templates for dashboards.

A template is copied into a new dashboard at creation time. Later changes to a
template never touch dashboards that were created from it. ``metric_script`` panels of a
template name the metric script template they read; the dashboard service resolves it to a
project script and pins the panels to that script's active revision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from qdash.datamodel.dashboard import DashboardPanelModel, PanelLayoutModel, PanelType


@dataclass(frozen=True)
class TemplatePanel:
    """Panel blueprint without an ID; IDs are minted per created dashboard."""

    type: PanelType
    title: str
    layout: tuple[int, int, int, int]
    config: dict[str, Any] = field(default_factory=dict)
    script_template: str | None = None
    """Metric script template a ``metric_script`` panel reads."""


@dataclass(frozen=True)
class DashboardTemplate:
    """A named set of panels a dashboard can start from."""

    template_id: str
    name: str
    description: str
    panels: tuple[TemplatePanel, ...]

    def script_requirements(self) -> dict[str, set[str]]:
        """Metric IDs each referenced script template must define."""
        required: dict[str, set[str]] = {}
        for panel in self.panels:
            if panel.script_template is not None:
                required.setdefault(panel.script_template, set()).add(panel.config["metric_id"])
        return required


FREQUENCY_COLLISION_INTRO = """\
- Blue: within the limit. Orange: on the boundary. Red: the limit is exceeded.
- Grey: not evaluated, usually because an input is missing from the last 30 days.
- Type2C is a signed two-photon detuning in MHz, not a ratio.

Select a qubit or an edge to see the terms behind its verdict. Limits, the CNOT time and
fallback values are under **Advanced** in each panel's settings.
"""


COLLISION_TITLES = {
    "Type0A": "Type0A — Qubit quality",
    "Type0B": "Type0B — Excessive detuning",
    "Type1A": "Type1A — GE–GE proximity",
    "Type3A": "Type3A — EF–GE proximity",
    "Type1C": "Type1C — CR causes GE",
    "Type2C": "Type2C — Two-photon e0–f1 detuning (screening)",
}


def _collision(kind: str, x: int, y: int) -> TemplatePanel:
    return TemplatePanel(
        type="metric_script",
        title=COLLISION_TITLES[kind],
        layout=(x, y, 6, 4),
        config={
            "metric_id": kind,
            "period": {"kind": "relative", "days": 30},
            "params": {},
            "view": "map",
            "direction": "both",
            "hops": [1, 2],
        },
        script_template="collision",
    )


FREQUENCY_COLLISION_MAP = DashboardTemplate(
    template_id="frequency-collision-map",
    name="Frequency Collision Map",
    description=(
        "Qubit quality, detuning and the main cross-resonance collision checks "
        "on the chip topology, with a qubit frequency map for context"
    ),
    panels=(
        # Maps first; the reading guide fills the slot beside Type2C, which it explains,
        # and comes last on narrow screens where panels stack.
        TemplatePanel(
            type="qubit_metric",
            title="Qubit frequency",
            layout=(0, 0, 6, 4),
            config={"metric": "qubit_frequency"},
        ),
        _collision("Type0A", 6, 0),
        _collision("Type0B", 0, 4),
        _collision("Type1A", 6, 4),
        _collision("Type3A", 0, 8),
        _collision("Type1C", 6, 8),
        _collision("Type2C", 0, 12),
        TemplatePanel(
            type="markdown",
            title="Reading the collision maps",
            layout=(6, 12, 6, 4),
            config={"content": FREQUENCY_COLLISION_INTRO},
        ),
    ),
)

TEMPLATES: dict[str, DashboardTemplate] = {
    FREQUENCY_COLLISION_MAP.template_id: FREQUENCY_COLLISION_MAP,
}


def instantiate_panels(
    template: DashboardTemplate,
    scripts: dict[str, tuple[str, int]] | None = None,
    *,
    partial: bool = False,
) -> list[DashboardPanelModel]:
    """Copy a template's panels with fresh panel IDs, in the template's order.

    Args:
        template: Template to copy.
        scripts: Script template ID → ``(script_id, revision)`` the metric_script panels
            are pinned to.
        partial: Leave a metric_script panel without a script reference when ``scripts``
            has no entry for its script template, as a preview does, instead of failing.
    """
    panels = []
    for panel in template.panels:
        config = dict(panel.config)
        if panel.script_template is not None:
            pinned = (scripts or {}).get(panel.script_template)
            if pinned is not None:
                script_id, revision = pinned
                config = {"script_id": script_id, "script_revision": revision, **config}
            elif not partial:
                raise KeyError(panel.script_template)
        panels.append(
            DashboardPanelModel(
                panel_id=uuid4().hex,
                type=panel.type,
                title=panel.title,
                layout=PanelLayoutModel(
                    x=panel.layout[0], y=panel.layout[1], w=panel.layout[2], h=panel.layout[3]
                ),
                config=config,
            )
        )
    return panels
