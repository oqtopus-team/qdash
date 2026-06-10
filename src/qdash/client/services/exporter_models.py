from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class NormalizedMetricRecord:
    """Canonical metric representation used by exporter-oriented helpers."""

    chip_id: str
    entity_type: str
    entity_id: str
    metric_name: str
    value: float
    unit: str = ""
    observed_at: datetime | None = None
