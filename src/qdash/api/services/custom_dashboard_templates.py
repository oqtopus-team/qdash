"""Starter templates for custom dashboards.

A template is copied into a new dashboard at creation time. Later changes to a
template never touch dashboards that were created from it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from qdash.api.services.collision_analysis import CHECKS
from qdash.datamodel.custom_dashboard import DashboardPanelModel, PanelLayoutModel, PanelType


@dataclass(frozen=True)
class TemplatePanel:
    """Panel blueprint without an ID; IDs are minted per created dashboard."""

    type: PanelType
    title: str
    layout: tuple[int, int, int, int]
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DashboardTemplate:
    """A named set of panels a dashboard can start from."""

    template_id: str
    name: str
    description: str
    panels: tuple[TemplatePanel, ...]


FREQUENCY_COLLISION_INTRO = """\
## Frequency collision map

Each map evaluates one qubex collision condition from the chip's current qubit frequencies,
anharmonicities, resonator frequencies, coherence times and coupling strengths.

- Blue: below the limit. Orange: on the boundary. Red: the limit is exceeded.
- Grey: not evaluated, usually because an input is missing.
- Type2C shows a signed two-photon detuning in MHz instead of a ratio.

Select a qubit or an edge for the terms behind the verdict. Adjust the limits, the CNOT time and
the fallback values from each panel's settings; they are saved with this dashboard.
"""


def _collision(kind: str, x: int, y: int) -> TemplatePanel:
    return TemplatePanel(
        type="collision_check",
        title=CHECKS[kind].title,
        layout=(x, y, 6, 4),
        config={"check": kind, "params": {}, "hops": [1, 2]},
    )


FREQUENCY_COLLISION_MAP = DashboardTemplate(
    template_id="frequency-collision-map",
    name="Frequency Collision Map",
    description=(
        "Qubit quality, detuning and the main cross-resonance collision checks "
        "on the chip topology, with a qubit frequency map for context"
    ),
    panels=(
        TemplatePanel(
            type="markdown",
            title="How to read this dashboard",
            layout=(0, 0, 12, 2),
            config={"content": FREQUENCY_COLLISION_INTRO},
        ),
        TemplatePanel(
            type="qubit_metric",
            title="Qubit frequency",
            layout=(0, 2, 6, 4),
            config={"metric": "qubit_frequency"},
        ),
        _collision("Type0A", 6, 2),
        _collision("Type0B", 0, 6),
        _collision("Type1A", 6, 6),
        _collision("Type3A", 0, 10),
        _collision("Type1C", 6, 10),
        _collision("Type2C", 0, 14),
    ),
)

TEMPLATES: dict[str, DashboardTemplate] = {
    FREQUENCY_COLLISION_MAP.template_id: FREQUENCY_COLLISION_MAP,
}


def instantiate_panels(template: DashboardTemplate) -> list[DashboardPanelModel]:
    """Copy a template's panels with fresh panel IDs."""
    return [
        DashboardPanelModel(
            panel_id=uuid4().hex,
            type=panel.type,
            title=panel.title,
            layout=PanelLayoutModel(
                x=panel.layout[0], y=panel.layout[1], w=panel.layout[2], h=panel.layout[3]
            ),
            config=dict(panel.config),
        )
        for panel in template.panels
    ]
