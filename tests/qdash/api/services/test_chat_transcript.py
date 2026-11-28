"""The server's fold of a chat turn's SSE events into the messages a session stores."""

import json
from typing import Any

from qdash.api.services.chat_transcript import TurnTranscript, transcript_digest
from qdash.dbmodel.agent_chat_session import AgentChatMessage, AgentChatSteer


def _clock(start: int = 1_000):
    ticks = iter(range(start, start + 10_000, 10))
    return lambda: next(ticks)


def _user(text: str = "What is T1?") -> AgentChatMessage:
    return AgentChatMessage(role="user", content=text, turn_request_id="r1")


def _payload(message: AgentChatMessage) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(message.content)
    return payload


def test_the_digest_matches_the_pages_digest() -> None:
    # Values computed by transcriptDigest in ui/src/lib/agentObservedTurn.ts.
    messages = [
        AgentChatMessage(role="user", content='こんにちは "q" \n\t\x01 😀'),
        AgentChatMessage(
            role="assistant",
            content='{"blocks":[{"type":"text","content":"hi","chart":null}],"assessment":null}',
        ),
        AgentChatMessage(
            role="user", content="steer", steer=AgentChatSteer(request_id="s", entry_id=None)
        ),
    ]
    assert transcript_digest(messages) == "0b3c0204ed516ffb"
    assert transcript_digest([]) == "d095202279b28c9e"
    # An answer of a recorded turn counts by its turn, whatever its text.
    answer = AgentChatMessage(role="assistant", content="ignored", turn_request_id="r9")
    assert transcript_digest([*messages, answer]) == "8af3d0d15d3928a4"
    assert transcript_digest([*messages, answer.model_copy(update={"content": "rated"})]) == (
        "8af3d0d15d3928a4"
    )


def test_an_answer_is_stored_with_its_trace_and_entry() -> None:
    fold = TurnTranscript("r1", _user(), clock=_clock())
    fold.apply("thinking", {"text": "Let me check"})
    fold.apply("tool_start", {"id": "c1", "tool": "qdash_get", "label": "Get", "args": {"q": 1}})
    fold.apply("tool_end", {"id": "c1", "tool": "qdash_get", "is_error": False, "output": "ok"})
    fold.apply("delta", {"text": "T1 is "})
    fold.apply("delta", {"text": "40 us."})
    fold.apply(
        "result",
        {
            "blocks": [{"type": "text", "content": "T1 is 40 us.", "chart": None}],
            "assessment": None,
            "entry_id": "17",
        },
    )

    user, answer = fold.messages()
    assert user.content == "What is T1?"
    assert answer.entry_id == "17"
    assert answer.turn_request_id == "r1"
    payload = _payload(answer)
    assert payload["blocks"][0]["content"] == "T1 is 40 us."
    kinds = [step["kind"] for step in payload["trace"]["steps"]]
    assert kinds == ["thinking", "tool"]
    tool = payload["trace"]["steps"][1]
    assert tool["status"] == "done"
    assert tool["args"] == {"q": 1}
    assert tool["output"] == "ok"
    assert fold.end == "completed"


def test_progress_is_the_answer_so_far_marked_in_progress() -> None:
    fold = TurnTranscript("r1", _user(), clock=_clock())
    assert [m.role for m in fold.messages()] == ["user"]
    fold.apply("tool_start", {"id": "c1", "tool": "qdash_wait_execution", "label": "Wait"})
    fold.apply("delta", {"text": "Waiting"})

    _, partial = fold.messages()
    payload = _payload(partial)
    assert payload["in_progress"] is True
    assert payload["blocks"] == [{"type": "text", "content": "Waiting", "chart": None}]
    assert payload["trace"]["steps"][0]["tool"] == "qdash_wait_execution"


def _write(fold: TurnTranscript, call_id: str, path: str, content: str, *, error: bool) -> None:
    fold.apply(
        "tool_start",
        {
            "id": call_id,
            "tool": "write",
            "label": "Write",
            "args": {"path": path, "content": content},
        },
    )
    fold.apply("tool_end", {"id": call_id, "tool": "write", "is_error": error, "output": "ok"})


def test_finished_writes_keep_full_arguments_within_a_shared_budget() -> None:
    fold = TurnTranscript("r1", _user(), clock=_clock())
    # Measured as the page measures it: UTF-16 code units, so astral characters count twice.
    large = "😀" * 20_000
    _write(fold, "w1", "a.txt", large, error=False)
    _write(fold, "w2", "b.txt", large, error=False)
    _write(fold, "w3", "small.txt", "tiny", error=False)
    _write(fold, "w4", "e.txt", large, error=True)
    fold.apply(
        "tool_start",
        {"id": "w5", "tool": "write", "label": "Write", "args": {"path": "r", "content": "x"}},
    )
    fold.apply("delta", {"text": "Stopped"})
    fold.stop()

    steps = _payload(fold.messages()[-1])["trace"]["steps"]
    assert steps[0]["args"] == {"path": "a.txt", "content": large}
    assert "interrupted" not in steps[0]
    # What the first write left is not enough for the second.
    assert isinstance(steps[1]["args"], str)
    assert len(steps[1]["args"]) == 4_001
    assert steps[2]["args"] == {"path": "small.txt", "content": "tiny"}
    assert steps[3]["status"] == "error"
    assert isinstance(steps[3]["args"], str)
    assert steps[4]["status"] == "done"
    assert steps[4]["interrupted"] is True
    assert steps[4]["args"] == {"path": "r", "content": "x"}


def test_progress_keeps_open_tools_open_and_the_end_closes_them() -> None:
    # Two tools: one done, one waiting; a third call is still being written.
    fold = TurnTranscript("r1", _user(), clock=_clock())
    fold.apply("tool_start", {"id": "c1", "tool": "qdash_get", "label": "Get"})
    fold.apply("tool_end", {"id": "c1", "tool": "qdash_get", "is_error": False})
    fold.apply("tool_start", {"id": "c2", "tool": "qdash_wait_execution", "label": "Wait"})
    fold.apply("tool_draft", {"id": "c3", "tool": "qdash_get", "index": 0})

    _, partial = fold.messages()
    steps = _payload(partial)["trace"]["steps"]
    # Progress of a running turn reports no tool as done or as not run that is not.
    assert [(s["tool"], s["status"]) for s in steps] == [
        ("qdash_get", "done"),
        ("qdash_wait_execution", "running"),
        ("qdash_get", "drafting"),
    ]
    assert "endedAt" not in steps[1]
    assert "interrupted" not in steps[1]

    fold.stop()
    _, stopped = fold.messages()
    assert [s["status"] for s in _payload(stopped)["trace"]["steps"]] == [
        "done",
        "done",
        "cancelled",
    ]
    # Stopping closed the waiting call without seeing its end.
    assert [s.get("interrupted") for s in _payload(stopped)["trace"]["steps"]] == [
        None,
        True,
        None,
    ]


def test_a_steer_closes_off_the_answer_so_far_and_follows_it() -> None:
    fold = TurnTranscript("r1", _user(), clock=_clock())
    fold.apply("delta", {"text": "First part"})
    fold.apply(
        "steer",
        {
            "request_id": "s1",
            "status": "applied",
            "entry_id": "9",
            "text": "also check T2",
            "result": {"blocks": [{"type": "text", "content": "First part", "chart": None}]},
        },
    )
    fold.apply("steer", {"request_id": "s1", "status": "applied", "text": "again"})
    fold.apply("result", {"blocks": [{"type": "text", "content": "Both", "chart": None}]})

    roles = [(m.role, m.steer.request_id if m.steer else None) for m in fold.messages()]
    assert roles == [("user", None), ("assistant", None), ("user", "s1"), ("assistant", None)]
    steer = fold.messages()[2]
    assert steer.steer is not None
    assert steer.steer.placement == "exact"
    assert steer.steer.entry_id == "9"
    assert all(m.turn_request_id == "r1" for m in fold.messages())


def test_a_stopped_turn_keeps_what_streamed_and_a_failed_one_says_why() -> None:
    stopped = TurnTranscript("r1", _user(), clock=_clock())
    stopped.apply("delta", {"text": "Partial"})
    stopped.apply("error", {"detail": "conversation was not answered: aborted"})
    stopped.stop()
    payload = _payload(stopped.messages()[-1])
    assert payload["stopped"] is True
    assert payload["blocks"][0]["content"] == "Partial"
    assert stopped.end == "stopped"
    assert stopped.error is None

    failed = TurnTranscript("r1", _user(), clock=_clock())
    failed.apply("error", {"detail": "The model returned an empty response"})
    assert failed.messages()[-1].content == "Error: The model returned an empty response"
    assert failed.end == "failed"


def test_a_failed_turn_keeps_its_progress_updates_ahead_of_the_error() -> None:
    fold = TurnTranscript("r1", _user(), clock=_clock())
    fold.apply("delta", {"text": "Checking the latest T1 results."})
    fold.apply("tool_start", {"id": "c1", "tool": "qdash_get_task_results", "args": {}})
    fold.apply("tool_end", {"id": "c1", "tool": "qdash_get_task_results", "is_error": False})
    fold.apply("delta", {"text": "Q3 looks low; comparing"})
    fold.apply("error", {"detail": "conversation was not answered: model_error"})
    *_, partial, error = fold.messages()
    assert error.content == "Error: conversation was not answered: model_error"
    payload = _payload(partial)
    assert payload["interrupted"] is True
    # The update before the tool stays in the trace; the text after it is the answer so far.
    assert [s["kind"] for s in payload["trace"]["steps"]] == ["text", "tool"]
    assert payload["trace"]["steps"][0]["text"] == "Checking the latest T1 results."
    assert payload["blocks"] == [
        {"type": "text", "content": "Q3 looks low; comparing", "chart": None}
    ]
    assert partial.turn_request_id == error.turn_request_id == "r1"


def test_a_continue_adds_no_user_message_and_a_noop_or_refusal_adds_nothing() -> None:
    fold = TurnTranscript("r1", None, clock=_clock())
    fold.apply("noop", {"reason": "nothing_to_answer"})
    assert fold.messages() == []
    assert fold.end == "noop"

    refused = TurnTranscript("r1", None, clock=_clock())
    refused.apply("error", {"detail": "Nothing to continue"})
    assert refused.messages() == []
    assert refused.end == "failed"


def test_a_restart_folds_the_replayed_turn_once() -> None:
    fold = TurnTranscript("r1", _user(), clock=_clock())
    fold.apply("delta", {"text": "Hello"})
    fold.restart()
    fold.apply("delta", {"text": "Hello"})
    fold.apply("result", {"blocks": [{"type": "text", "content": "Hello", "chart": None}]})
    assert [m.role for m in fold.messages()] == ["user", "assistant"]
    assert _payload(fold.messages()[-1])["blocks"][0]["content"] == "Hello"
