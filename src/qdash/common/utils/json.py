"""JSON utility functions."""

from __future__ import annotations

import math
from typing import Any


def sanitize_for_json(obj: Any) -> Any:
    """Replace NaN/Infinity float values with None for JSON safety."""
    if isinstance(obj, float):
        return None if not math.isfinite(obj) else obj
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_for_json(v) for v in obj]
    return obj
