"""JSON utility functions."""

from __future__ import annotations

import math
from typing import Any


def sanitize_for_json(obj: Any) -> Any:
    """Replace NaN/Infinity float values with None for JSON safety.

    Parameters
    ----------
    obj : Any
        The object to sanitize (recursively handles dicts and lists)

    Returns
    -------
    Any
        Sanitized object with non-finite floats replaced by None

    """
    if isinstance(obj, float):
        return None if not math.isfinite(obj) else obj
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_for_json(v) for v in obj]
    return obj
