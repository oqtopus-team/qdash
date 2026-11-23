"""Starter metric scripts shipped with QDash (``templates/*.py``)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


@dataclass(frozen=True)
class MetricScriptTemplate:
    """A starter script; creating a script from it copies the source."""

    template_id: str
    name: str
    description: str
    filename: str

    @property
    def source(self) -> str:
        return _read(self.filename)


@cache
def _read(filename: str) -> str:
    return (TEMPLATE_DIR / filename).read_text(encoding="utf-8")


TEMPLATES: dict[str, MetricScriptTemplate] = {
    template.template_id: template
    for template in (
        MetricScriptTemplate(
            template_id="getting_started",
            name="Getting started",
            description=(
                "Coherence ratio, neighbour frequency gap and a history mean: "
                "the latest-value, topology and history APIs in three small metrics"
            ),
            filename="getting_started.py",
        ),
        MetricScriptTemplate(
            template_id="collision",
            name="Frequency collision checks",
            description=(
                "Qubex-compatible frequency collision checks (Type0A-Type9) per qubit "
                "and directed pair, with verdict colors and the terms behind each verdict"
            ),
            filename="collision.py",
        ),
        MetricScriptTemplate(
            template_id="zx90_median",
            name="Median ZX90 fidelity",
            description=(
                "Median of every ZX90 gate fidelity observation per directed coupling in "
                "the period, with sample counts and a minimum-sample threshold"
            ),
            filename="zx90_median.py",
        ),
        MetricScriptTemplate(
            template_id="zx90_daily_trend",
            name="ZX90 fidelity trend",
            description=(
                "Daily or weekly (UTC) median ZX90 gate fidelity of selected directed "
                "couplings over the period, with counts per point and gaps for empty bins"
            ),
            filename="zx90_daily_trend.py",
        ),
    )
}
"""Templates in display order."""
