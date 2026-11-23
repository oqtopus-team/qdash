"""Server-Sent Event formatting utilities."""

from __future__ import annotations

import json
import math
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

import anyio
from starlette.responses import StreamingResponse

if TYPE_CHECKING:
    from starlette.types import Receive, Scope, Send


class ClosingStreamingResponse(StreamingResponse):
    """Close the response's async generator when sending ends or disconnects.

    Starlette's ASGI 2.4 send-error path does not close its body iterator. A chat
    subscriber must release its queue without waiting for garbage collection of
    the response or its exception traceback. Closing that subscriber does not
    cancel the independent task that owns the chat turn.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Finish generator cleanup even when the request's cancel scope is cancelled."""
        try:
            await super().__call__(scope, receive, send)
        finally:
            if isinstance(self.body_iterator, AsyncGenerator):
                with anyio.CancelScope(shield=True):
                    await self.body_iterator.aclose()


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
