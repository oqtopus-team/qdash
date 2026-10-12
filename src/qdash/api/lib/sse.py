"""Server-Sent Event formatting utilities."""

from __future__ import annotations

import json
import math
from typing import Any


def _sanitize_for_json(obj: Any) -> Any:
    """Recursively sanitize values for JSON serialization.

    - NaN / Inf floats → None
    - Array-like objects (numpy ndarray, etc.) → list
    - Non-primitive types (datetime, numpy scalar, etc.) → str
    """
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, (str, int, bool, type(None), float)):
        return obj
    # numpy ndarray, pandas Series, etc. — convert to list first
    if hasattr(obj, "tolist"):
        return _sanitize_for_json(obj.tolist())
    return str(obj)


def sse_event(event: str, data: dict[str, Any]) -> str:
    """Format a Server-Sent Event.

    Parameters
    ----------
    event : str
        The event type name
    data : dict[str, Any]
        The event data payload

    Returns
    -------
    str
        Formatted SSE string

    """
    return f"event: {event}\ndata: {json.dumps(_sanitize_for_json(data), default=str, ensure_ascii=False)}\n\n"
