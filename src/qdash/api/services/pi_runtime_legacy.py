"""Legacy adapter: a runtime's raw NDJSON chat stream, mapped to QDash's SSE contract.

A runtime that speaks the presentation contract (``qdash.agent.contracts.
presentation``) maps a turn's events to what the chat shows itself, and the API
only validates and relays them (``runtime_presentation``). This module keeps the
API's earlier mapping for a runtime that answers the API's ``Accept`` with plain
NDJSON (an older runtime image during an upgrade). It yields the same SSE as the
runtime's mapping for the same events (``agent-runtime/testdata/
presentation-v1.json``); remove it once no deployed runtime predates the contract.
"""

from __future__ import annotations

import json
import logging
import math
import re
from typing import TYPE_CHECKING, Any

from qdash.agent.contracts.presentation import MAX_UI_BLOCK_CHARS
from qdash.api.lib.sse import sse_event
from qdash.api.services.runtime_presentation import STREAM_LOST, evaluation_for_chat

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterable

    from qdash.api.services.pi_chat_service import EvaluationRecorder

logger = logging.getLogger(__name__)

# Runtime tools whose derived label would not say what they do.
_TOOL_LABELS = {"codemode": "Code mode script", "tool_search": "Search tools"}


def tool_label(name: str) -> str:
    """Render a tool name for display.

    Derived rather than looked up: pi-qdash ships 30+ tools and the set changes
    with the package, so a hand-maintained label table would rot. Only the
    agent runtime's own tools named in ``_TOOL_LABELS`` are looked up.
    """
    if name in _TOOL_LABELS:
        return _TOOL_LABELS[name]
    return name.removeprefix("qdash_").replace("_", " ").capitalize() or name


async def translate(
    lines: AsyncIterable[str],
    *,
    extra_result: dict[str, Any] | None = None,
    step: str = "run_chat",
    recorder: EvaluationRecorder | None = None,
) -> AsyncGenerator[str, None]:
    """Turn a legacy runtime NDJSON stream into QDash SSE events.

    ``extra_result`` is merged into the final ``result`` event, which a task
    chat uses to carry ``images_sent``. ``recorder`` stores the evaluations the
    planner makes (the `record` on an evaluation tool's ``tool_end``); the
    chat is told where they were stored and sees the summary only. Kept free
    of HTTP so it can be tested on plain strings.
    """
    # Charts and composed UIs, in the order their tools finished.
    visuals: list[dict[str, Any]] = []
    # Questions and approval requests the turn ended on, rendered as cards.
    interactions: list[dict[str, Any]] = []
    completed_tools: list[str] = []
    ui: dict[str, Any] | None = None

    async for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            kind = event.get("type")

            if kind == "ping":
                # Keepalive from a quiet turn. An SSE comment keeps every proxy
                # on the way to the browser from timing out an idle stream.
                yield ":\n\n"
                continue
            if kind in ("tool_start", "tool_draft"):
                label = tool_label(event["name"])
            elif kind == "tool_args_delta" and not isinstance(event["delta"], str):
                raise TypeError(kind)
            elif kind == "tool_end":
                completed_tools.append(tool_label(event["name"]))
            elif kind == "chart":
                visuals.append({"type": "chart", "content": None, "chart": event["chart"]})
            elif kind == "ui":
                ui = ui_block(event["ui"])
                if ui is not None:
                    visuals.append(ui)
            elif kind == "ask":
                interactions.append(
                    {"type": "ask", "content": None, "chart": None, "ask": event["ask"]}
                )
            elif kind == "approval":
                interactions.append(
                    {
                        "type": "approval",
                        "content": None,
                        "chart": None,
                        "approval": event["approval"],
                    }
                )
            elif kind == "edit":
                # A change proposed to the editor the user has open; the chat shows a diff.
                interactions.append(
                    {"type": "edit", "content": None, "chart": None, "edit": event["edit"]}
                )
            elif (
                kind in ("text_delta", "thinking_delta") and not isinstance(event["delta"], str)
            ) or (kind == "steer" and not isinstance(event["request_id"], str)):
                raise TypeError(kind)
        except (ValueError, KeyError, TypeError):
            logger.warning("Malformed NDJSON line from agent runtime")
            yield sse_event("error", {"step": step, "detail": "Agent runtime sent malformed data"})
            return

        # ``delta``/``thinking``/``tool_draft``/``tool_args_delta``/``tool_start``/
        # ``tool_end`` drive the live transcript in the chat page. ``status``
        # stays for consumers that only show a one-line progress message.
        if kind == "text_delta":
            yield sse_event("delta", {"text": event["delta"]})
        elif kind == "thinking_delta":
            yield sse_event("thinking", {"text": event["delta"]})
        elif kind == "tool_draft":
            # The model is writing a tool call; the chat shows the code as it is typed.
            yield sse_event(
                "tool_draft",
                {
                    "index": event["index"],
                    "id": event.get("id"),
                    "tool": event["name"],
                    "label": label,
                },
            )
        elif kind == "tool_args_delta":
            yield sse_event(
                "tool_args_delta",
                {
                    "index": event["index"],
                    "path": event.get("path") or [],
                    "delta": event["delta"],
                },
            )
        elif kind == "tool_start":
            yield sse_event(
                "tool_start",
                {
                    "id": event.get("id"),
                    "tool": event["name"],
                    "label": label,
                    "args": event.get("args"),
                },
            )
            yield sse_event(
                "status",
                {"step": "tool_call", "tool": event["name"], "message": f"{label}..."},
            )
        elif kind == "tool_end":
            figures = event.get("figures")
            # A result's durable entry names its call the same way in the original
            # stream of the turn and in every replay, whatever ID the model gave it.
            entry_id = event.get("entry_id")
            call = f"entry:{entry_id}" if isinstance(entry_id, str) and entry_id else None
            # A result committed before this turn's message is an earlier turn's (a run
            # recovered after the runtime restarted): this turn never files it.
            shown = event.get("evaluation")
            evaluation = evaluation_for_chat(
                shown,
                shown.get("record") if isinstance(shown, dict) else None,
                None if event.get("before_turn") is True else recorder,
                call=call,
            )
            classification = _classification_for_chat(event.get("classification"))
            calibration_session = _created_calibration_session_for_chat(event)
            yield sse_event(
                "tool_end",
                {
                    "id": event.get("id"),
                    "tool": event["name"],
                    "label": tool_label(event["name"]),
                    "is_error": bool(event.get("isError")),
                    # Figure paths the tool fetched; the chat renders them inline.
                    **({"figures": figures} if isinstance(figures, list) and figures else {}),
                    # What an evaluation tool sent its model; the chat shows it on request.
                    **({"evaluation": evaluation} if isinstance(evaluation, dict) else {}),
                    # What the classifier decided for a ``classify`` call.
                    **({"classification": classification} if classification else {}),
                    # The calibration session a successful create call made, for the chat
                    # to show without another call.
                    **({"calibration_session": calibration_session} if calibration_session else {}),
                    # What a workspace tool (bash, read, write, edit) answered.
                    **(
                        {"output": event["output"]}
                        if isinstance(event.get("output"), str) and event["output"]
                        else {}
                    ),
                    **(
                        {"exit_code": event["exitCode"]}
                        if isinstance(event.get("exitCode"), int)
                        and not isinstance(event.get("exitCode"), bool)
                        else {}
                    ),
                },
            )
            yield sse_event(
                "status",
                {
                    "step": "thinking",
                    "message": "AI is thinking...",
                    "completed_tools": list(completed_tools),
                },
            )
        elif kind == "ui":
            # Shown as soon as its tool finishes, and kept if the user stops the turn.
            if ui is not None:
                yield sse_event("ui", ui)
        elif kind in ("chart", "ask", "approval", "edit"):
            pass
        elif kind == "steer" and event.get("status") == "applied":
            # The user's message landed here in the transcript. What streamed before it
            # is the answer so far: its charts, UIs and, when the steer came after the
            # run's last tool round, the answer it follows up.
            segment = build_blocks_result(str(event.get("answer") or ""), visuals, interactions)
            visuals = []
            interactions = []
            applied: dict[str, Any] = {
                "request_id": event["request_id"],
                "status": "applied",
                "entry_id": event.get("entry_id"),
                "text": str(event.get("text") or ""),
                "result": segment,
            }
            # A run recovered after the runtime died placed it before this turn's
            # message: it belongs to an earlier turn.
            if event.get("before_turn") is True:
                applied["before_turn"] = True
            yield sse_event("steer", applied)
        elif kind == "turn_start":
            # This turn's own message was placed. What streamed before it was a run
            # recovered after the runtime died answering a steer of an earlier turn:
            # it ends here, and the chat keeps it with that turn.
            segment = build_blocks_result(str(event.get("answer") or ""), visuals, interactions)
            visuals = []
            interactions = []
            yield sse_event("turn_start", {"result": segment})
        elif kind == "steer":
            # Settled without being placed: the run failed or was stopped first.
            yield sse_event(
                "steer",
                {
                    "request_id": event["request_id"],
                    "status": "withdrawn",
                    "reason": str(event.get("reason") or ""),
                },
            )
        elif kind == "noop":
            # A continue found the last answer complete: nothing was asked or added.
            yield sse_event("noop", {"reason": str(event.get("reason") or "nothing_to_answer")})
            return
        elif kind == "error":
            failure: dict[str, Any] = {"step": step, "detail": event.get("message", "Agent failed")}
            if isinstance(event.get("code"), str):
                failure["code"] = event["code"]
            yield sse_event("error", failure)
            return
        elif kind == "done":
            if recorder is not None:
                recorder.finish(str(event.get("text") or ""))
            result = build_blocks_result(event.get("text", ""), visuals, interactions)
            # No text and no chart means the turn produced nothing renderable.
            # Local models do this when they emit a malformed tool call, and a
            # silent empty reply is indistinguishable from the UI hanging.
            if not result["blocks"]:
                yield sse_event(
                    "error",
                    {"step": step, "detail": "The model returned an empty response"},
                )
                return
            # The answer's durable entry, so a later request can name it.
            entry_id = event.get("entry_id")
            if isinstance(entry_id, str) and entry_id:
                result["entry_id"] = entry_id
            yield sse_event("status", {"step": "complete", "message": "Done"})
            yield sse_event("result", {**result, **(extra_result or {})})
            return

    yield sse_event(
        "error",
        {
            "step": step,
            "detail": "Agent runtime closed the stream without a result",
            "code": STREAM_LOST,
        },
    )


_CLASSIFICATION_OUTCOMES = frozenset({"classified", "ambiguous", "failed"})
_MAX_CLASSIFICATION_TEXT = 200
_MAX_CLASSIFICATION_CATEGORIES = 8


def _probability(value: Any) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
        and 0 <= value <= 1
    )


def _short_text(value: Any) -> str | None:
    return value[:_MAX_CLASSIFICATION_TEXT] if isinstance(value, str) and value else None


def _classification_for_chat(classification: Any) -> dict[str, Any] | None:
    """The decision of a ``classify`` call that the chat shows under its step.

    Only the known fields pass, bounded: which classifier answered, the
    outcome, the chosen category with its probability and lead, every
    category's probability, and why there was no answer. Anything malformed is
    dropped rather than shown; the classifier's input never reaches the chat.
    """
    if not isinstance(classification, dict):
        return None
    classifier = _short_text(classification.get("classifier"))
    outcome = classification.get("outcome")
    if classifier is None or outcome not in _CLASSIFICATION_OUTCOMES:
        return None
    shown: dict[str, Any] = {"classifier": classifier, "outcome": outcome}
    category = _short_text(classification.get("category"))
    if category is not None:
        shown["category"] = category
    if _probability(classification.get("probability")):
        shown["probability"] = classification["probability"]
    margin = classification.get("margin")
    if isinstance(margin, int | float) and not isinstance(margin, bool) and math.isfinite(margin):
        shown["margin"] = margin
    probabilities = classification.get("probabilities")
    if isinstance(probabilities, list):
        ranked = [
            {"category": name, "probability": entry["probability"]}
            for entry in probabilities
            if isinstance(entry, dict)
            and (name := _short_text(entry.get("category"))) is not None
            and _probability(entry.get("probability"))
        ][:_MAX_CLASSIFICATION_CATEGORIES]
        if ranked:
            shown["probabilities"] = ranked
    reason = _short_text(classification.get("reason"))
    if reason is not None:
        shown["reason"] = reason
    return shown


_CREATE_CALIBRATION_SESSION_TOOL = "qdash_create_calibration_session"
_CALIBRATION_SESSION_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,200}$")


def _created_calibration_session_for_chat(event: dict[str, Any]) -> dict[str, str] | None:
    """The calibration session a ``qdash_create_calibration_session`` call created.

    The runtime reads it from the tool's own result details, never from the model's
    arguments or text. Only a successful call of that tool passes, with a well-formed ID and
    chip; anything else is dropped. The chat reads the session from QDash under the project
    open there, so an ID this lets through still shows nothing QDash does not find.
    """
    if event.get("name") != _CREATE_CALIBRATION_SESSION_TOOL or event.get("isError"):
        return None
    created = event.get("calibrationSession")
    if not isinstance(created, dict):
        return None
    session_id = created.get("calibrationSessionId")
    if not isinstance(session_id, str) or not _CALIBRATION_SESSION_ID.match(session_id):
        return None
    shown = {"calibration_session_id": session_id}
    chip_id = created.get("chipId")
    if isinstance(chip_id, str) and chip_id:
        shown["chip_id"] = chip_id[:200]
    return shown


def ui_block(ui: Any) -> dict[str, Any] | None:
    """The chat block for a runtime ``ui`` event (a ``render_ui`` result).

    The runtime validated the spec against the catalog it shares with the
    chat, which validates it again before rendering. This only bounds what is
    stored: a payload that is not shaped like a versioned block, or is too
    large, keeps its plain-text fallback as a text block, or is dropped.
    """
    if not isinstance(ui, dict):
        return None
    fallback = ui.get("fallback") if isinstance(ui.get("fallback"), str) else ""
    version = ui.get("version")
    spec = ui.get("spec")
    try:
        size = len(json.dumps(ui))
    except (TypeError, ValueError):
        size = MAX_UI_BLOCK_CHARS + 1
    if (
        isinstance(version, int)
        and not isinstance(version, bool)
        and isinstance(spec, dict)
        and size <= MAX_UI_BLOCK_CHARS
    ):
        return {
            "type": "ui",
            # The fallback doubles as the block's text for readers that only know text.
            "content": fallback or None,
            "chart": None,
            "ui": {"version": version, "spec": spec, "fallback": fallback},
        }
    logger.warning("Dropped a malformed ui block from the agent runtime")
    return {"type": "text", "content": fallback, "chart": None} if fallback else None


def build_blocks_result(
    text: str,
    visuals: list[dict[str, Any]],
    interactions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble the blocks payload the chat UI renders.

    ``visuals`` are the chart and ``ui`` blocks the turn's tools produced, in
    order; they precede the answer text. ``assessment`` stays null: the
    runtime answers in free-form text, not a structured verdict.
    """
    blocks: list[dict[str, Any]] = list(visuals)
    if text:
        blocks.append({"type": "text", "content": text, "chart": None})
    blocks.extend(interactions or [])
    return {"blocks": blocks, "assessment": None}
