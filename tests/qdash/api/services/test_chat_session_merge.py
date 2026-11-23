"""What a client save of a chat's messages stores next to the turns the server recorded."""

from __future__ import annotations

import itertools
import json
import random
from datetime import datetime, timezone
from typing import Any

import pytest

from qdash.api.services.copilot_chat_session_service import merge_saved_messages
from qdash.dbmodel.copilot_chat_session import (
    CopilotChatMessage,
    CopilotChatServerTurn,
    CopilotChatSessionDocument,
    CopilotChatSteer,
    TurnStatus,
)

# Documents are built in memory; bunnet needs its collection set up for that.
pytestmark = pytest.mark.usefixtures("init_db")

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _m(content: str, role: str = "user", rid: str | None = None) -> CopilotChatMessage:
    return CopilotChatMessage(role=role, content=content, turn_request_id=rid, created_at=T0)


def _doc(
    messages: list[CopilotChatMessage],
    rid: str | None = None,
    status: TurnStatus = "completed",
    start: int = 0,
) -> CopilotChatSessionDocument:
    turn = (
        CopilotChatServerTurn(
            request_id=rid,
            project_id="p1",
            start_index=start,
            continuing=False,
            started_at=T0,
            updated_at=T0,
            status=status,
        )
        if rid
        else None
    )
    return CopilotChatSessionDocument(
        username="alice", session_id="s1", messages=messages, turn=turn
    )


def _contents(messages: list[CopilotChatMessage]) -> list[str]:
    return [m.content for m in messages]


A = [_m("qa", rid="a"), _m("answer a", "assistant", "a")]
B = [_m("qb", rid="b"), _m("answer b", "assistant", "b")]


def test_a_chat_without_recorded_turns_takes_the_client_copy() -> None:
    doc = _doc([_m("hi"), _m("hello", "assistant")])
    incoming = [_m("edited"), _m("hello", "assistant"), _m("more")]
    assert merge_saved_messages(doc, incoming) == incoming


def test_a_steer_the_page_placed_between_turns_is_kept() -> None:
    doc = _doc([*A, *B], "b")
    steer = CopilotChatMessage(
        role="user", content="late", steer=CopilotChatSteer(request_id="s"), created_at=T0
    )
    merged = merge_saved_messages(doc, [*A, steer, *B])
    assert _contents(merged) == ["qa", "answer a", "late", "qb", "answer b"]


def test_a_copy_missing_an_earlier_turn_gets_it_back_in_place() -> None:
    doc = _doc([_m("hi"), *A, _m("between"), *B], "b")
    # A copy that dropped turn a.
    merged = merge_saved_messages(doc, [_m("hi"), _m("between"), *B])
    assert _contents(merged) == ["hi", "qa", "answer a", "between", "qb", "answer b"]
    # An older copy holding less of the chat than precedes the first turn.
    merged = merge_saved_messages(_doc([_m("hi"), _m("there"), *A], "a"), [_m("hi")])
    assert _contents(merged) == ["hi", "there", "qa", "answer a"]


def test_a_copy_cannot_reorder_or_duplicate_a_recorded_turn() -> None:
    doc = _doc([*A, *B], "b")
    # The stored order wins over the copy's, whatever the copy repeats or moves.
    assert merge_saved_messages(doc, [B[1], *A]) == [*A, *B]
    stale = [_m("answer b old", "assistant", "b"), *A, _m("answer a dup", "assistant", "a")]
    assert merge_saved_messages(doc, stale) == [*A, *B]
    assert merge_saved_messages(doc, [*B, *A, *B]) == [*A, *B]


def test_nothing_after_a_running_turn_comes_from_the_client() -> None:
    running = _doc([*A, B[0]], "b", status="running", start=2)
    merged = merge_saved_messages(running, [*A, _m("qb", rid="b"), _m("extra")])
    assert _contents(merged) == ["qa", "answer a", "qb"]


def test_a_continue_just_claimed_keeps_the_chat_as_claimed() -> None:
    # A continue has no message of its own until its answer streams.
    continuing = _doc([*A], "c", status="running", start=2)
    merged = merge_saved_messages(continuing, [_m("qa", rid="a"), _m("extra")])
    assert _contents(merged) == ["qa", "answer a"]


# ---------------------------------------------------------------------------
# Invariants over every copy of a chat
# ---------------------------------------------------------------------------


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))


def _answer(text: str, rid: str, entry: str | None = None, **extra: Any) -> CopilotChatMessage:
    payload = {"blocks": [{"type": "text", "content": text, "chart": None}], "assessment": None}
    return CopilotChatMessage(
        role="assistant",
        content=_json({**payload, **extra}),
        turn_request_id=rid,
        entry_id=entry,
        created_at=T0,
    )


def _steer(text: str, request_id: str, rid: str | None = None) -> CopilotChatMessage:
    return CopilotChatMessage(
        role="user",
        content=text,
        steer=CopilotChatSteer(request_id=request_id),
        turn_request_id=rid,
        created_at=T0,
    )


def _rated(m: CopilotChatMessage, feedback: Any) -> CopilotChatMessage:
    payload = json.loads(m.content)
    if feedback is _UNRATED:
        payload.pop("feedback", None)
    else:
        payload["feedback"] = feedback
    return m.model_copy(update={"content": _json(payload)})


_UNRATED = object()


def _feedback(m: CopilotChatMessage) -> Any:
    return json.loads(m.content).get("feedback", _UNRATED)


# A legacy start, a steered turn, a client-owned message between turns, a
# continue (no user message), and a last turn.
LEGACY = [_m("legacy q"), _m("legacy a", "assistant")]
STEERED = [
    _m("q1", rid="t1"),
    _answer("part 1", "t1"),
    _steer("steer 1", "s1", "t1"),
    _answer("answer 1", "t1", "e1"),
]
BETWEEN = _m("between")
CONTINUED = [_answer("answer 2", "t2", "e2")]
LAST = [_m("q3", rid="t3"), _answer("answer 3", "t3", "e3")]
CHAT = [*LEGACY, *STEERED, BETWEEN, *CONTINUED, *LAST]
DURABLE = [*STEERED, *CONTINUED, *LAST]


def _durable(messages: list[CopilotChatMessage]) -> list[CopilotChatMessage]:
    return [m for m in messages if m.turn_request_id in {"t1", "t2", "t3"}]


def _check(incoming: list[CopilotChatMessage]) -> list[CopilotChatMessage]:
    """Merge a copy of CHAT and check the invariants every save keeps."""
    merged = merge_saved_messages(_doc(CHAT, "t3"), incoming)
    assert _durable(merged) == DURABLE
    owned = [m for m in merged if m.turn_request_id is None]
    # Each client-owned message is the copy's or the stored one, never repeated.
    assert all(m in incoming or m in CHAT for m in owned)
    for m in owned:
        assert owned.count(m) <= max(incoming.count(m), CHAT.count(m))
    return merged


def test_every_in_order_subset_keeps_the_stored_chat() -> None:
    # A copy that lacks any messages: durable ones always come back in place.
    for size in range(len(CHAT) + 1):
        for subset in itertools.combinations(CHAT, size):
            merged = _check(list(subset))
            if all(m in subset for m in CHAT if m.turn_request_id is None):
                assert merged == CHAT


def test_every_order_of_the_durable_messages_keeps_the_stored_order() -> None:
    owned = [m for m in CHAT if m.turn_request_id is None]
    for order in itertools.permutations(DURABLE):
        # "between" followed every durable message in the copy, so it follows them here.
        assert _check([*owned[:2], *order, owned[2]]) == [*LEGACY, *DURABLE, BETWEEN]


def test_shuffled_and_repeated_copies_keep_the_stored_order() -> None:
    rng = random.Random(1915)  # noqa: S311 - reproducible test data
    for _ in range(2000):
        copy = [rng.choice(CHAT) for _ in range(rng.randint(0, 2 * len(CHAT)))]
        _check(copy)
        shuffled = rng.sample(CHAT, len(CHAT))
        _check(shuffled)


def test_a_late_steer_stays_after_the_part_of_the_answer_it_interrupted() -> None:
    late = _steer("late", "s0")
    copy = [*LEGACY, *STEERED[:2], late, *STEERED[2:], BETWEEN, *CONTINUED, *LAST]
    assert _check(copy) == copy
    # A copy that lacks the rest of the chat did not see it: what it added
    # goes after that rest, as a message queued before it would.
    assert _check([*LEGACY, *STEERED[:2], late]) == [*CHAT, late]


def test_a_copy_saved_before_later_turns_keeps_its_new_message_last() -> None:
    queued = _m("queued")
    merged = _check([*LEGACY, *STEERED, queued])
    assert merged == [*CHAT, queued]


def test_a_rating_goes_to_the_same_answer_when_folds_differ() -> None:
    # The page folded turn t1 as one answer: its rating is the final answer's,
    # found by its runtime entry, not the part at the same index.
    fold = [STEERED[0], _rated(_answer("one fold", "t1", "e1"), "up")]
    merged = merge_saved_messages(_doc(CHAT, "t3"), [*LEGACY, *fold, BETWEEN, *CONTINUED, *LAST])
    assert merged[3] == STEERED[1]
    assert merged[5] == _rated(STEERED[3], "up")
    # Without an entry, the last answer of the turn is the turn's last answer.
    fold = [STEERED[0], _rated(_answer("one fold", "t1"), "down")]
    merged = merge_saved_messages(_doc(CHAT, "t3"), [*LEGACY, *fold, BETWEEN, *CONTINUED, *LAST])
    assert merged[3] == STEERED[1]
    assert merged[5] == _rated(STEERED[3], "down")
    # The part a steer closed off is known by that steer.
    part = _rated(_answer("part fold", "t1"), "up")
    merged = merge_saved_messages(_doc(CHAT, "t3"), [*LEGACY, STEERED[0], part, STEERED[2]])
    assert merged[3] == _rated(STEERED[1], "up")
    assert merged[5] == STEERED[3]


def test_an_ambiguous_rating_keeps_the_stored_one() -> None:
    stored = [*LEGACY, *STEERED[:3], _rated(STEERED[3], "up"), BETWEEN, *CONTINUED, *LAST]
    doc = _doc(stored, "t3")
    conflicting = [
        STEERED[0],
        _rated(_answer("a", "t1", "e1"), "down"),
        _rated(_answer("b", "t1", "e1"), _UNRATED),
    ]
    assert merge_saved_messages(doc, [*LEGACY, *conflicting])[5] == stored[5]
    # Copies that agree are no ambiguity.
    agreeing = [STEERED[0], _rated(STEERED[3], "down"), _rated(STEERED[3], "down")]
    assert _feedback(merge_saved_messages(doc, [*LEGACY, *agreeing])[5]) == "down"
    # An answer of another fold that neither its entry nor its place identifies
    # gets no rating.
    unkeyed = [_m("q4", rid="t4"), _answer("x", "t4"), _answer("y", "t4")]
    doc = _doc(unkeyed, "t4")
    copy = [unkeyed[0], _rated(_answer("x'", "t4"), "up"), _answer("y'", "t4")]
    assert merge_saved_messages(doc, copy) == unkeyed


def test_a_rating_is_cleared_only_on_its_own_answer() -> None:
    stored = [*LEGACY, *STEERED[:3], _rated(STEERED[3], "up"), BETWEEN, *CONTINUED, *LAST]
    doc = _doc(stored, "t3")
    merged = merge_saved_messages(doc, CHAT)
    assert merged[5] == STEERED[3]
    assert merged == CHAT
    # A copy that does not hold the answer leaves its rating alone.
    assert merge_saved_messages(doc, [*LEGACY, BETWEEN, *CONTINUED, *LAST]) == stored


def test_a_legacy_answer_rated_in_a_copy_missing_a_turn_is_not_repeated() -> None:
    # The page wraps a plain-text answer into blocks to rate it.
    wrapped = _rated(
        LEGACY[1].model_copy(
            update={
                "content": _json(
                    {
                        "blocks": [{"type": "text", "content": "legacy a", "chart": None}],
                        "assessment": None,
                    }
                )
            }
        ),
        "up",
    )
    merged = _check([LEGACY[0], wrapped, *LAST])
    assert merged == [LEGACY[0], wrapped, *STEERED, BETWEEN, *CONTINUED, *LAST]


def test_a_running_turn_keeps_its_place_and_progress() -> None:
    progress = _answer("so far", "t3", in_progress=True)
    doc = _doc([*CHAT[:-1], progress], "t3", status="running", start=len(CHAT) - 2)
    stale_answer = _answer("older", "t3")
    for copy in (
        [*CHAT[:-1], stale_answer, _m("extra")],
        [*LEGACY, *STEERED, _m("extra")],
        [LAST[0], *LEGACY],
    ):
        merged = merge_saved_messages(doc, copy)
        assert _durable(merged) == [*STEERED, *CONTINUED, LAST[0], progress]
        assert merged[-2:] == [LAST[0], progress]
    # A rating of an earlier answer while it runs is kept.
    rated = [*CHAT[:5], _rated(STEERED[3], "up"), *CHAT[6:-1], progress]
    assert merge_saved_messages(doc, rated) == rated


def test_a_client_only_error_of_an_unrecorded_turn_stays_where_the_copy_put_it() -> None:
    # A turn the server never claimed leaves its message and error with the page.
    unsent = [_m("q5", rid="t5"), _m("Error: offline", "assistant", "t5")]
    assert _check([*CHAT, *unsent]) == [*CHAT, *unsent]
    # Before a recorded turn, as the copy put it.
    expected = [*LEGACY, *unsent, *STEERED, BETWEEN, *CONTINUED, *LAST]
    assert _check([*LEGACY, *unsent, *STEERED]) == expected
