"""Server-Sent Event formatting utilities."""

from __future__ import annotations

import asyncio
import json
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable


def _sanitize_for_json(obj: Any) -> Any:
    """Recursively replace NaN/Inf float values with None for valid JSON."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    return obj


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
    return f"event: {event}\ndata: {json.dumps(_sanitize_for_json(data), ensure_ascii=False)}\n\n"


@dataclass
class SSETaskBridge:
    """Bridge between an asyncio task and an SSE event stream.

    Encapsulates the repeated pattern of:
    1. Creating a queue for status callbacks
    2. Polling the queue while the task runs
    3. Yielding SSE events or heartbeats
    4. Draining remaining events after the task completes

    Parameters
    ----------
    tool_labels : dict[str, str]
        Mapping of tool names to human-readable labels.
    status_labels : dict[str, str]
        Mapping of status keys to human-readable labels.
    heartbeat_timeout : float
        Seconds to wait before sending a heartbeat comment.

    """

    tool_labels: dict[str, str] = field(default_factory=dict)
    status_labels: dict[str, str] = field(default_factory=dict)
    heartbeat_timeout: float = 0.3

    def _make_callbacks(
        self, queue: asyncio.Queue[dict[str, Any]]
    ) -> tuple[
        Callable[[str, dict[str, Any]], Awaitable[None]],
        Callable[[str], Awaitable[None]],
    ]:
        """Create on_tool_call and on_status callbacks that push to *queue*."""
        completed_tools: list[str] = []

        async def on_tool_call(name: str, args: dict[str, Any]) -> None:
            label = self.tool_labels.get(name, name)
            await queue.put({"step": "tool_call", "tool": name, "message": f"{label}..."})
            completed_tools.append(label)

        async def on_status(status: str) -> None:
            label = self.status_labels.get(status, status)
            if status == "thinking" and completed_tools:
                label = f"Analyzing {completed_tools[-1].lower().rstrip('.')} results..."
            await queue.put(
                {"step": status, "message": label, "completed_tools": list(completed_tools)}
            )

        return on_tool_call, on_status

    async def drain(
        self,
        coro: Any,
    ) -> AsyncGenerator[str | Any, None]:
        """Run *coro* in a task and yield SSE events until it completes.

        Yields
        ------
        str
            SSE-formatted status events and heartbeat comments.

        The coroutine receives ``on_tool_call`` and ``on_status`` keyword
        arguments via :pyattr:`_make_callbacks`.  After the task finishes
        the result is yielded as-is (not formatted) so the caller can
        post-process it.

        Parameters
        ----------
        coro : coroutine
            An *unawaited* coroutine that accepts ``on_tool_call`` and
            ``on_status`` keyword arguments.

        Yields
        ------
        str | Any
            SSE event strings while the task runs, then the final result
            object as the last yielded value.

        Raises
        ------
        Exception
            Re-raises any exception from the background task.

        """
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        on_tool_call, on_status = self._make_callbacks(queue)

        task = asyncio.create_task(coro(on_tool_call=on_tool_call, on_status=on_status))

        while not task.done():
            try:
                event = await asyncio.wait_for(queue.get(), timeout=self.heartbeat_timeout)
                yield sse_event("status", event)
            except asyncio.TimeoutError:  # noqa: PERF203
                yield ":\n\n"

        # Drain remaining events
        while not queue.empty():
            event = queue.get_nowait()
            yield sse_event("status", event)

        # Yield the result for the caller to handle
        yield task.result()
