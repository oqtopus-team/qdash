"""Bridge between the Copilot chat SSE endpoint and the Pi Agent Runtime.

The runtime speaks NDJSON; this module owns the translation into QDash's SSE
contract. Pi owns its durable execution state; MongoDB owns the user-facing
session metadata and rendered messages.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import httpx

from qdash.api.lib.sse import sse_event
from qdash.dbmodel.copilot_chat_session import CopilotChatSessionDocument

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterable

    from qdash.copilot.config import CopilotConfig
    from qdash.copilot.contracts import ChatRequest
    from qdash.copilot.contracts.models import ApprovalDecision

logger = logging.getLogger(__name__)

RUNTIME_URL = os.environ.get("PI_AGENT_RUNTIME_URL", "http://agent-runtime:8002")
# No read timeout: a turn runs until it answers or the user stops it, and a
# tool waiting on a calibration can be quiet for a long time. The runtime pings
# every few seconds (translated to SSE comments below), so a dead runtime still
# surfaces as a closed stream rather than a hang.
REQUEST_TIMEOUT = httpx.Timeout(connect=10.0, read=None, write=30.0, pool=10.0)

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


def _find_session(username: str, session_id: str) -> CopilotChatSessionDocument | None:
    """Find one persisted session from synchronous Bunnet code."""
    return CopilotChatSessionDocument.find_one(
        CopilotChatSessionDocument.username == username,
        CopilotChatSessionDocument.session_id == session_id,
    ).run()


def _ensure_agent_session(username: str, session_id: str) -> None:
    """Create a minimal analysis session when only a browser-cached session exists."""
    if _find_session(username, session_id) is not None:
        return
    from pymongo.errors import DuplicateKeyError

    try:
        CopilotChatSessionDocument(
            username=username,
            session_id=session_id,
            title="Analysis",
        ).insert()
    except DuplicateKeyError:
        # Another request restored the same cached session first.
        return


async def ensure_agent_session(username: str, session_id: str) -> None:
    """Ensure analysis state has a durable destination without blocking the event loop."""
    await asyncio.to_thread(_ensure_agent_session, username, session_id)


async def abort_runtime_turn(username: str, session_id: str) -> bool:
    """Stop the turn the runtime is running for this session, if any.

    Closing the SSE stream alone does not cancel durable work in the runtime,
    so the chat's Stop button calls this. Returns False when nothing was
    running or the runtime could not be reached.
    """
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            response = await client.post(
                f"{RUNTIME_URL}/chat/abort",
                headers=_runtime_headers(),
                json={"owner_id": username, "conversation_id": session_id},
            )
    except (httpx.HTTPError, RuntimeError):
        logger.warning("Could not abort Pi turn for session %s", session_id, exc_info=True)
        return False
    return response.status_code == httpx.codes.OK


async def delete_runtime_session_state(username: str, session_id: str) -> None:
    """Best-effort cleanup of Pi state after its QDash session is deleted."""
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            response = await client.request(
                "DELETE",
                f"{RUNTIME_URL}/session",
                headers=_runtime_headers(),
                json={"owner_id": username, "conversation_id": session_id},
            )
            response.raise_for_status()
    except (httpx.HTTPError, RuntimeError):
        logger.warning(
            "Could not delete Pi durable state for session %s owned by %s",
            session_id,
            username,
            exc_info=True,
        )


@dataclass(frozen=True)
class QDashAuth:
    """User credentials forwarded only in internal headers, never chat payloads."""

    access_token: str = field(repr=False)
    project_id: str | None = None

    def headers(self) -> dict[str, str]:
        if not self.access_token:
            raise RuntimeError("QDash user token is required")
        return {
            "X-QDash-Token": self.access_token,
            **({"X-QDash-Project-Id": self.project_id} if self.project_id else {}),
        }


def _runtime_headers() -> dict[str, str]:
    """Return the internal runtime credential, failing closed when it is absent."""
    token = os.environ.get("AGENT_RUNTIME_TOKEN")
    if not token:
        msg = "AGENT_RUNTIME_TOKEN is required for the Pi Agent Runtime"
        raise RuntimeError(msg)
    return {"Authorization": f"Bearer {token}"}


def _request_payload(
    request: ChatRequest,
    config: CopilotConfig,
    username: str,
) -> dict[str, Any]:
    return {
        "owner_id": username,
        "conversation_id": request.session_id,
        "request_id": request.request_id,
        "message": request.message,
        "model": {"provider": config.model.provider, "name": config.model.name},
        "thinking_level": thinking_level(config),
        # Attached with this turn's message; the runtime fills figure-evaluation
        # tools from the newest image in the conversation.
        **(
            {
                "images": [
                    {"data": image.data, "mimeType": image.mime_type} for image in request.images
                ]
            }
            if request.images
            else {}
        ),
        **approval_payload(request.approval),
    }


def approval_payload(approval: ApprovalDecision | None) -> dict[str, Any]:
    """Forward the user's decision on a pending write operation, if any."""
    return {"approval": approval.model_dump()} if approval else {}


async def stream(
    request: ChatRequest,
    config: CopilotConfig,
    *,
    username: str,
    auth: QDashAuth,
) -> AsyncGenerator[str, None]:
    """Proxy one chat turn through the Pi Agent Runtime as SSE events."""
    if not request.session_id:
        yield sse_event(
            "error",
            {"step": "init", "detail": "session_id is required by the Pi chat backend"},
        )
        return

    payload = _request_payload(request, config, username)
    async for event in stream_payload(payload, step="run_chat", auth=auth):
        yield event


async def stream_payload(
    payload: dict[str, Any],
    *,
    step: str,
    auth: QDashAuth,
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
            httpx.AsyncClient(timeout=REQUEST_TIMEOUT, trust_env=False) as client,
            client.stream(
                "POST",
                f"{RUNTIME_URL}/chat",
                headers={**_runtime_headers(), **auth.headers()},
                json=payload,
            ) as response,
        ):
            if response.status_code != httpx.codes.OK:
                await response.aread()
                detail = _status_detail(response)
                yield sse_event("error", {"step": step, "detail": detail})
                return

            async for event in translate(
                response.aiter_lines(),
                extra_result=extra_result,
                step=step,
            ):
                yield event
    except httpx.HTTPError as exc:
        logger.exception("Pi agent runtime request failed")
        yield sse_event("error", {"step": step, "detail": f"Agent runtime error: {exc}"})
    except RuntimeError:
        logger.exception("Pi agent runtime authentication is not configured")
        yield sse_event(
            "error",
            {"step": step, "detail": "Agent runtime authentication is not configured"},
        )


def _status_detail(response: httpx.Response) -> str:
    """Explain a non-200 from the runtime."""
    if response.status_code == httpx.codes.CONFLICT:
        return "Another request is already running for this conversation"
    if response.status_code == httpx.codes.BAD_REQUEST:
        # The runtime rejects models missing from chat.yaml / review.yaml.
        try:
            return str(response.json().get("error", response.text))
        except ValueError:
            return response.text
    return f"Agent runtime returned HTTP {response.status_code}"


async def translate(
    lines: AsyncIterable[str],
    *,
    extra_result: dict[str, Any] | None = None,
    step: str = "run_chat",
) -> AsyncGenerator[str, None]:
    """Turn a runtime NDJSON stream into QDash SSE events.

    ``extra_result`` is merged into the final ``result`` event, which analysis
    uses to carry ``images_sent``. Kept free of HTTP and database access so it
    can be tested on plain strings.
    """
    charts: list[dict[str, Any]] = []
    # Questions and approval requests the turn ended on, rendered as cards.
    interactions: list[dict[str, Any]] = []
    completed_tools: list[str] = []

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
            if kind == "tool_start":
                label = tool_label(event["name"])
            elif kind == "tool_end":
                completed_tools.append(tool_label(event["name"]))
            elif kind == "chart":
                charts.append(event["chart"])
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
            elif kind in ("text_delta", "thinking_delta") and not isinstance(event["delta"], str):
                raise TypeError(kind)
        except (ValueError, KeyError, TypeError):
            logger.warning("Malformed NDJSON line from agent runtime")
            yield sse_event("error", {"step": step, "detail": "Agent runtime sent malformed data"})
            return

        # ``delta``/``thinking``/``tool_start``/``tool_end`` drive the live
        # transcript in the chat page. ``status`` stays for consumers that only
        # show a one-line progress message.
        if kind == "text_delta":
            yield sse_event("delta", {"text": event["delta"]})
        elif kind == "thinking_delta":
            yield sse_event("thinking", {"text": event["delta"]})
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
            yield sse_event(
                "tool_end",
                {
                    "id": event.get("id"),
                    "tool": event["name"],
                    "label": tool_label(event["name"]),
                    "is_error": bool(event.get("isError")),
                    # Figure paths the tool fetched; the chat renders them inline.
                    **({"figures": figures} if isinstance(figures, list) and figures else {}),
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
        elif kind in ("chart", "ask", "approval"):
            pass
        elif kind == "error":
            yield sse_event(
                "error",
                {"step": step, "detail": event.get("message", "Agent failed")},
            )
            return
        elif kind == "done":
            result = build_blocks_result(event.get("text", ""), charts, interactions)
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


def build_blocks_result(
    text: str,
    charts: list[dict[str, Any]],
    interactions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble the blocks payload the chat UI renders.

    ``assessment`` stays null: the Pi backend returns free-form text rather than
    the structured verdict the LiteLLM path enforces through a response schema.
    """
    blocks: list[dict[str, Any]] = [
        {"type": "chart", "content": None, "chart": chart} for chart in charts
    ]
    if text:
        blocks.append({"type": "text", "content": text, "chart": None})
    blocks.extend(interactions or [])
    return {"blocks": blocks, "assessment": None}
