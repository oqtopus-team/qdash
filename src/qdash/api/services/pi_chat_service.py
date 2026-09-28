"""Bridge between the Copilot chat SSE endpoint and the Pi Agent Runtime.

The runtime speaks NDJSON; this module owns the translation into QDash's SSE
contract and the persistence of Pi conversation state.

See .agent docs: adr/0002 (Mongo owns the conversation) and adr/0005 (NDJSON).
"""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING, Any

import httpx

from qdash.api.lib.sse import sse_event
from qdash.dbmodel.copilot_chat_session import CopilotChatSessionDocument

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterable, Callable

    from qdash.copilot.config import CopilotConfig
    from qdash.copilot.contracts import ChatRequest

logger = logging.getLogger(__name__)

RUNTIME_URL = os.environ.get("PI_AGENT_RUNTIME_URL", "http://agent-runtime:8002")
REQUEST_TIMEOUT_S = float(os.environ.get("PI_AGENT_RUNTIME_TIMEOUT", "300"))

# Maps QDash's reasoning_effort vocabulary onto Pi thinking levels.
_THINKING_LEVELS = {
    "none": "off",
    "minimal": "minimal",
    "low": "low",
    "medium": "medium",
    "high": "high",
}


def tool_label(name: str) -> str:
    """Render a tool name for display.

    Derived rather than looked up: pi-qdash ships 30+ tools and the set changes
    with the package, so a hand-maintained label table would rot.
    """
    return name.removeprefix("qdash_").replace("_", " ").capitalize() or name


def thinking_level(config: CopilotConfig) -> str | None:
    """Map the configured model's reasoning effort onto a Pi thinking level."""
    effort = config.model.reasoning_effort
    return _THINKING_LEVELS.get(effort.lower()) if effort else None


def load_agent_messages(username: str, session_id: str) -> list[dict[str, Any]]:
    """Read stored Pi conversation state. Empty for new or LiteLLM-created chats."""
    doc = CopilotChatSessionDocument.find_one(
        CopilotChatSessionDocument.username == username,
        CopilotChatSessionDocument.session_id == session_id,
    ).run()
    if doc is None or doc.agent_messages is None:
        return []
    return doc.agent_messages


def save_agent_messages(
    username: str,
    session_id: str,
    messages: list[dict[str, Any]],
) -> None:
    """Persist Pi conversation state.

    Only ``agent_messages`` is written here. The display-facing ``messages``
    list stays owned by the frontend, which already PATCHes it after each turn.
    """
    doc = CopilotChatSessionDocument.find_one(
        CopilotChatSessionDocument.username == username,
        CopilotChatSessionDocument.session_id == session_id,
    ).run()
    if doc is None:
        logger.warning(
            "Chat session %s for %s vanished before writeback; agent state not saved",
            session_id,
            username,
        )
        return
    doc.agent_messages = messages
    doc.save()


def _request_payload(
    request: ChatRequest,
    config: CopilotConfig,
    agent_messages: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "conversation_id": request.session_id,
        "message": request.message,
        "messages": agent_messages,
        "model": {"provider": config.model.provider, "name": config.model.name},
        "thinking_level": thinking_level(config),
    }


async def stream(
    request: ChatRequest,
    config: CopilotConfig,
    *,
    username: str,
) -> AsyncGenerator[str, None]:
    """Proxy one chat turn through the Pi Agent Runtime as SSE events."""
    if not request.session_id:
        yield sse_event(
            "error",
            {"step": "init", "detail": "session_id is required by the Pi chat backend"},
        )
        return

    agent_messages = load_agent_messages(username, request.session_id)
    payload = _request_payload(request, config, agent_messages)

    def on_done(messages: list[dict[str, Any]]) -> None:
        save_agent_messages(username, str(request.session_id), messages)

    async for event in stream_payload(payload, on_done=on_done, step="run_chat"):
        yield event


async def stream_payload(
    payload: dict[str, Any],
    *,
    on_done: Callable[[list[dict[str, Any]]], None],
    step: str,
    extra_result: dict[str, Any] | None = None,
) -> AsyncGenerator[str, None]:
    """POST one turn to the runtime and re-emit its NDJSON as SSE.

    Shared by chat and analysis: the two differ only in how the payload is built
    and what they attach to the final result.
    """
    try:
        async with (
            # trust_env=False: the runtime is an internal service, so an ambient
            # HTTP(S)_PROXY must not be applied to it.
            httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S, trust_env=False) as client,
            client.stream("POST", f"{RUNTIME_URL}/chat", json=payload) as response,
        ):
            if response.status_code != httpx.codes.OK:
                await response.aread()
                detail = _status_detail(response)
                yield sse_event("error", {"step": step, "detail": detail})
                return

            async for event in translate(
                response.aiter_lines(),
                on_done=on_done,
                extra_result=extra_result,
                step=step,
            ):
                yield event
    except httpx.HTTPError as exc:
        logger.exception("Pi agent runtime request failed")
        yield sse_event("error", {"step": step, "detail": f"Agent runtime error: {exc}"})


def _status_detail(response: httpx.Response) -> str:
    """Explain a non-200 from the runtime."""
    if response.status_code == httpx.codes.CONFLICT:
        return "Another request is already running for this conversation"
    if response.status_code == httpx.codes.BAD_REQUEST:
        # The runtime rejects models missing from chat.yaml / review.yaml.
        # See .agents/sessions/2026-09-28-analyze-sidebar-pi-agent/adr/0004-*.md
        try:
            return str(response.json().get("error", response.text))
        except ValueError:
            return response.text
    return f"Agent runtime returned HTTP {response.status_code}"


async def translate(
    lines: AsyncIterable[str],
    *,
    on_done: Callable[[list[dict[str, Any]]], None],
    extra_result: dict[str, Any] | None = None,
    step: str = "run_chat",
) -> AsyncGenerator[str, None]:
    """Turn a runtime NDJSON stream into QDash SSE events.

    ``on_done`` receives the final Pi conversation state so the caller can
    persist it. ``extra_result`` is merged into the final ``result`` event,
    which analysis uses to carry ``images_sent``. Kept free of HTTP and database
    access so it can be tested on plain strings.
    """
    charts: list[dict[str, Any]] = []
    completed_tools: list[str] = []

    async for line in lines:
        if not line.strip():
            continue
        event = json.loads(line)
        kind = event.get("type")

        if kind == "tool_start":
            label = tool_label(event["name"])
            yield sse_event(
                "status",
                {"step": "tool_call", "tool": event["name"], "message": f"{label}..."},
            )
        elif kind == "tool_end":
            completed_tools.append(tool_label(event["name"]))
            yield sse_event(
                "status",
                {
                    "step": "thinking",
                    "message": "AI is thinking...",
                    "completed_tools": list(completed_tools),
                },
            )
        elif kind == "chart":
            charts.append(event["chart"])
        elif kind == "error":
            yield sse_event(
                "error",
                {"step": step, "detail": event.get("message", "Agent failed")},
            )
            return
        elif kind == "done":
            on_done(event.get("messages", []))
            result = build_blocks_result(event.get("text", ""), charts)
            # No text and no chart means the turn produced nothing renderable.
            # Local models do this when they emit a malformed tool call, and a
            # silent empty reply is indistinguishable from the UI hanging.
            if not result["blocks"]:
                yield sse_event(
                    "error",
                    {"step": step, "detail": "The model returned an empty response"},
                )
                return
            yield sse_event("status", {"step": "complete", "message": "Done"})
            yield sse_event("result", {**result, **(extra_result or {})})
            return

    yield sse_event(
        "error",
        {"step": step, "detail": "Agent runtime closed the stream without a result"},
    )


def build_blocks_result(text: str, charts: list[dict[str, Any]]) -> dict[str, Any]:
    """Assemble the blocks payload the chat UI renders.

    ``assessment`` stays null: the Pi backend returns free-form text rather than
    the structured verdict the LiteLLM path enforces through a response schema.
    """
    blocks: list[dict[str, Any]] = [
        {"type": "chart", "content": None, "chart": chart} for chart in charts
    ]
    if text:
        blocks.append({"type": "text", "content": text, "chart": None})
    return {"blocks": blocks, "assessment": None}
