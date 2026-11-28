"""Fold a chat turn's SSE events into the messages the chat session stores.

The server records every turn itself, whoever watches it, so the transcript a
chat shows after a reload is the one the server saved. This is the server's
copy of the fold the chat page does (``ui/src/lib/agentChatStream.ts`` and
``runTurn`` in ``AgentChatSessionContext.tsx``): the same trace steps, the
same limits on what is stored, and the same message shapes, so the page renders
a saved answer exactly like one it folded itself. Kept free of I/O.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any, Literal

from qdash.dbmodel.agent_chat_session import AgentChatMessage, AgentChatSteer

if TYPE_CHECKING:
    from collections.abc import Callable

# Bound what a single message adds to the stored session document (as the page does).
MAX_PERSISTED_THINKING = 20_000
MAX_PERSISTED_ARGS = 4_000
MAX_PERSISTED_PROMPT = 12_000
MAX_PERSISTED_OUTPUT = 2_000
# Room for the full arguments of an answer's finished ``write`` calls, shared by them
# in order, so the page can offer the written content after a reload.
MAX_PERSISTED_WRITE_ARGS = 64_000

TurnEnd = Literal["completed", "failed", "stopped", "noop"]

_CLASSIFICATION_OUTCOMES = {"classified", "ambiguous", "failed"}


def _now_ms() -> int:
    return int(time.time() * 1000)


def to_json(value: Any) -> str:
    """JSON as the page writes it (``JSON.stringify``): compact, non-ASCII kept."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Transcript digest (``transcriptDigest`` in ui/src/lib/agentObservedTurn.ts)
# ---------------------------------------------------------------------------


def _imul(a: int, b: int) -> int:
    return (a * b) & 0xFFFFFFFF


def hash64(text: str) -> str:
    """The page's 64-bit hash of ``text`` (cyrb53-style, over UTF-16 code units)."""
    h1 = 0xDEADBEEF
    h2 = 0x41C6CE57
    data = text.encode("utf-16-le", errors="surrogatepass")
    for i in range(0, len(data), 2):
        ch = data[i] | (data[i + 1] << 8)
        h1 = _imul(h1 ^ ch, 2654435761)
        h2 = _imul(h2 ^ ch, 1597334677)
    h1 = _imul(h1 ^ (h1 >> 16), 2246822507)
    h1 ^= _imul(h2 ^ (h2 >> 13), 3266489909)
    h2 = _imul(h2 ^ (h2 >> 16), 2246822507)
    h2 ^= _imul(h1 ^ (h1 >> 13), 3266489909)
    return f"{h2:08x}{h1:08x}"


def transcript_digest(messages: list[AgentChatMessage]) -> str:
    """Each message's role, text, and whether it is a steer, hashed as the page does.

    An answer of a recorded turn counts by its turn, not its text: the server and
    each window fold the same answer with their own timings, and a rating changes it.
    """
    return hash64(
        to_json(
            [
                [
                    m.role,
                    f"@turn:{m.turn_request_id}"
                    if m.role == "assistant" and m.turn_request_id
                    else m.content,
                    1 if m.steer else 0,
                ]
                for m in messages
            ]
        )
    )


# ---------------------------------------------------------------------------
# Trace steps (camelCase keys: they are stored for the page as it stores them)
# ---------------------------------------------------------------------------

Step = dict[str, Any]


def _close_thinking(steps: list[Step], now: int) -> list[Step]:
    return [
        {**s, "endedAt": now} if s["kind"] == "thinking" and "endedAt" not in s else s
        for s in steps
    ]


def _close_open_steps(steps: list[Step], now: int) -> list[Step]:
    closed: list[Step] = []
    for step in steps:
        if step["kind"] == "thinking" and "endedAt" not in step:
            closed.append({**step, "endedAt": now})
        elif step["kind"] == "tool" and step.get("status") == "drafting":
            # A call still being written when the turn ended was never made.
            closed.append({**step, "status": "cancelled", "endedAt": now})
        elif step["kind"] == "tool" and step.get("status") == "running":
            closed.append({**step, "status": "done", "endedAt": now})
        else:
            closed.append(step)
    return closed


def interrupted_content(content: str, now: int | None = None) -> str | None:
    """``content`` of saved progress marked as interrupted, or None if it is no progress.

    For progress of a turn that no process runs any more (its API process restarted and
    a new turn replaced it): the answer so far is kept, marked ``interrupted`` instead of
    ``in_progress``, and its open steps closed as a stopped turn's are.
    """
    try:
        payload = json.loads(content)
    except ValueError:
        return None
    if not isinstance(payload, dict) or payload.get("in_progress") is not True:
        return None
    payload.pop("in_progress")
    payload["interrupted"] = True
    trace = payload.get("trace")
    if isinstance(trace, dict) and isinstance(trace.get("steps"), list):
        steps = trace["steps"]
        closed = _close_open_steps(steps, _now_ms() if now is None else now)
        # A call that was running is closed as done; keep that its end was not seen.
        trace["steps"] = [
            {**c, "interrupted": True}
            if isinstance(s, dict) and s.get("kind") == "tool" and s.get("status") == "running"
            else c
            for s, c in zip(steps, closed, strict=True)
        ]
    return to_json(payload)


def _tool_evaluation(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    prompt = value.get("prompt")
    if not isinstance(prompt, str) or not prompt:
        return None
    result: dict[str, Any] = {"prompt": prompt}
    if isinstance(value.get("model"), str) and value["model"]:
        result["model"] = value["model"]
    if value.get("fallback") is True:
        result["fallback"] = True
    if isinstance(value.get("run_id"), str) and value["run_id"]:
        result["runId"] = value["run_id"]
    if isinstance(value.get("evaluation_id"), str) and value["evaluation_id"]:
        result["evaluationId"] = value["evaluation_id"]
    return result


def _is_probability(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value == value  # not NaN
        and 0 <= value <= 1
    )


def _tool_classification(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    classifier = value.get("classifier")
    outcome = value.get("outcome")
    if not isinstance(classifier, str) or not classifier:
        return None
    if outcome not in _CLASSIFICATION_OUTCOMES:
        return None
    result: dict[str, Any] = {"classifier": classifier, "outcome": outcome}
    if isinstance(value.get("category"), str) and value["category"]:
        result["category"] = value["category"]
    if _is_probability(value.get("probability")):
        result["probability"] = value["probability"]
    margin = value.get("margin")
    if isinstance(margin, (int, float)) and not isinstance(margin, bool) and margin == margin:
        result["margin"] = margin
    ranked = [
        {"category": e["category"], "probability": e["probability"]}
        for e in value.get("probabilities") or []
        if isinstance(e, dict)
        and isinstance(e.get("category"), str)
        and e["category"]
        and _is_probability(e.get("probability"))
    ]
    if ranked:
        result["probabilities"] = ranked
    if isinstance(value.get("reason"), str) and value["reason"]:
        result["reason"] = value["reason"]
    return result


def _answer_start(steps: list[Step]) -> int:
    i = len(steps)
    while i > 0 and steps[i - 1]["kind"] == "text":
        i -= 1
    return i


def _truncate_args(args: Any) -> Any:
    if args is None:
        return None
    try:
        text = to_json(args)
    except (TypeError, ValueError):
        return None
    return f"{text[:MAX_PERSISTED_ARGS]}…" if len(text) > MAX_PERSISTED_ARGS else args


def _json_length(value: Any) -> int | None:
    """Serialized length as the page measures it (UTF-16 code units of ``JSON.stringify``)."""
    try:
        return len(to_json(value).encode("utf-16-le")) // 2
    except (TypeError, ValueError):
        return None


class LiveTurn:
    """What one stretch of the turn streamed: its steps and finished UI blocks."""

    def __init__(self, started_at: int, clock: Callable[[], int]) -> None:
        self.steps: list[Step] = []
        self.blocks: list[dict[str, Any]] = []
        self.started_at = started_at
        self._clock = clock

    def append_delta(self, kind: str, text: str) -> None:
        last = self.steps[-1] if self.steps else None
        if last is not None and last["kind"] == kind:
            self.steps[-1] = {**last, "text": last["text"] + text}
            return
        now = self._clock()
        self.steps = _close_thinking(self.steps, now)
        self.steps.append(
            {"kind": kind, "text": text}
            if kind == "text"
            else {"kind": kind, "text": text, "startedAt": now}
        )

    def start_draft(self, payload: dict[str, Any]) -> None:
        now = self._clock()
        tool = str(payload.get("tool") or "")
        index = payload.get("index")
        self.steps = _close_thinking(self.steps, now)
        self.steps.append(
            {
                "kind": "tool",
                "id": payload.get("id") or f"draft-{tool}-{index}-{now}",
                "tool": tool,
                "label": payload.get("label") or tool,
                "status": "drafting",
                "startedAt": now,
                "draft": {},
                "draftIndex": index,
            }
        )

    def append_args_delta(self, payload: dict[str, Any]) -> None:
        delta = payload.get("delta")
        path = payload.get("path")
        if not isinstance(delta, str) or not delta or not isinstance(path, list):
            return
        key = ".".join(str(p) for p in path)
        for i in range(len(self.steps) - 1, -1, -1):
            s = self.steps[i]
            if (
                s["kind"] == "tool"
                and s.get("status") == "drafting"
                and s.get("draftIndex") == payload.get("index")
            ):
                draft = dict(s.get("draft") or {})
                draft[key] = draft.get(key, "") + delta
                self.steps[i] = {**s, "draft": draft}
                return

    def start_tool(self, payload: dict[str, Any]) -> None:
        now = self._clock()
        call_id = payload.get("id")
        tool = str(payload.get("tool") or "")
        idx = -1
        same_tool = -1
        for i in range(len(self.steps) - 1, -1, -1):
            s = self.steps[i]
            if s["kind"] != "tool" or s.get("status") != "drafting":
                continue
            if call_id is not None and s["id"] == call_id:
                idx = i
                break
            if (
                same_tool == -1
                and s["tool"] == tool
                and (call_id is None or str(s["id"]).startswith("draft-"))
            ):
                same_tool = i
        if idx == -1:
            idx = same_tool
        running: Step = {
            "id": call_id if call_id is not None else f"{tool}-{now}",
            "tool": tool,
            "label": payload.get("label") or tool,
            "status": "running",
        }
        if payload.get("args") is not None:
            running["args"] = payload["args"]
        if idx != -1:
            rest = {k: v for k, v in self.steps[idx].items() if k not in ("draft", "draftIndex")}
            self.steps[idx] = {**rest, **running}
            return
        self.steps = _close_thinking(self.steps, now)
        self.steps.append({"kind": "tool", **running, "startedAt": now})

    def end_tool(self, payload: dict[str, Any]) -> None:
        call_id = payload.get("id")
        tool = payload.get("tool")
        idx = -1
        if call_id is not None:
            for i in range(len(self.steps) - 1, -1, -1):
                s = self.steps[i]
                if s["kind"] == "tool" and s["id"] == call_id and s.get("status") == "running":
                    idx = i
                    break
            if idx == -1:
                idx = next(
                    (
                        i
                        for i, s in enumerate(self.steps)
                        if s["kind"] == "tool" and s["id"] == call_id
                    ),
                    -1,
                )
        else:
            idx = next(
                (
                    i
                    for i, s in enumerate(self.steps)
                    if s["kind"] == "tool" and s["tool"] == tool and s.get("status") == "running"
                ),
                -1,
            )
        if idx == -1:
            return
        step = self.steps[idx]
        figures = [p for p in payload.get("figures") or [] if isinstance(p, str) and p]
        evaluation = _tool_evaluation(payload.get("evaluation"))
        classification = _tool_classification(payload.get("classification"))
        ended: Step = {
            **step,
            "status": "error" if payload.get("is_error") else "done",
            "endedAt": self._clock(),
        }
        if figures:
            ended["figures"] = figures
        if evaluation:
            ended["evaluation"] = evaluation
        if classification:
            ended["classification"] = classification
        if isinstance(payload.get("output"), str) and payload["output"]:
            ended["output"] = payload["output"]
        exit_code = payload.get("exit_code")
        if isinstance(exit_code, (int, float)) and not isinstance(exit_code, bool):
            ended["exitCode"] = exit_code
        self.steps[idx] = ended

    def append_block(self, payload: dict[str, Any]) -> None:
        if payload.get("type") == "ui" and isinstance(payload.get("ui"), dict):
            self.blocks.append(payload)
        elif payload.get("type") == "text" and isinstance(payload.get("content"), str):
            if payload["content"]:
                self.blocks.append({"type": "text", "content": payload["content"], "chart": None})

    def stopped_blocks(self) -> list[dict[str, Any]]:
        """Finished UI blocks, then the answer text streamed so far."""
        partial = "".join(
            s["text"] for s in self.steps[_answer_start(self.steps) :] if s["kind"] == "text"
        )
        return [
            *self.blocks,
            *([{"type": "text", "content": partial, "chart": None}] if partial else []),
        ]

    def trace(self, now: int, *, settle: bool = True) -> dict[str, Any] | None:
        """The steps as stored with the answer (``toPersistedTrace``).

        ``settle``: the turn ended, so a step still open is closed (a call still being
        written was never made). Progress of a running turn keeps them open: a tool
        that runs, or is being written, is not reported as done or as not run.
        """
        steps_now = _close_open_steps(self.steps, now) if settle else list(self.steps)
        work = steps_now[: _answer_start(self.steps)]
        if not work:
            return None
        budget = MAX_PERSISTED_THINKING
        write_budget = MAX_PERSISTED_WRITE_ARGS
        steps: list[Step] = []
        for index, s in enumerate(work):
            if s["kind"] == "thinking":
                text = s["text"][: max(0, budget)]
                budget -= len(text)
                steps.append({**s, "text": text})
            elif s["kind"] == "tool":
                rest = {k: v for k, v in s.items() if k not in ("draft", "draftIndex", "output")}
                # Closing marks a running call done; keep that its end was not seen.
                # Progress keeps the call running, so it is not interrupted.
                interrupted = settle and self.steps[index].get("status") == "running"
                args = _truncate_args(
                    s.get("args") if s.get("args") is not None else s.get("draft")
                )
                full = s.get("args")
                if s["tool"] == "write" and s.get("status") == "done" and not interrupted and full:
                    length = _json_length(full)
                    if length is not None and MAX_PERSISTED_ARGS < length <= write_budget:
                        write_budget -= length
                        args = full
                if args is None:
                    rest.pop("args", None)
                else:
                    rest["args"] = args
                if interrupted:
                    rest["interrupted"] = True
                output = s.get("output")
                if output:
                    rest["output"] = (
                        f"…{output[-MAX_PERSISTED_OUTPUT:]}"
                        if len(output) > MAX_PERSISTED_OUTPUT
                        else output
                    )
                if isinstance(s.get("evaluation"), dict):
                    rest["evaluation"] = {
                        **s["evaluation"],
                        "prompt": s["evaluation"]["prompt"][:MAX_PERSISTED_PROMPT],
                    }
                steps.append(rest)
            else:
                steps.append(s)
        return {"steps": steps, "durationMs": now - self.started_at}


def _result_blocks(payload: dict[str, Any]) -> dict[str, Any]:
    """``resultToBlocks``: a blocks payload, or the payload's text as one block."""
    if isinstance(payload.get("blocks"), list):
        return payload
    text = payload.get("explanation")
    return {
        "blocks": [
            {
                "type": "text",
                "content": text if isinstance(text, str) else to_json(payload),
                "chart": None,
            }
        ],
        "assessment": None,
    }


class TurnTranscript:
    """The messages one turn adds to its chat, folded from the turn's SSE events.

    ``messages()`` is the turn's run as stored: what a run recovered from an
    earlier request placed before the turn's own message, the user's message
    (none for a continue), each part of the answer a steer closed off followed
    by the steer, and the answer so far or its end. Every message carries the
    turn's request ID.
    """

    def __init__(
        self,
        request_id: str,
        user_message: AgentChatMessage | None,
        *,
        clock: Callable[[], int] = _now_ms,
    ) -> None:
        self.request_id = request_id
        self.user_message = user_message
        self._clock = clock
        self.restart()

    def restart(self) -> None:
        """Fold again from the turn's start: a reattached stream replays the turn."""
        self._before: list[AgentChatMessage] = []
        self._after: list[AgentChatMessage] = []
        self._placed: set[str] = set()
        self.turn = LiveTurn(self._clock(), self._clock)
        self.end: TurnEnd | None = None
        self.error: str | None = None
        self._final: AgentChatMessage | None = None

    def _message(self, role: str, content: str, **fields: Any) -> AgentChatMessage:
        return AgentChatMessage(
            role=role, content=content, turn_request_id=self.request_id, **fields
        )

    def _segment(self, payload: Any, now: int) -> AgentChatMessage | None:
        segment = (
            _result_blocks(payload)
            if isinstance(payload, dict)
            else {
                "blocks": [],
                "assessment": None,
            }
        )
        trace = self.turn.trace(now)
        if not segment.get("blocks") and not trace:
            return None
        return self._message(
            "assistant", to_json({**segment, "trace": trace} if trace else segment)
        )

    def apply(self, event: str, data: dict[str, Any]) -> None:
        """Fold one SSE event of the turn."""
        turn = self.turn
        if event == "delta" and isinstance(data.get("text"), str):
            turn.append_delta("text", data["text"])
        elif event == "thinking" and isinstance(data.get("text"), str):
            turn.append_delta("thinking", data["text"])
        elif event == "tool_draft":
            turn.start_draft(data)
        elif event == "tool_args_delta":
            turn.append_args_delta(data)
        elif event == "tool_start":
            turn.start_tool(data)
        elif event == "tool_end":
            turn.end_tool(data)
        elif event == "ui":
            turn.append_block(data)
        elif event == "steer" and data.get("status") == "applied":
            self._place_steer(data)
        elif event == "turn_start":
            # What streamed so far answered a steer of an earlier turn (a run recovered
            # after the runtime restarted): it goes before this turn's message.
            now = self._clock()
            message = self._segment(data.get("result"), now)
            if message is not None:
                self._before.append(message)
            self.turn = LiveTurn(now, self._clock)
        elif event == "result":
            now = self._clock()
            result = {k: v for k, v in data.items() if k != "entry_id"}
            blocks = _result_blocks(result)
            trace = turn.trace(now)
            entry_id = data.get("entry_id")
            self._final = self._message(
                "assistant",
                to_json({**blocks, "trace": trace} if trace else blocks),
                entry_id=entry_id if isinstance(entry_id, str) and entry_id else None,
            )
            self.end = "completed"
        elif event == "noop":
            self.end = "noop"
        elif event == "error":
            self.error = str(data.get("detail") or "Agent failed")
            self.end = "failed"

    def _place_steer(self, data: dict[str, Any]) -> None:
        request_id = data.get("request_id")
        if not isinstance(request_id, str) or request_id in self._placed:
            return
        self._placed.add(request_id)
        now = self._clock()
        segment = self._segment(data.get("result"), now)
        text = data.get("text") if isinstance(data.get("text"), str) else ""
        entry_id = data.get("entry_id") if isinstance(data.get("entry_id"), str) else None
        before_turn = data.get("before_turn") is True and self.user_message is not None
        target = self._before if before_turn else self._after
        if segment is not None:
            target.append(segment)
        if text:
            target.append(
                self._message(
                    "user",
                    text,
                    steer=AgentChatSteer(
                        request_id=request_id,
                        entry_id=entry_id,
                        placement="approximate" if before_turn else "exact",
                    ),
                )
            )
        self.turn = LiveTurn(now, self._clock)

    def _unfinished(self, now: int) -> AgentChatMessage | None:
        """The answer so far of a failed turn, marked ``interrupted``; None if nothing streamed."""
        blocks = self.turn.stopped_blocks()
        trace = self.turn.trace(now)
        if not blocks and not trace:
            return None
        payload: dict[str, Any] = {"blocks": blocks, "assessment": None, "interrupted": True}
        return self._message(
            "assistant", to_json({**payload, "trace": trace} if trace else payload)
        )

    def _streamed(self) -> bool:
        return bool(self.turn.steps or self.turn.blocks)

    def stop(self) -> None:
        """The user stopped the turn: whatever streamed is kept, marked stopped."""
        self.end = "stopped"
        self.error = None

    def messages(self) -> list[AgentChatMessage]:
        """The turn's run as it stands: in progress, or its end once it ended."""
        head = [*self._before, *([self.user_message] if self.user_message else []), *self._after]
        now = self._clock()
        if self.end == "completed" and self._final is not None:
            return [*head, self._final]
        if self.end == "noop":
            return head
        if self.end == "failed":
            if self.user_message is None and not head and not self._streamed():
                # A refused continue changed nothing.
                return head
            error = self._message("assistant", f"Error: {self.error}")
            # What streamed before the failure (progress updates, steps, the answer so far)
            # is kept as an unfinished answer ahead of the error, as a stopped turn keeps it.
            partial = self._unfinished(now)
            return [*head, *([partial] if partial is not None else []), error]
        blocks = self.turn.stopped_blocks()
        trace = self.turn.trace(now, settle=self.end == "stopped")
        if self.end == "stopped":
            payload: dict[str, Any] = {"blocks": blocks, "assessment": None, "stopped": True}
        elif blocks or trace:
            # Still running: the answer so far, marked as such for a page that shows it.
            payload = {"blocks": blocks, "assessment": None, "in_progress": True}
        else:
            return head
        return [
            *head,
            self._message("assistant", to_json({**payload, "trace": trace} if trace else payload)),
        ]
