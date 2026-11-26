"""Relay the agent runtime's presentation stream to the chat as SSE.

The runtime decides what the chat shows of a turn (``qdash.agent.contracts.
presentation``). The API validates every envelope and relays its ``data``
unchanged as the SSE event it names, adding only what the API owns: the
``step`` of an error, a task chat's ``extra_result`` on the final result, and
the ids of the evaluations it stores. Evaluation records reach the recorder,
never the chat.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from qdash.agent.contracts.presentation import (
    MAX_ENVELOPE_CHARS,
    PRESENTATION_MEDIA_TYPE,
    PRESENTATION_VERSION,
    TERMINAL_EVENTS,
    PresentationError,
    parse_envelope,
)
from qdash.api.lib.sse import sse_event

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterable

    from qdash.api.services.pi_chat_service import EvaluationRecorder

logger = logging.getLogger(__name__)

# SSE ``error`` code: the stream to the runtime failed or ended before the turn
# did, so the turn may still be running and the chat reattaches.
STREAM_LOST = "stream_lost"


def presentation_version(content_type: str | None) -> int | None:
    """The presentation version a runtime response declares, or None for legacy NDJSON.

    A response of the presentation media type without a version, or with one this
    API does not speak, is ``-1``: refused explicitly rather than read as NDJSON.
    """
    media_type, *params = [part.strip() for part in (content_type or "").split(";")]
    if media_type.lower() != PRESENTATION_MEDIA_TYPE:
        return None
    for param in params:
        name, _, value = param.partition("=")
        if name.strip().lower() == "version":
            return PRESENTATION_VERSION if value.strip() == str(PRESENTATION_VERSION) else -1
    return -1


class EnvelopeTooLargeError(Exception):
    """A line of the runtime stream grew past ``MAX_ENVELOPE_CHARS`` without ending."""


async def bounded_lines(
    chunks: AsyncIterable[str], limit: int = MAX_ENVELOPE_CHARS
) -> AsyncGenerator[str, None]:
    """Split decoded text into lines, refusing one longer than ``limit`` before it ends."""
    buffer = ""
    async for chunk in chunks:
        buffer += chunk
        *complete, buffer = buffer.split("\n")
        for line in complete:
            if len(line) > limit:
                raise EnvelopeTooLargeError
            yield line
        if len(buffer) > limit:
            raise EnvelopeTooLargeError
    if buffer:
        yield buffer


def evaluation_for_chat(
    evaluation: Any,
    record: Any,
    recorder: EvaluationRecorder | None,
    *,
    call: str | None,
) -> dict[str, Any] | None:
    """The evaluation summary the chat shows, with the record stored and replaced by its ids."""
    if not isinstance(evaluation, dict):
        return None
    shown = {key: value for key, value in evaluation.items() if key != "record"}
    if recorder is not None and isinstance(record, dict):
        ids = recorder.record(record, call)
        if ids:
            shown.update(ids)
    return shown


def _refuse(step: str, detail: str) -> str:
    return sse_event("error", {"step": step, "detail": detail})


async def relay(
    lines: AsyncIterable[str],
    *,
    extra_result: dict[str, Any] | None = None,
    step: str = "run_chat",
    recorder: EvaluationRecorder | None = None,
) -> AsyncGenerator[str, None]:
    """Turn a runtime presentation stream into QDash SSE events.

    Every envelope is validated before anything of it is relayed; the first one
    refused ends the stream with an ``error``. Kept free of HTTP so it can be
    tested on plain strings.
    """
    try:
        async for line in lines:
            if not line.strip():
                continue
            try:
                envelope = parse_envelope(line)
            except PresentationError as exc:
                logger.warning("Refused a runtime presentation envelope: %s", exc.detail)
                yield _refuse(step, exc.detail)
                return
            event = envelope.event
            if event == "keepalive":
                # An SSE comment keeps every proxy on the way to the browser from
                # timing out an idle stream.
                yield ":\n\n"
                continue
            data: dict[str, Any] = dict(envelope.data)
            internal = envelope.internal
            if event == "tool_end" and internal is not None and internal.evaluation_record:
                stored = internal.evaluation_record
                # A result committed before this turn's message is an earlier turn's (a
                # run recovered after the runtime restarted): this turn never files it.
                data["evaluation"] = evaluation_for_chat(
                    data["evaluation"],
                    stored.record,
                    None if stored.before_turn else recorder,
                    call=f"entry:{stored.entry_id}" if stored.entry_id else None,
                )
            if internal is not None and internal.answer is not None and recorder is not None:
                recorder.finish(internal.answer)
            if event == "error":
                data = {"step": step, **data}
            elif event == "result":
                data = {**data, **(extra_result or {})}
            yield sse_event(event, data)
            if event in TERMINAL_EVENTS:
                return
    except EnvelopeTooLargeError:
        logger.warning("Refused a runtime presentation envelope over the size limit")
        yield _refuse(step, "Agent runtime sent an event over the size limit")
        return

    yield sse_event(
        "error",
        {
            "step": step,
            "detail": "Agent runtime closed the stream without a result",
            "code": STREAM_LOST,
        },
    )
