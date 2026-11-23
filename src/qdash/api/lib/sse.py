"""Server-Sent Event formatting utilities."""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING, Any

from starlette.responses import StreamingResponse

if TYPE_CHECKING:
    from starlette.types import Receive, Scope, Send


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


class ClosingStreamingResponse(StreamingResponse):
    """A streaming response that closes its body iterator as soon as it ends.

    Starlette leaves the iterator suspended when a send fails with ``OSError``
    (how an ASGI 2.4 server reports a closed connection), so its ``finally``
    blocks wait for garbage collection. Closing it here runs them when the
    response ends, however it ends.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            aclose = getattr(self.body_iterator, "aclose", None)
            if aclose is not None:
                await aclose()
