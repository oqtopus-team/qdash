"""The server's fold of a chat turn's SSE events into the messages a session stores."""

import json
from typing import Any

from qdash.api.services.chat_transcript import TurnTranscript, transcript_digest
from qdash.dbmodel.copilot_chat_session import CopilotChatMessage, CopilotChatSteer


def _clock(start: int = 1_000):
    ticks = iter(range(start, start + 10_000, 10))
    return lambda: next(ticks)


def _user(text: str = "What is T1?") -> CopilotChatMessage:
    return CopilotChatMessage(role="user", content=text, turn_request_id="r1")


def _payload(message: CopilotChatMessage) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(message.content)
    return payload


def test_the_digest_matches_the_pages_digest() -> None:
    # Values computed by transcriptDigest in ui/src/lib/copilotObservedTurn.ts.
    messages = [
        CopilotChatMessage(role="user", content='こんにちは "q" \n\t\x01 😀'),
        CopilotChatMessage(
            role="assistant",
            content='{"blocks":[{"type":"text","content":"hi","chart":null}],"assessment":null}',
        ),
        CopilotChatMessage(
            role="user", content="steer", steer=CopilotChatSteer(request_id="s", entry_id=None)
        ),
    ]
    assert transcript_digest(messages) == "0b3c0204ed516ffb"
    assert transcript_digest([]) == "d095202279b28c9e"
    # An answer of a recorded turn counts by its turn, whatever its text.
    answer = CopilotChatMessage(role="assistant", content="ignored", turn_request_id="r9")
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
    # A call still running when the progress was taken shows as done in the stored trace.
    assert payload["trace"]["steps"][0]["tool"] == "qdash_wait_execution"


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
