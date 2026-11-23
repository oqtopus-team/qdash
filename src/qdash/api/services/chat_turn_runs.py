"""Run each chat turn's stream in the API, apart from the browser that asked for it.

A chat request starts the turn's stream in a background task (``TurnRun``) and
the HTTP response only subscribes to it. Closing the response, or every window,
ends the subscription, never the stream: the task reads the turn to its end,
records its progress and its end in the chat session (``chat_transcript`` and
``copilot_chat_session_service``), and then reports ``transcript``. A request
for the same turn (a retry, or a reattach) on the same API process subscribes
to the running task instead of opening a second stream; on another process it
opens its own, which records the same turn idempotently. A stream to the runtime
that drops is attached again by the task itself, with no browser involved.

What runs survives a browser disconnect, not a restart of the API process; a
reattach after such a restart opens a stream that records the turn again.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from qdash.api.lib.sse import sse_event
from qdash.api.services import copilot_chat_session_service as sessions
from qdash.api.services.chat_transcript import TurnTranscript
from qdash.api.services.pi_chat_service import (
    STREAM_LOST,
    TURN_BOUNDARY_UNKNOWN,
    parse_sse,
)
from qdash.dbmodel.copilot_chat_session import CopilotChatMessage

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable

    from qdash.copilot.contracts import ChatRequest

logger = logging.getLogger(__name__)

# SSE ``error`` code: another turn of the chat still runs; nothing was sent.
TURN_RUNNING = "turn_running"
# SSE ``error`` code: the saved chat no longer holds the start the turn was sent
# from (another window changed it); nothing was sent, and the page reloads it.
TRANSCRIPT_CONFLICT = "transcript_conflict"

# How long a turn waits for a save of its start still on its way (seconds).
CLAIM_WAITS = (0.2, 0.4, 0.8, 1.0)
# Attaching again to the runtime after its stream dropped: delays in seconds.
REATTACH_DELAYS = (1, 2, 4, 8, 16)
REATTACH_LATER = 30
MAX_REATTACH_ATTEMPTS = 25
# A keepalive comment for subscribers while the task waits to attach again.
KEEPALIVE_SECONDS = 15
# Progress is written at most this often (seconds); a placed steer at once.
PROGRESS_INTERVAL = 1.0
# Writing the turn's end: delays in seconds before each further attempt.
END_WRITE_DELAYS = (0.5, 1, 2, 4)

CONNECTION_LOST = (
    "Lost the connection to the assistant. It may still be working; reopen the chat to check."
)
_TERMINAL = ("result", "noop", "error")
_RETRY_CODES = (STREAM_LOST, TURN_BOUNDARY_UNKNOWN)


@dataclass
class TurnRun:
    """One turn's stream in this process, and who listens to it."""

    project_id: str | None
    events: list[str] = field(default_factory=list)
    subscribers: set[asyncio.Queue[str | None]] = field(default_factory=set)
    done: bool = False
    stop_requested: bool = False
    task: asyncio.Task[None] | None = None

    def subscribe(self) -> asyncio.Queue[str | None]:
        """A queue with the turn's events so far, then its live ones, then None."""
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        for event in self.events:
            queue.put_nowait(event)
        if self.done:
            queue.put_nowait(None)
        else:
            self.subscribers.add(queue)
        return queue

    def publish(self, chunk: str, *, keep: bool = True) -> None:
        if keep:
            self.events.append(chunk)
        for queue in self.subscribers:
            queue.put_nowait(chunk)

    def restart(self) -> None:
        """The stream replays the turn from its start: listeners fold it again."""
        self.events = []
        self.publish(sse_event("restart", {}))

    def close(self) -> None:
        self.done = True
        for queue in self.subscribers:
            queue.put_nowait(None)
        self.subscribers.clear()


RunKey = tuple[str, str, str]
_runs: dict[RunKey, TurnRun] = {}


def running(username: str, session_id: str, request_id: str) -> TurnRun | None:
    """The turn's stream in this process, if it runs here."""
    return _runs.get((username, session_id, request_id))


def note_stop(username: str, session_id: str, turn_request_id: str | None) -> None:
    """The user stopped the turn: it ends as stopped, not as failed."""
    for (user, session, request_id), run in _runs.items():
        if (
            user == username
            and session == session_id
            and (turn_request_id is None or request_id == turn_request_id)
        ):
            run.stop_requested = True


def user_message_of(request: ChatRequest, request_id: str) -> CopilotChatMessage | None:
    """The turn's own message as the chat stores it; None for a continue."""
    if request.continue_run:
        return None
    attached = bool(request.images) or request.task is not None or request.investigation is not None
    return CopilotChatMessage(
        role="user",
        content=request.message,
        attached_image="1" if attached else None,
        turn_request_id=request_id,
    )


def _message_json(message: CopilotChatMessage) -> dict[str, Any]:
    """A stored message as the session API returns it."""
    return {
        "role": message.role,
        "content": message.content,
        "attached_image": message.attached_image,
        "steer": message.steer.model_dump() if message.steer else None,
        "entry_id": message.entry_id,
        "turn_request_id": message.turn_request_id,
        "created_at": message.created_at.isoformat(),
    }


class _Recorder:
    """Writes one turn's messages: progress at most every PROGRESS_INTERVAL, then its end."""

    def __init__(self, username: str, session_id: str, request_id: str) -> None:
        self.username = username
        self.session_id = session_id
        self.request_id = request_id
        self._pending: list[CopilotChatMessage] | None = None
        self._writer: asyncio.Task[None] | None = None
        self._last = 0.0
        self.gone = False

    async def _write(self, run: list[CopilotChatMessage], **end: Any) -> sessions.TurnWrite:
        return await asyncio.to_thread(
            sessions.write_turn, self.username, self.session_id, self.request_id, run, **end
        )

    def progress(self, transcript: TurnTranscript, *, now: bool = False) -> None:
        """Keep the turn's progress, without holding up its stream."""
        if self.gone:
            return
        clock = time.monotonic()
        if not now and clock - self._last < PROGRESS_INTERVAL:
            return
        self._last = clock
        self._pending = transcript.messages()
        if self._writer is None or self._writer.done():
            self._writer = asyncio.create_task(self._drain())

    async def _drain(self) -> None:
        while self._pending is not None:
            run, self._pending = self._pending, None
            try:
                written = await self._write(run)
            except Exception:
                # The next progress write, or the end, writes it again.
                logger.warning(
                    "Could not save the progress of turn %s", self.request_id, exc_info=True
                )
                continue
            if written.outcome == "gone":
                self.gone = True
                return

    async def end(self, transcript: TurnTranscript) -> sessions.TurnWrite | None:
        """Write the turn's end, trying again on failure; None when it could not be saved."""
        self._pending = None
        if self._writer is not None:
            with contextlib.suppress(Exception):
                await self._writer
        status = transcript.end or "failed"
        for attempt in range(len(END_WRITE_DELAYS) + 1):
            try:
                return await self._write(
                    transcript.messages(), status=status, error=transcript.error
                )
            except Exception:
                logger.warning(
                    "Could not save the end of turn %s (attempt %d)",
                    self.request_id,
                    attempt + 1,
                    exc_info=True,
                )
            if attempt < len(END_WRITE_DELAYS):
                await asyncio.sleep(END_WRITE_DELAYS[attempt])
        logger.error("Gave up saving the end of turn %s", self.request_id)
        return None


def _runs_other_turn(username: str, session_id: str, request_id: str) -> bool:
    """Whether this process streams another turn of the chat."""
    return any(
        user == username and session == session_id and other != request_id and not run.done
        for (user, session, other), run in _runs.items()
    )


async def _claim(
    request: ChatRequest,
    username: str,
    project_id: str | None,
    request_id: str,
    turn_running: Callable[[], Awaitable[bool | None]] | None,
) -> tuple[sessions.ClaimOutcome | Literal["unknown"], CopilotChatMessage | None]:
    """Record the turn's start, waiting briefly for a save of it still on its way.

    A recorded turn still marked running blocks the claim while it runs here or in
    the runtime; one that runs nowhere (its API process restarted and nobody
    reattached) is replaced. Only the runtime's own answer that nothing runs
    counts as nowhere: when it cannot say (``turn_running`` gives None), the
    claim is ``unknown`` and the recorded turn, and what it saved, stay as they are.
    """
    assert request.session_id is not None and request.turn_start is not None
    session_id = request.session_id
    user_message = user_message_of(request, request_id)
    outcome: sessions.ClaimOutcome | Literal["unknown"] = "conflict"
    replace_running = False
    for wait in (0.0, *CLAIM_WAITS):
        if wait:
            await asyncio.sleep(wait)
        outcome = await asyncio.to_thread(
            sessions.claim_turn,
            username,
            session_id,
            request_id=request_id,
            project_id=project_id,
            start_index=request.turn_start.index,
            digest=request.turn_start.digest,
            user_message=user_message,
            replace_running=replace_running,
        )
        if outcome == "busy" and not replace_running:
            if _runs_other_turn(username, session_id, request_id):
                break
            if turn_running is not None:
                runs = await turn_running()
                if runs is None:
                    outcome = "unknown"
                    break
                if runs:
                    break
            replace_running = True
            continue
        if outcome != "conflict":
            break
    return outcome, user_message


async def _stopped(run: TurnRun, key: RunKey) -> bool:
    """Whether the user stopped the turn, here or through another API process."""
    if run.stop_requested:
        return True
    try:
        return await asyncio.to_thread(sessions.turn_stop_requested, *key)
    except Exception:
        logger.warning("Could not read whether turn %s was stopped", key[2], exc_info=True)
        return False


async def _wait_to_reattach(run: TurnRun, delay: float) -> None:
    """Sleep ``delay`` seconds, keeping subscribers' connections alive meanwhile."""
    remaining = delay
    while remaining > 0:
        step = min(remaining, KEEPALIVE_SECONDS)
        await asyncio.sleep(step)
        remaining -= step
        run.publish(":\n\n", keep=False)


async def _drive(
    run: TurnRun,
    key: RunKey,
    request: ChatRequest,
    source: Callable[[ChatRequest], AsyncGenerator[str, None]],
    turn_running: Callable[[], Awaitable[bool | None]] | None = None,
) -> None:
    username, session_id, request_id = key
    recorder: _Recorder | None = None
    transcript: TurnTranscript | None = None
    try:
        if not request.reattach and request.turn_start is not None:
            try:
                outcome, user_message = await _claim(
                    request, username, run.project_id, request_id, turn_running
                )
            except Exception:
                logger.exception("Could not record the start of turn %s", request_id)
                run.publish(
                    sse_event(
                        "error",
                        {"step": "init", "detail": "Could not save the chat; try again"},
                    )
                )
                return
            if outcome == "conflict":
                run.publish(
                    sse_event(
                        "error",
                        {
                            "step": "init",
                            "detail": (
                                "This chat changed in another window, so the message was not "
                                "sent. Check the chat and send it again."
                            ),
                            "code": TRANSCRIPT_CONFLICT,
                        },
                    )
                )
                return
            if outcome == "busy":
                run.publish(
                    sse_event(
                        "error",
                        {
                            "step": "init",
                            "detail": (
                                "Another answer is still running in this chat. Wait for it to "
                                "end, or stop it, then send the message again."
                            ),
                            "code": TURN_RUNNING,
                        },
                    )
                )
                return
            if outcome == "unknown":
                run.publish(
                    sse_event(
                        "error",
                        {
                            "step": "init",
                            "detail": (
                                "Could not check whether an earlier answer still runs in this "
                                "chat, so the message was not sent. Send it again shortly."
                            ),
                            "code": TURN_RUNNING,
                        },
                    )
                )
                return
            if outcome == "gone":
                run.publish(
                    sse_event("error", {"step": "init", "detail": "Chat session not found"})
                )
                return
            recorded = await asyncio.to_thread(
                sessions.recorded_turn, username, session_id, request_id
            )
            # A retried request of a turn sent from another project records nothing.
            if recorded is not None and recorded.turn.project_id == run.project_id:
                recorder = _Recorder(username, session_id, request_id)
                transcript = TurnTranscript(request_id, user_message)
        elif request.reattach:
            try:
                recorded = await asyncio.to_thread(
                    sessions.recorded_turn, username, session_id, request_id
                )
            except Exception:
                # Still streamed; the stream that started the turn, or a later one, records it.
                logger.warning("Could not read the record of turn %s", request_id, exc_info=True)
                recorded = None
            if recorded is not None and recorded.turn.project_id == run.project_id:
                own = next(
                    (m for m in recorded.messages if m.role == "user" and m.steer is None),
                    None,
                )
                recorder = _Recorder(username, session_id, request_id)
                transcript = TurnTranscript(request_id, None if recorded.turn.continuing else own)

        current = request
        attempt = 0
        terminal: str | None = None
        while terminal is None:
            async with contextlib.aclosing(source(current)) as stream:
                async for chunk in stream:
                    parsed = parse_sse(chunk)
                    if parsed is None:
                        run.publish(chunk, keep=False)
                        continue
                    name, data = parsed
                    if name == "error" and data.get("code") in _RETRY_CODES:
                        break
                    if name == "error" and data.get("code") == "wrong_project":
                        # Refused before it reached the turn: the turn's record is not this
                        # request's to write.
                        recorder = transcript = None
                    if transcript is not None:
                        transcript.apply(name, data)
                    if name in _TERMINAL:
                        terminal = name
                        if name == "error" and transcript is not None and await _stopped(run, key):
                            transcript.stop()
                        run.publish(chunk)
                        break
                    run.publish(chunk)
                    if recorder is not None and transcript is not None:
                        recorder.progress(transcript, now=name == "steer")
            if terminal is not None:
                break
            attempt += 1
            if attempt > MAX_REATTACH_ATTEMPTS:
                run.publish(sse_event("error", {"step": "run_chat", "detail": CONNECTION_LOST}))
                if transcript is not None:
                    transcript.apply("error", {"detail": CONNECTION_LOST})
                break
            delay = (
                REATTACH_DELAYS[attempt - 1] if attempt <= len(REATTACH_DELAYS) else REATTACH_LATER
            )
            await _wait_to_reattach(run, delay)
            current = request.model_copy(update={"reattach": True})
            if transcript is not None:
                transcript.restart()
            run.restart()

        if recorder is not None and transcript is not None and transcript.end is not None:
            written = await recorder.end(transcript)
            if written is None:
                run.publish(sse_event("transcript", {"saved": False, "request_id": request_id}))
            elif written.outcome != "gone":
                run.publish(
                    sse_event(
                        "transcript",
                        {
                            "saved": True,
                            "request_id": request_id,
                            "messages": [_message_json(m) for m in written.messages],
                        },
                    )
                )
    except Exception:
        logger.exception("The stream of turn %s failed", request_id)
        run.publish(sse_event("error", {"step": "run_chat", "detail": "The chat stream failed"}))
    finally:
        run.close()
        if _runs.get(key) is run:
            del _runs[key]


async def stream_turn(
    request: ChatRequest,
    *,
    username: str,
    project_id: str | None,
    source: Callable[[ChatRequest], AsyncGenerator[str, None]],
    turn_running: Callable[[], Awaitable[bool | None]] | None = None,
) -> AsyncGenerator[str, None]:
    """The turn's SSE events for one HTTP response, from the turn's own run.

    ``turn_running`` asks the runtime whether a turn of the chat runs, so a turn
    left marked running by a restarted API process does not block the chat.

    The run outlives the response: closing it only unsubscribes. A request of a
    turn that runs here from another project is refused, as the runtime would.
    """
    if not request.session_id or not request.request_id:
        async for chunk in source(request):
            yield chunk
        return
    key: RunKey = (username, request.session_id, request.request_id)
    run = _runs.get(key)
    if run is not None and run.project_id != project_id:
        yield sse_event(
            "error",
            {
                "step": "init",
                "detail": "This turn was sent from another project",
                "code": "wrong_project",
            },
        )
        return
    if run is None:
        run = TurnRun(project_id=project_id)
        _runs[key] = run
        run.task = asyncio.create_task(_drive(run, key, request, source, turn_running))
    queue = run.subscribe()
    try:
        while (item := await queue.get()) is not None:
            yield item
    finally:
        run.subscribers.discard(queue)
