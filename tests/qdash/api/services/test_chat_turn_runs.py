"""The API runs and records each chat turn, whoever watches it.

A turn's stream runs in a background task: closing every response leaves it
running to its end and saved; a second request of the turn subscribes instead
of streaming it again; a stale save cannot replace what the server recorded.
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

import pytest

from qdash.api.lib.sse import sse_event
from qdash.api.schemas.copilot_chat_session import (
    CopilotChatMessageSchema,
    CreateCopilotChatSessionRequest,
    UpdateCopilotChatSessionRequest,
)
from qdash.api.services import chat_turn_runs
from qdash.api.services import copilot_chat_session_service as sessions
from qdash.api.services.chat_transcript import TurnTranscript, transcript_digest
from qdash.api.services.copilot_chat_session_service import (
    CopilotChatSessionService,
    request_turn_stop,
)
from qdash.copilot.contracts import ChatRequest, ChatTurnStart
from qdash.dbmodel.copilot_chat_session import CopilotChatMessage, CopilotChatSessionDocument

USER = "alice"
SESSION = "s1"
HISTORY = [
    {"role": "user", "content": "Hi"},
    {"role": "assistant", "content": "Hello"},
]


@pytest.fixture(autouse=True)
def _fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat_turn_runs, "CLAIM_WAITS", (0.01,))
    monkeypatch.setattr(chat_turn_runs, "REATTACH_DELAYS", (0, 0, 0))
    monkeypatch.setattr(chat_turn_runs, "PROGRESS_INTERVAL", 0.0)
    monkeypatch.setattr(chat_turn_runs, "END_WRITE_DELAYS", (0, 0))


def _session(messages: list[dict[str, str]] = HISTORY) -> CopilotChatSessionService:
    service = CopilotChatSessionService()
    service.create_session(
        username=USER,
        request=CreateCopilotChatSessionRequest(
            session_id=SESSION,
            messages=[CopilotChatMessageSchema.model_validate(m) for m in messages],
        ),
    )
    return service


def _request(
    text: str = "What is T1?",
    request_id: str = "r1",
    history: list[dict[str, Any]] | None = None,
    **fields: Any,
) -> ChatRequest:
    history = HISTORY if history is None else history
    prefix = [CopilotChatMessage.model_validate(m) for m in history]
    own = [CopilotChatMessage(role="user", content=text)]
    return ChatRequest.model_validate(
        {
            "message": text,
            "session_id": SESSION,
            "request_id": request_id,
            "turn_start": ChatTurnStart(
                index=len(history), digest=transcript_digest([*prefix, *own])
            ),
            **fields,
        }
    )


def _stored() -> CopilotChatSessionDocument:
    doc = CopilotChatSessionDocument.find_one({"username": USER, "session_id": SESSION}).run()
    assert doc is not None
    return doc


def _events(chunks: list[str]) -> list[tuple[str, dict[str, Any]]]:
    parsed = []
    for chunk in chunks:
        lines = dict(line.split(": ", 1) for line in chunk.strip().splitlines() if ": " in line)
        if "event" in lines:
            parsed.append((lines["event"], json.loads(lines["data"])))
    return parsed


class Runtime:
    """A runtime stream the test releases event by event; counts how often it is opened."""

    def __init__(self) -> None:
        self.opened: list[ChatRequest] = []
        self.queue: asyncio.Queue[str | None] = asyncio.Queue()

    def send(self, event: str, data: dict[str, Any]) -> None:
        self.queue.put_nowait(sse_event(event, data))

    def end(self) -> None:
        self.queue.put_nowait(None)

    async def source(self, request: ChatRequest) -> AsyncGenerator[str, None]:
        self.opened.append(request)
        while (chunk := await self.queue.get()) is not None:
            yield chunk


async def _collect(gen: AsyncGenerator[str, None]) -> list[str]:
    return [chunk async for chunk in gen]


async def _settle(request_id: str = "r1") -> None:
    run = chat_turn_runs.running(USER, SESSION, request_id)
    if run is not None and run.task is not None:
        await asyncio.wait_for(run.task, 5)


def _answer(text: str = "T1 is 40 us.") -> dict[str, Any]:
    return {"blocks": [{"type": "text", "content": text, "chart": None}], "entry_id": "17"}


@pytest.mark.asyncio
async def test_a_turn_with_no_window_left_runs_to_its_end_and_is_saved(init_db) -> None:
    _session()
    runtime = Runtime()
    response = chat_turn_runs.stream_turn(
        _request(), username=USER, project_id="p1", source=runtime.source
    )
    runtime.send("delta", {"text": "T1 is "})
    first = await anext(response)
    assert _events([first]) == [("delta", {"text": "T1 is "})]
    # The only window closes: the response ends, the turn does not.
    await response.aclose()

    # The start and the progress are already saved, for a window that opens now.
    for _ in range(50):
        if len(_stored().messages) == 4:
            break
        await asyncio.sleep(0.01)
    stored = _stored()
    assert [m.role for m in stored.messages] == ["user", "assistant", "user", "assistant"]
    assert stored.messages[2].turn_request_id == "r1"
    assert json.loads(stored.messages[3].content)["in_progress"] is True
    assert stored.turn is not None
    assert stored.turn.status == "running"
    assert stored.title == "What is T1?"

    runtime.send("delta", {"text": "40 us."})
    runtime.send("result", _answer())
    runtime.end()
    await _settle()

    stored = _stored()
    assert stored.turn is not None
    assert stored.turn.status == "completed"
    answer = stored.messages[3]
    assert answer.entry_id == "17"
    assert json.loads(answer.content)["blocks"][0]["content"] == "T1 is 40 us."
    assert len(runtime.opened) == 1


@pytest.mark.asyncio
async def test_a_second_request_of_the_turn_follows_it_without_sending_it_again(init_db) -> None:
    _session()
    runtime = Runtime()
    first = asyncio.create_task(
        _collect(
            chat_turn_runs.stream_turn(
                _request(), username=USER, project_id="p1", source=runtime.source
            )
        )
    )
    runtime.send("delta", {"text": "Part"})
    await asyncio.sleep(0.05)
    # Reconnecting mid-turn: the turn so far, then its live events.
    rejoin = asyncio.create_task(
        _collect(
            chat_turn_runs.stream_turn(
                _request(reattach=True), username=USER, project_id="p1", source=runtime.source
            )
        )
    )
    other_project = await _collect(
        chat_turn_runs.stream_turn(
            _request(), username=USER, project_id="p2", source=runtime.source
        )
    )
    await asyncio.sleep(0.05)
    runtime.send("result", _answer("Part"))
    runtime.end()
    one, two = await asyncio.gather(first, rejoin)

    assert len(runtime.opened) == 1
    assert [e for e, _ in _events(one)] == ["delta", "result", "transcript"]
    assert _events(two) == _events(one)
    saved = _events(one)[-1][1]
    assert saved["saved"] is True
    assert [m["role"] for m in saved["messages"]] == ["user", "assistant"]
    assert _events(other_project)[0][1]["code"] == "wrong_project"


@pytest.mark.asyncio
async def test_a_stopped_turn_is_saved_as_stopped_and_a_failed_one_as_failed(init_db) -> None:
    _session()
    runtime = Runtime()
    task = asyncio.create_task(
        _collect(
            chat_turn_runs.stream_turn(
                _request(), username=USER, project_id="p1", source=runtime.source
            )
        )
    )
    runtime.send("delta", {"text": "Partial"})
    await asyncio.sleep(0.05)
    # Stop from another API process: only the stored note says so.
    request_turn_stop(USER, SESSION, "r1")
    runtime.send("error", {"step": "run_chat", "detail": "conversation was not answered: aborted"})
    runtime.end()
    await task
    stored = _stored()
    assert stored.turn is not None
    assert stored.turn.status == "stopped"
    payload = json.loads(stored.messages[-1].content)
    assert payload["stopped"] is True
    assert payload["blocks"][0]["content"] == "Partial"

    failed = Runtime()
    history = [
        m.model_dump(include={"role", "content", "turn_request_id"}) for m in stored.messages
    ]
    task = asyncio.create_task(
        _collect(
            chat_turn_runs.stream_turn(
                _request("Again", request_id="r2", history=history),
                username=USER,
                project_id="p1",
                source=failed.source,
            )
        )
    )
    failed.send("error", {"step": "run_chat", "detail": "Agent runtime returned HTTP 500"})
    failed.end()
    await task
    stored = _stored()
    assert stored.turn is not None
    assert stored.turn.status == "failed"
    assert stored.messages[-1].content == "Error: Agent runtime returned HTTP 500"
    assert len(stored.messages) == 6


@pytest.mark.asyncio
async def test_a_dropped_runtime_stream_is_attached_again_by_the_api(init_db) -> None:
    _session()
    runtime = Runtime()
    task = asyncio.create_task(
        _collect(
            chat_turn_runs.stream_turn(
                _request(), username=USER, project_id="p1", source=runtime.source
            )
        )
    )
    runtime.send("delta", {"text": "Part"})
    # The API stops reading a stream that reports it was lost.
    runtime.send("error", {"step": "run_chat", "detail": "lost", "code": "stream_lost"})
    await asyncio.sleep(0.05)
    # The reattached stream replays the turn from its start.
    runtime.send("delta", {"text": "Part"})
    runtime.send("result", _answer("Part"))
    runtime.end()
    events = _events(await task)

    assert [r.reattach for r in runtime.opened] == [False, True]
    assert [e for e, _ in events] == ["delta", "restart", "delta", "result", "transcript"]
    stored = _stored()
    assert stored.turn is not None
    assert stored.turn.status == "completed"
    assert json.loads(stored.messages[-1].content)["blocks"][0]["content"] == "Part"


@pytest.mark.asyncio
async def test_a_turn_sent_from_a_stale_copy_of_the_chat_is_refused_unsent(init_db) -> None:
    _session()
    runtime = Runtime()
    stale = _request(history=[{"role": "user", "content": "Something else"}])
    events = _events(
        await _collect(
            chat_turn_runs.stream_turn(stale, username=USER, project_id="p1", source=runtime.source)
        )
    )
    assert events[0][1]["code"] == chat_turn_runs.TRANSCRIPT_CONFLICT
    assert runtime.opened == []
    assert [m.content for m in _stored().messages] == ["Hi", "Hello"]
    assert _stored().turn is None


@pytest.mark.asyncio
async def test_a_stale_save_cannot_replace_the_recorded_turn_but_keeps_its_rating(init_db) -> None:
    service = _session()
    runtime = Runtime()
    task = asyncio.create_task(
        _collect(
            chat_turn_runs.stream_turn(
                _request(), username=USER, project_id="p1", source=runtime.source
            )
        )
    )
    runtime.send("delta", {"text": "Partial"})
    await asyncio.sleep(0.05)

    # A save queued before the turn started (only the history) keeps the running turn.
    service.update_session(
        username=USER,
        session_id=SESSION,
        request=UpdateCopilotChatSessionRequest(
            messages=[CopilotChatMessageSchema.model_validate(m) for m in HISTORY]
        ),
    )
    assert [m.turn_request_id for m in _stored().messages][2:] == ["r1", "r1"]

    runtime.send("result", _answer())
    runtime.end()
    await task
    answer = _stored().messages[3]

    # A window that folded the turn itself saves its own copy, rated: only the rating stays.
    own = json.loads(answer.content)
    own["blocks"][0]["content"] = "a different fold"
    own["feedback"] = "up"
    service.update_session(
        username=USER,
        session_id=SESSION,
        request=UpdateCopilotChatSessionRequest(
            messages=[
                *[CopilotChatMessageSchema.model_validate(m) for m in HISTORY],
                CopilotChatMessageSchema(role="user", content="What is T1?", turn_request_id="r1"),
                CopilotChatMessageSchema(
                    role="assistant", content=json.dumps(own), turn_request_id="r1"
                ),
            ]
        ),
    )
    saved = json.loads(_stored().messages[3].content)
    assert saved["blocks"][0]["content"] == "T1 is 40 us."
    assert saved["feedback"] == "up"
    assert _stored().messages[3].entry_id == "17"


@pytest.mark.asyncio
async def test_a_reattach_after_the_end_reports_the_saved_turn_without_writing(init_db) -> None:
    _session()
    runtime = Runtime()
    task = asyncio.create_task(
        _collect(
            chat_turn_runs.stream_turn(
                _request(), username=USER, project_id="p1", source=runtime.source
            )
        )
    )
    runtime.send("result", _answer())
    runtime.end()
    await task
    revision = _stored().revision

    replay = Runtime()
    replay.send("result", _answer())
    replay.end()
    events = _events(
        await _collect(
            chat_turn_runs.stream_turn(
                _request(reattach=True), username=USER, project_id="p1", source=replay.source
            )
        )
    )
    assert events[-1][0] == "transcript"
    assert events[-1][1]["saved"] is True
    assert len(events[-1][1]["messages"]) == 2
    assert _stored().revision == revision


async def _complete_turn(request_id: str, text: str, answer: str) -> None:
    """Run one recorded turn from the chat as stored, to its end."""
    history = [
        m.model_dump(include={"role", "content", "steer", "turn_request_id"})
        for m in _stored().messages
    ]
    runtime = Runtime()
    task = asyncio.create_task(
        _collect(
            chat_turn_runs.stream_turn(
                _request(text, request_id=request_id, history=history),
                username=USER,
                project_id="p1",
                source=runtime.source,
            )
        )
    )
    runtime.send("result", _answer(answer))
    runtime.end()
    await task


def _schema(message: CopilotChatMessage) -> CopilotChatMessageSchema:
    return CopilotChatMessageSchema.model_validate(message.model_dump())


@pytest.mark.asyncio
async def test_a_stale_save_after_a_later_turn_started_keeps_every_recorded_turn(init_db) -> None:
    service = _session()
    await _complete_turn("r1", "What is T1?", "T1 is 40 us.")
    first_turn = _stored().messages[2:]
    # A window that folded turn r1 itself, before it ended, keeps that copy.
    stale_answer = first_turn[1].model_copy(
        update={
            "content": json.dumps({"blocks": [], "in_progress": True}),
            "entry_id": None,
        }
    )
    stale = [*_stored().messages[:3], stale_answer]

    runtime = Runtime()
    history = [
        m.model_dump(include={"role", "content", "turn_request_id"}) for m in _stored().messages
    ]
    task = asyncio.create_task(
        _collect(
            chat_turn_runs.stream_turn(
                _request("And T2?", request_id="r2", history=history),
                username=USER,
                project_id="p1",
                source=runtime.source,
            )
        )
    )
    runtime.send("delta", {"text": "T2 is "})
    for _ in range(50):
        if len(_stored().messages) == 6:
            break
        await asyncio.sleep(0.01)

    # The stale copy arrives after turn r2 started: shorter, longer, and with a
    # message of its own after the turns.
    for copy in (
        stale,
        stale[:2],
        [*stale, CopilotChatMessage(role="user", content="queued")],
    ):
        service.update_session(
            username=USER,
            session_id=SESSION,
            request=UpdateCopilotChatSessionRequest(messages=[_schema(m) for m in copy]),
        )
        stored = _stored().messages
        assert stored[2:4] == first_turn
        assert [m.turn_request_id for m in stored] == [None, None, "r1", "r1", "r2", "r2"]
        assert json.loads(stored[5].content)["in_progress"] is True

    runtime.send("result", _answer("T2 is 30 us."))
    runtime.end()
    await task
    stored = _stored().messages
    assert stored[2:4] == first_turn
    assert json.loads(stored[5].content)["blocks"][0]["content"] == "T2 is 30 us."

    # Once r2 ended, the stale copy still cannot change either turn; the client's
    # own message after them is kept.
    service.update_session(
        username=USER,
        session_id=SESSION,
        request=UpdateCopilotChatSessionRequest(
            messages=[
                _schema(m) for m in [*stale, CopilotChatMessage(role="user", content="queued")]
            ]
        ),
    )
    after = _stored().messages
    assert after[:6] == stored
    assert [m.content for m in after[6:]] == ["queued"]


@pytest.mark.asyncio
async def test_rating_an_earlier_turn_keeps_its_recorded_answer(init_db) -> None:
    service = _session()
    await _complete_turn("r1", "What is T1?", "T1 is 40 us.")
    await _complete_turn("r2", "And T2?", "T2 is 30 us.")
    recorded = _stored().messages

    # The page rates r1's answer from its own fold, which differs from the server's.
    own = json.loads(recorded[3].content)
    own["blocks"][0]["content"] = "the page's fold"
    own["trace"] = [{"kind": "thinking", "text": "local"}]
    own["feedback"] = {"rating": "up"}
    rated = recorded[3].model_copy(
        update={"content": json.dumps(own), "entry_id": None, "created_at": recorded[0].created_at}
    )
    service.update_session(
        username=USER,
        session_id=SESSION,
        request=UpdateCopilotChatSessionRequest(
            messages=[_schema(m) for m in [*recorded[:3], rated, *recorded[4:]]]
        ),
    )
    stored = _stored().messages
    answer = json.loads(stored[3].content)
    assert answer == {**json.loads(recorded[3].content), "feedback": {"rating": "up"}}
    assert stored[3].entry_id == recorded[3].entry_id
    assert stored[3].created_at == recorded[3].created_at
    assert stored[4:] == recorded[4:]

    # Clearing the rating removes only the rating.
    cleared = stored[3].model_copy(update={"content": json.dumps({**own, "feedback": None})})
    del own["feedback"]
    unrated = stored[3].model_copy(update={"content": json.dumps(own)})
    for copy, expected in ((unrated, None), (cleared, "null")):
        service.update_session(
            username=USER,
            session_id=SESSION,
            request=UpdateCopilotChatSessionRequest(
                messages=[_schema(m) for m in [*recorded[:3], copy, *recorded[4:]]]
            ),
        )
        payload = json.loads(_stored().messages[3].content)
        base = json.loads(recorded[3].content)
        assert payload == (base if expected is None else {**base, "feedback": None})


@pytest.mark.asyncio
async def test_a_turn_that_replaces_an_orphaned_one_marks_its_progress_interrupted(
    init_db,
) -> None:
    # r1's API process restarted mid-turn: its progress stays saved as running.
    _session()
    first = _request()
    own = chat_turn_runs.user_message_of(first, "r1")
    assert first.turn_start is not None
    claimed = sessions.claim_turn(
        USER,
        SESSION,
        request_id="r1",
        project_id="p1",
        start_index=first.turn_start.index,
        digest=first.turn_start.digest,
        user_message=own,
    )
    assert claimed == "claimed"
    fold = TurnTranscript("r1", own)
    fold.apply("tool_start", {"id": "c1", "tool": "qdash_wait_execution", "label": "Wait"})
    fold.apply("tool_draft", {"id": "c2", "tool": "qdash_get", "index": 0})
    sessions.write_turn(USER, SESSION, "r1", fold.messages())
    progress = [m.model_dump(mode="json") for m in _stored().messages]
    assert json.loads(progress[3]["content"])["in_progress"] is True

    # The next turn is sent from the chat as saved; nothing runs r1 any more.
    async def nothing_runs() -> bool:
        return False

    runtime = Runtime()
    second = chat_turn_runs.stream_turn(
        _request("And T2?", "r2", history=progress),
        username=USER,
        project_id="p1",
        source=runtime.source,
        turn_running=nothing_runs,
    )
    runtime.send("result", _answer("T2 is 30 us."))
    runtime.end()
    await _collect(second)
    await _settle("r2")

    stored = _stored()
    assert [m.turn_request_id for m in stored.messages] == [None, None, "r1", "r1", "r2", "r2"]
    kept = json.loads(stored.messages[3].content)
    # r1's answer so far stays, as interrupted, with no step claiming to still run.
    assert "in_progress" not in kept
    assert kept["interrupted"] is True
    assert [s["status"] for s in kept["trace"]["steps"]] == ["done", "cancelled"]
    # The wait's end was not seen, so its written content is never offered as finished.
    assert [s.get("interrupted") for s in kept["trace"]["steps"]] == [True, None]


@pytest.mark.asyncio
async def test_a_runtime_that_cannot_say_whether_a_turn_runs_never_replaces_it(
    init_db,
) -> None:
    # r1 is recorded as running, and its progress is saved, when this API asks again.
    _session()
    first = _request()
    own = chat_turn_runs.user_message_of(first, "r1")
    assert first.turn_start is not None
    assert (
        sessions.claim_turn(
            USER,
            SESSION,
            request_id="r1",
            project_id="p1",
            start_index=first.turn_start.index,
            digest=first.turn_start.digest,
            user_message=own,
        )
        == "claimed"
    )
    fold = TurnTranscript("r1", own)
    fold.apply("tool_start", {"id": "c1", "tool": "qdash_wait_execution", "label": "Wait"})
    sessions.write_turn(USER, SESSION, "r1", fold.messages())
    before = _stored()
    progress = [m.model_dump(mode="json") for m in before.messages]

    asked: list[int] = []

    async def outage() -> bool | None:
        # The runtime is down or answered something malformed: it cannot say.
        asked.append(1)
        return None

    runtime = Runtime()
    second = await _collect(
        chat_turn_runs.stream_turn(
            _request("And T2?", "r2", history=progress),
            username=USER,
            project_id="p1",
            source=runtime.source,
            turn_running=outage,
        )
    )

    # The new turn is refused as busy, and nothing was sent to the runtime...
    events = _events(second)
    assert [name for name, _ in events] == ["error"]
    assert events[0][1]["code"] == chat_turn_runs.TURN_RUNNING
    assert asked
    assert runtime.opened == []
    # ...and r1, its record and what it saved stay exactly as they were.
    after = _stored()
    assert after.turn is not None
    assert after.turn.request_id == "r1"
    assert after.turn.status == "running"
    assert [m.model_dump(mode="json") for m in after.messages] == progress
    assert json.loads(after.messages[-1].content)["in_progress"] is True
