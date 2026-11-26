"""Bridge between the Agent chat SSE endpoint and the Pi Agent Runtime.

The runtime speaks NDJSON; this module owns the translation into QDash's SSE
contract. Pi owns its durable execution state; MongoDB owns the user-facing
session metadata and rendered messages.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

import httpx
from pydantic import ValidationError

from qdash.agent.contracts.models import ChatTurnStart
from qdash.agent.prompts.models import TaskChatPromptOptions
from qdash.agent.prompts.task_chat import build_language_instruction, build_task_chat_prompt
from qdash.api.lib.sse import sse_event
from qdash.api.services.agent_chat_session_service import (
    BranchRefusedError,
    ForkedBranch,
    ForkSettledError,
    RuntimeTarget,
    StopOutcome,
    store_generation,
    store_in_use,
)
from qdash.api.services.agent_chat_session_service import (
    runtime_target as _stored_runtime_target,
)
from qdash.dbmodel.agent_chat_session import AgentChatSessionDocument

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterable

    from qdash.agent.config import AgentConfig
    from qdash.agent.contracts import ChatRequest, TaskContextBundle
    from qdash.agent.contracts.models import ApprovalDecision

logger = logging.getLogger(__name__)

RUNTIME_URL = os.environ.get("PI_AGENT_RUNTIME_URL", "http://agent-runtime:8002")
# Bound on one stored ``ui`` block; the runtime caps the spec itself at 100k characters.
MAX_UI_BLOCK_CHARS = 200_000

# No read timeout: a turn runs until it answers or the user stops it, and a
# tool waiting on a calibration can be quiet for a long time. The runtime pings
# every few seconds (translated to SSE comments below), so a dead runtime still
# surfaces as a closed stream rather than a hang.
REQUEST_TIMEOUT = httpx.Timeout(connect=10.0, read=None, write=30.0, pool=10.0)
# A fork call; the pending branch's lease (BRANCH_LEASE) outlasts it.
FORK_TIMEOUT = 60.0

# Maps QDash's reasoning_effort vocabulary onto Pi thinking levels.
_THINKING_LEVELS = {
    "none": "off",
    "minimal": "minimal",
    "low": "low",
    "medium": "medium",
    "high": "high",
}


# Runtime tools whose derived label would not say what they do.
_TOOL_LABELS = {
    "codemode": "Code mode script",
    "tool_search": "Search tools",
    "delegate_research": "Research subagents",
}


def tool_label(name: str) -> str:
    """Render a tool name for display.

    Derived rather than looked up: pi-qdash ships 30+ tools and the set changes
    with the package, so a hand-maintained label table would rot. Only the
    agent runtime's own tools named in ``_TOOL_LABELS`` are looked up.
    """
    if name in _TOOL_LABELS:
        return _TOOL_LABELS[name]
    return name.removeprefix("qdash_").replace("_", " ").capitalize() or name


def thinking_level(config: AgentConfig) -> str | None:
    """Map the configured model's reasoning effort onto a Pi thinking level."""
    effort = config.model.reasoning_effort
    return _THINKING_LEVELS.get(effort.lower()) if effort else None


def _find_session(username: str, session_id: str) -> AgentChatSessionDocument | None:
    """Find one persisted session from synchronous Bunnet code."""
    return AgentChatSessionDocument.find_one(
        AgentChatSessionDocument.username == username,
        AgentChatSessionDocument.session_id == session_id,
    ).run()


def _ensure_agent_session(username: str, session_id: str) -> None:
    """Create a minimal analysis session when only a browser-cached session exists."""
    if _find_session(username, session_id) is not None:
        return
    if store_in_use(username, session_id):
        # A deleted chat whose branches still use its store; it is not recreated.
        return
    from pymongo.errors import DuplicateKeyError

    try:
        AgentChatSessionDocument(
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


async def runtime_target(username: str, session_id: str) -> RuntimeTarget:
    """Where the runtime keeps the user's chat, resolved from its stored session only.

    Raises ``ChatUnavailableError`` for a branch still being created, or a
    deleted chat whose store its branches still use.
    """
    return await _stored_runtime_target(username, session_id)


def _target_payload(session_id: str, target: RuntimeTarget | None) -> dict[str, str]:
    """The runtime fields naming where a chat lives; a chat never branched is its own store's root."""
    return (target or RuntimeTarget(session_id)).payload()


async def abort_runtime_turn(
    username: str,
    session_id: str,
    target: RuntimeTarget | None = None,
    *,
    stored_with: QDashAuth | None = None,
    turn_request_id: str | None = None,
) -> StopOutcome:
    """Stop the turn the runtime is running for this session, if any.

    Closing the SSE stream alone does not cancel durable work in the runtime,
    so the chat's Stop button calls this. It stops only this chat's turn, never
    one of another branch of the same store. ``stopped``: the runtime stopped
    the turn, or will as soon as its message is admitted. ``not_running``: the
    runtime runs no turn of this chat. ``unknown``: the runtime could not be
    reached or did not answer as expected, so the turn may still run.

    With ``stored_with`` (the user's credentials), for a deleted chat: when no
    turn of it runs, the work the runtime's store kept for it from before a
    restart is stopped too, while the runtime holds the store, without running
    any of it. ``stopped`` then also means that work will run no model or tool
    again; ``not_running``, that there was none.

    With ``turn_request_id``, only the turn that request started is stopped; a
    newer turn of the chat is ``not_running`` for this stop.
    """
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            response = await client.post(
                f"{RUNTIME_URL}/chat/abort",
                headers={
                    **_runtime_headers(),
                    **(stored_with.headers() if stored_with is not None else {}),
                },
                json={
                    "owner_id": username,
                    "conversation_id": session_id,
                    **_target_payload(session_id, target),
                    **({"include_stored": True} if stored_with is not None else {}),
                    **({"turn_request_id": turn_request_id} if turn_request_id else {}),
                },
            )
    except (httpx.HTTPError, RuntimeError):
        logger.warning("Could not abort Pi turn for session %s", session_id, exc_info=True)
        return "unknown"
    if response.status_code == httpx.codes.OK:
        return "stopped"
    if response.status_code == httpx.codes.NOT_FOUND:
        return "not_running"
    logger.warning(
        "Pi runtime answered HTTP %s to stopping session %s", response.status_code, session_id
    )
    return "unknown"


# ``active_runtime_turn`` when the runtime could not say whether a turn runs.
RUNTIME_TURN_UNKNOWN: dict[str, Any] = {"running": False, "unavailable": True}


async def active_runtime_turn(
    username: str,
    session_id: str,
    *,
    auth: QDashAuth,
    target: RuntimeTarget | None = None,
) -> dict[str, Any]:
    """Which turn runs this chat now, read from the runtime's memory.

    Read-only: it opens no store and starts nothing. The runtime names the turn
    only for the user's own chat (``owner_id`` is the signed-in user) in the
    project the turn was sent from. ``running`` false is the runtime's own answer
    that no turn of the chat runs. When the runtime cannot be reached or answers
    unexpectedly, the reply is ``unavailable`` (with ``running`` false): a turn may
    still run, so no caller may take it for ended; the chat asks again later.
    """
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            response = await client.post(
                f"{RUNTIME_URL}/chat/active",
                headers={**_runtime_headers(), **auth.headers()},
                json={
                    "owner_id": username,
                    "conversation_id": session_id,
                    **_target_payload(session_id, target),
                },
            )
        body = response.json() if response.status_code == httpx.codes.OK else None
    except (httpx.HTTPError, RuntimeError, ValueError):
        logger.warning("Could not read the running turn of session %s", session_id, exc_info=True)
        return dict(RUNTIME_TURN_UNKNOWN)
    if not isinstance(body, dict) or not isinstance(body.get("running"), bool):
        logger.warning(
            "Pi runtime answered HTTP %s to reading the running turn of session %s",
            response.status_code,
            session_id,
        )
        return dict(RUNTIME_TURN_UNKNOWN)
    if body["running"] is False:
        return {"running": False}
    if body.get("other_project") is True:
        return {"running": True, "other_project": True}
    request_id = body.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        logger.warning("Pi runtime named no request for the running turn of %s", session_id)
        return dict(RUNTIME_TURN_UNKNOWN)
    started_at = body.get("started_at")
    try:
        turn_start = ChatTurnStart.model_validate(body.get("turn_start")).model_dump()
    except ValidationError:
        turn_start = None
    return {
        "running": True,
        "turn_request_id": request_id,
        "continuing": body.get("continuing") is True,
        "turn_start": turn_start,
        "started_at": int(started_at)
        if isinstance(started_at, (int, float)) and not isinstance(started_at, bool)
        else None,
    }


class SteerRefusedError(Exception):
    """The runtime refused a steer for a reason the user cannot fix by resending it."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


_STEER_STATUSES = ("queued", "applied", "withdrawn", "rejected", "not_found")


async def steer_runtime_turn(
    username: str,
    session_id: str,
    *,
    request_id: str,
    turn_request_id: str,
    message: str,
    auth: QDashAuth,
    target: RuntimeTarget | None = None,
) -> dict[str, Any]:
    """Send a message to the turn running for this session, read before its next step.

    The runtime submits it to the harness the running turn already has open, so
    the turn keeps its own credentials; ``auth`` only proves the caller and must
    name the same project. Only the turn whose request ID is ``turn_request_id``
    admits it. Returns the steer's status (``queued``, ``applied``,
    ``withdrawn``, or ``rejected`` when that turn is not running and the
    runtime's store has never seen this request ID).
    """
    return await _post_steer(
        "/chat/steer",
        {
            "owner_id": username,
            "conversation_id": session_id,
            "request_id": request_id,
            "turn_request_id": turn_request_id,
            "message": message,
            **_target_payload(session_id, target),
        },
        auth,
    )


async def steer_runtime_status(
    username: str,
    session_id: str,
    *,
    request_id: str,
    auth: QDashAuth,
    target: RuntimeTarget | None = None,
) -> dict[str, Any]:
    """Where a steer stands, read from the runtime's store without sending it.

    Never admits the steer or starts a run. ``not_found`` means it was never
    admitted, and the runtime will not admit a request with that ID later: only
    the turn it was sent to could, and the lookup fences it there while that
    turn runs.
    """
    return await _post_steer(
        "/chat/steer/status",
        {
            "owner_id": username,
            "conversation_id": session_id,
            "request_id": request_id,
            **_target_payload(session_id, target),
        },
        auth,
    )


async def _post_steer(path: str, payload: dict[str, Any], auth: QDashAuth) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        response = await client.post(
            f"{RUNTIME_URL}{path}",
            headers={**_runtime_headers(), **auth.headers()},
            json=payload,
        )
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code in (httpx.codes.OK, httpx.codes.CONFLICT) and isinstance(body, dict):
        status = body.get("status")
        if status in _STEER_STATUSES:
            return {
                "status": status,
                "reason": body.get("reason") if isinstance(body.get("reason"), str) else None,
                "entry_id": body.get("entry_id") if isinstance(body.get("entry_id"), str) else None,
            }
    if response.status_code == httpx.codes.FORBIDDEN:
        raise SteerRefusedError(403, "The message belongs to another project")
    detail = body.get("error") if isinstance(body, dict) else None
    raise SteerRefusedError(
        502, str(detail or f"Agent runtime returned HTTP {response.status_code}")
    )


async def fork_runtime_branch(
    username: str,
    store_session_id: str,
    source_conversation_id: str | None,
    entry_id: str,
    target_session_id: str,
    *,
    auth: QDashAuth,
) -> ForkedBranch:
    """Fork the chat's conversation at one answer, in its runtime store.

    Idempotent by ``target_session_id``. Raises ``BranchRefusedError`` when the
    runtime refused the fork (it then created nothing), ``ForkSettledError``
    when the runtime failed it or was never reached, and another
    ``httpx.HTTPError`` when the request may still run there (a timeout).
    """
    generation = await asyncio.to_thread(store_generation, username, store_session_id)
    try:
        async with httpx.AsyncClient(timeout=FORK_TIMEOUT, trust_env=False) as client:
            response = await client.post(
                f"{RUNTIME_URL}/chat/branch",
                headers={**_runtime_headers(), **auth.headers()},
                json={
                    "owner_id": username,
                    "store_session_id": store_session_id,
                    "store_generation": generation,
                    **(
                        {"source_conversation_id": source_conversation_id}
                        if source_conversation_id is not None
                        else {}
                    ),
                    "entry_id": entry_id,
                    "target_session_id": target_session_id,
                },
            )
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        raise ForkSettledError("The agent runtime was not reached") from exc
    try:
        body = response.json()
    except ValueError:
        body = None
    if response.status_code == httpx.codes.OK and isinstance(body, dict):
        conversation_id = body.get("conversation_id")
        if isinstance(conversation_id, str) and conversation_id:
            return ForkedBranch(conversation_id, body.get("created") is True)
    if response.status_code in (400, 404, 409):
        detail = body.get("error") if isinstance(body, dict) else None
        reason = body.get("reason") if isinstance(body, dict) else None
        raise BranchRefusedError(
            response.status_code,
            str(detail or "The answer cannot be branched from"),
            reason if isinstance(reason, str) else None,
        )
    msg = f"Agent runtime returned HTTP {response.status_code}"
    raise ForkSettledError(msg)


async def delete_runtime_session_state(
    username: str, session_id: str, generation: str | None = None
) -> bool:
    """Remove a Pi store and workspace no QDash session uses any more; True once removed.

    ``session_id`` names the store: the chat's own ID, or for branches the
    store they share, removed with the last session that uses it. With
    ``generation``, only that incarnation of the store is removed: True also
    when it is gone already and the store is a newer one, which stays. The
    runtime refuses while a turn, a fork, or another removal holds the store;
    that and any other failure is logged and answers False.
    """
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            response = await client.request(
                "DELETE",
                f"{RUNTIME_URL}/session",
                headers=_runtime_headers(),
                json={
                    "owner_id": username,
                    "conversation_id": session_id,
                    **({"store_generation": generation} if generation is not None else {}),
                },
            )
            response.raise_for_status()
    except (httpx.HTTPError, RuntimeError):
        logger.warning(
            "Could not delete Pi durable state for session %s owned by %s",
            session_id,
            username,
            exc_info=True,
        )
        return False
    return True


async def remove_runtime_store(
    username: str,
    store_session_id: str,
    generation: str,
    deleted_chats: list[tuple[str, RuntimeTarget]],
    *,
    attempts: int = 3,
    retry_delay: float = 0.5,
) -> bool:
    """Remove ``generation`` of a store after its last session was deleted; True once
    the runtime confirmed it is gone.

    When the runtime refuses because a turn still holds the store, the turns
    of ``deleted_chats`` (the deleted chats of that store, each by its exact
    target) are stopped and the removal is tried again, up to ``attempts``
    times. A chat that is not deleted is never stopped. Every call names the
    generation, so one that arrives late removes nothing newer.
    """
    for attempt in range(attempts):
        if await delete_runtime_session_state(username, store_session_id, generation):
            return True
        for session_id, target in deleted_chats:
            await abort_runtime_turn(username, session_id, target)
        if attempt + 1 < attempts:
            await asyncio.sleep(retry_delay * (attempt + 1))
    return False


class EvaluationRecorder(Protocol):
    """Where the evaluations a chat turn's planner makes are stored."""

    def record(self, record: dict[str, Any], call: str | None = None) -> dict[str, str] | None:
        """Store one evaluation record; return its ids, or None when it was not stored.

        ``call`` names the tool call within the turn by its result's durable entry,
        the same way in every stream of the turn, so storing it again from a
        reattached stream stores nothing new. A turn's recorder stores nothing
        without it.
        """
        ...

    def finish(self, answer: str) -> None:
        """The turn's final answer, kept with the evaluations it made."""
        ...


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
    if not token and (token_file := os.environ.get("AGENT_RUNTIME_TOKEN_FILE")):
        token = Path(token_file).read_text().strip()
    if not token:
        msg = "Pi Agent Runtime credential is unavailable"
        raise RuntimeError(msg)
    return {"Authorization": f"Bearer {token}"}


async def system_prompt(username: str) -> dict[str, Any]:
    """The runtime's system prompt for this user's chats, with their own section."""
    instructions = user_instructions(username)
    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
        response = await client.post(
            f"{RUNTIME_URL}/system-prompt",
            json={"user_instructions": instructions} if instructions else {},
            headers=_runtime_headers(),
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result


async def skills() -> dict[str, Any]:
    """The skills the runtime has loaded, which a chat message invokes as ``/skill:<name>``."""
    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
        response = await client.get(f"{RUNTIME_URL}/skills", headers=_runtime_headers())
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result


async def available_chat_models() -> set[tuple[str, str]]:
    """The ``(provider, name)`` of every chat model whose credential the runtime has.

    The agent runtime holds the model credentials, so it alone decides; the API never
    reads them. The answer carries model names and a flag only, never a key.
    """
    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
        response = await client.get(f"{RUNTIME_URL}/chat-models", headers=_runtime_headers())
        response.raise_for_status()
        entries = response.json().get("chat_models")
    if not isinstance(entries, list):
        msg = "The agent runtime's chat model list is malformed"
        raise TypeError(msg)
    return {
        (entry["provider"], entry["name"])
        for entry in entries
        if isinstance(entry, dict)
        and entry.get("available") is True
        and isinstance(entry.get("provider"), str)
        and isinstance(entry.get("name"), str)
    }


def user_instructions(username: str) -> str | None:
    """The user's own Agent instructions, when they set any (chat only)."""
    from qdash.dbmodel.user import UserDocument

    user = UserDocument.find_one({"username": username}).run()
    text = (getattr(user, "agent_instructions", None) or "").strip() if user else ""
    return text or None


def _request_payload(
    request: ChatRequest,
    config: AgentConfig,
    username: str,
    target: RuntimeTarget | None = None,
) -> dict[str, Any]:
    instructions = user_instructions(username)
    return {
        # Chat only: evaluations and forum replies are built elsewhere and stay
        # the same for everyone, so their records remain comparable.
        **({"user_instructions": instructions} if instructions else {}),
        # The page the user has open, rebuilt into the prompt every turn.
        **({"page_context": request.page.model_dump()} if request.page else {}),
        "owner_id": username,
        "conversation_id": request.session_id,
        # Where the chat lives in the runtime, resolved from its stored session.
        **_target_payload(request.session_id or "", target),
        "request_id": request.request_id,
        "message": request.message,
        "model": {"provider": config.model.provider, "name": config.model.name},
        # The user's choice for this turn wins over the model's configured effort.
        "thinking_level": request.thinking_level or thinking_level(config),
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
        # Continue the run that ended without an answer; the message is not sent.
        **({"continue": True} if request.continue_run else {}),
        # Watch the turn ``request_id`` started again; nothing is sent.
        **({"reattach": True} if request.reattach else {}),
        # Where the turn starts in the saved transcript, reported to the user's other windows.
        **(
            {"turn_start": request.turn_start.model_dump()}
            if request.turn_start and not request.reattach
            else {}
        ),
    }


def approval_payload(approval: ApprovalDecision | None) -> dict[str, Any]:
    """Forward the user's decision on a pending write operation, if any."""
    return {"approval": approval.model_dump()} if approval else {}


# A task chat's opening message already holds the result, its parameters,
# task knowledge and figures. Without this, local models re-fetch all of it
# through tools before answering and run out of time or context.
_ANSWERING_GUIDANCE = """\
## How to answer

Everything about this result is already above: its parameters, the task \
knowledge, past cases and the attached figures. Answer from them first. Call a \
tool only when the question needs data that is not here, such as history, \
other qubits or other executions, and keep it to a few targeted calls. Do not \
re-fetch this result, its figures or its task knowledge."""


def collect_task_figures(bundle: TaskContextBundle) -> list[dict[str, str]]:
    """Flatten a task context's figures into Pi image attachments.

    Expected reference images come first, then the measured ones. Pi's
    ``ImageContent`` carries no alt text, so the prompt states the counts and the
    order instead.
    """
    experiment = bundle.experiment_images or (
        [(bundle.image_base64, "result figure")] if bundle.image_base64 else []
    )
    return [
        {"data": data, "mimeType": "image/png"}
        for data, _alt in [*bundle.expected_images, *experiment]
        if data
    ]


def task_opening_context(
    *,
    bundle: TaskContextBundle,
    config: AgentConfig,
    language_instruction: str,
) -> str:
    """The context that opens a chat about one task result, up to the user's message.

    The system prompt body and the language instruction are folded into the
    first message, because the Pi runtime has no separate system-prompt
    channel for it. The text ends where the user's message goes: the runtime
    appends that message itself, after expanding a ``/skill:<name>`` command
    the user typed, so the command still starts the text it reads.
    """
    expected_count = len(bundle.expected_images)
    experiment_count = len(collect_task_figures(bundle)) - expected_count

    body = build_task_chat_prompt(
        TaskChatPromptOptions(
            context=bundle.context,
            language_instruction=language_instruction,
            has_expected_images=expected_count > 0,
            has_experiment_image=experiment_count > 0,
        )
    )

    image_note = (
        f"\n\n## Attached figures\n\n"
        f"{expected_count} expected reference figure(s) first, "
        f"then {experiment_count} figure(s) measured in this run."
        if expected_count or experiment_count
        else ""
    )
    return f"{body}{image_note}\n\n{_ANSWERING_GUIDANCE}\n\n## Your task\n\n"


def task_opening_message(
    *,
    bundle: TaskContextBundle,
    config: AgentConfig,
    user_message: str,
    language_instruction: str,
) -> str:
    """The first message of a chat about one task result, carrying its whole context.

    The model receives this text when the user's message is not a skill
    command; the runtime assembles it from :func:`task_opening_context` and
    the message.
    """
    context = task_opening_context(
        bundle=bundle, config=config, language_instruction=language_instruction
    )
    return f"{context}{user_message}"


async def stream(
    request: ChatRequest,
    config: AgentConfig,
    *,
    username: str,
    auth: QDashAuth,
    task: TaskContextBundle | None = None,
    images_sent: dict[str, Any] | None = None,
    recorder: EvaluationRecorder | None = None,
    opening_message: str | None = None,
    target: RuntimeTarget | None = None,
) -> AsyncGenerator[str, None]:
    """Proxy one chat turn through the Pi Agent Runtime as SSE events.

    With ``task``, the turn belongs to a chat about one task result: a new
    conversation opens with the result's context and figures (the runtime
    attaches them only when the conversation is new, ahead of the user's
    message), and the final result reports which figures were sent.
    ``opening_message`` (an investigation's logs and instructions) likewise
    replaces the first message of a new conversation only; later turns are
    sent as typed.
    """
    if not request.session_id:
        yield sse_event(
            "error",
            {"step": "init", "detail": "session_id is required by the Pi chat backend"},
        )
        return

    payload = _request_payload(request, config, username, target)
    extra_result: dict[str, Any] | None = None
    if request.reattach:
        # The turn already carries its opening context; nothing new is sent.
        pass
    elif opening_message is not None:
        try:
            await ensure_agent_session(username, request.session_id)
        except Exception:
            logger.exception("Failed to ensure persisted Pi chat session")
            yield sse_event(
                "error",
                {"step": "init", "detail": "Could not persist the chat session"},
            )
            return
        payload["initial_message"] = opening_message
    elif task is not None:
        try:
            await ensure_agent_session(username, request.session_id)
        except Exception:
            logger.exception("Failed to ensure persisted Pi chat session")
            yield sse_event(
                "error",
                {"step": "init", "detail": "Could not persist the chat session"},
            )
            return
        # The runtime puts this before the user's message on a new conversation,
        # once it has expanded a `/skill:<name>` command the message starts with.
        payload["initial_context"] = task_opening_context(
            bundle=task,
            config=config,
            language_instruction=build_language_instruction(config),
        )
        payload["initial_images"] = collect_task_figures(task)
        extra_result = {"images_sent": images_sent or {}}

    async for event in stream_payload(
        payload, step="run_chat", auth=auth, extra_result=extra_result, recorder=recorder
    ):
        yield event


async def stream_payload(
    payload: dict[str, Any],
    *,
    step: str,
    auth: QDashAuth,
    extra_result: dict[str, Any] | None = None,
    recorder: EvaluationRecorder | None = None,
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
                error: dict[str, Any] = {"step": step, "detail": detail}
                code = _status_code(response)
                if code is not None:
                    error["code"] = code
                yield sse_event("error", error)
                return

            async for event in translate(
                response.aiter_lines(),
                extra_result=extra_result,
                step=step,
                recorder=recorder,
            ):
                yield event
    except httpx.HTTPError as exc:
        # The connection to the runtime failed or dropped: the turn may still run
        # there, so the chat reattaches instead of reporting a failed answer.
        logger.exception("Pi agent runtime request failed")
        yield sse_event(
            "error",
            {"step": step, "detail": f"Agent runtime error: {exc}", "code": STREAM_LOST},
        )
    except RuntimeError:
        logger.exception("Pi agent runtime authentication is not configured")
        yield sse_event(
            "error",
            {"step": step, "detail": "Agent runtime authentication is not configured"},
        )


# SSE ``error`` codes the chat acts on. ``stream_lost``: the stream to the runtime
# failed or ended before the turn did, so the turn may still be running and the
# chat reattaches with ``reattach``. ``turn_not_found``: a reattach named a turn
# the runtime has no record of. ``turn_boundary_unknown``: a reattach named an
# ended turn whose end the store does not settle yet, so the chat tries again.
# Other codes come from the runtime's own errors.
STREAM_LOST = "stream_lost"
TURN_NOT_FOUND = "turn_not_found"
TURN_BOUNDARY_UNKNOWN = "turn_boundary_unknown"


def _status_code(response: httpx.Response) -> str | None:
    """The ``error`` code of a non-200 from the runtime the chat acts on, if any."""
    if response.status_code in (httpx.codes.NOT_FOUND, httpx.codes.CONFLICT):
        try:
            body = response.json()
        except ValueError:
            body = None
        reason = body.get("reason") if isinstance(body, dict) else None
        if response.status_code == httpx.codes.NOT_FOUND and reason == TURN_NOT_FOUND:
            return TURN_NOT_FOUND
        if response.status_code == httpx.codes.CONFLICT and reason == TURN_BOUNDARY_UNKNOWN:
            return TURN_BOUNDARY_UNKNOWN
    if response.status_code in (
        httpx.codes.BAD_GATEWAY,
        httpx.codes.SERVICE_UNAVAILABLE,
        httpx.codes.GATEWAY_TIMEOUT,
    ):
        return STREAM_LOST
    return None


def _status_detail(response: httpx.Response) -> str:
    """Explain a non-200 from the runtime."""
    if response.status_code == httpx.codes.CONFLICT:
        # A refused continue says why (nothing to continue, waiting for the user).
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict) and body.get("reason") and isinstance(body.get("error"), str):
            return str(body["error"])
        return "Another request is already running for this conversation"
    if response.status_code == httpx.codes.NOT_FOUND:
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict) and isinstance(body.get("error"), str):
            return str(body["error"])
    if response.status_code == httpx.codes.BAD_REQUEST:
        # The runtime rejects models missing from chat.yaml / evaluation.yaml.
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
    recorder: EvaluationRecorder | None = None,
) -> AsyncGenerator[str, None]:
    """Turn a runtime NDJSON stream into QDash SSE events.

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
            elif kind == "tool_update" and (
                not isinstance(event["id"], str) or not isinstance(event["name"], str)
            ):
                raise TypeError(kind)
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
        elif kind == "tool_update":
            # Progress of a running call: the research tasks a ``delegate_research`` call runs.
            subagents = subagents_for_chat(event.get("subagents"))
            if subagents:
                yield sse_event(
                    "tool_progress",
                    {"id": event["id"], "tool": event["name"], "subagents": subagents},
                )
        elif kind == "tool_end":
            figures = event.get("figures")
            # A result's durable entry names its call the same way in the original
            # stream of the turn and in every replay, whatever ID the model gave it.
            entry_id = event.get("entry_id")
            call = f"entry:{entry_id}" if isinstance(entry_id, str) and entry_id else None
            # A result committed before this turn's message is an earlier turn's (a run
            # recovered after the runtime restarted): this turn never files it.
            evaluation = _evaluation_for_chat(
                event.get("evaluation"),
                None if event.get("before_turn") is True else recorder,
                call=call,
            )
            classification = _classification_for_chat(event.get("classification"))
            calibration_session = _created_calibration_session_for_chat(event)
            subagents = subagents_for_chat(event.get("subagents"))
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
                    # The research tasks a ``delegate_research`` call ran and how each ended.
                    **({"subagents": subagents} if subagents else {}),
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


def _evaluation_for_chat(
    evaluation: Any, recorder: EvaluationRecorder | None, *, call: str | None = None
) -> dict[str, Any] | None:
    """The evaluation summary the chat shows, with the record stored and replaced by its ids."""
    if not isinstance(evaluation, dict):
        return None
    record = evaluation.get("record")
    shown = {key: value for key, value in evaluation.items() if key != "record"}
    if recorder is not None and isinstance(record, dict):
        ids = recorder.record(record, call)
        if ids:
            shown.update(ids)
    return shown


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


_SUBAGENT_STATUSES = {"queued", "running", "done", "error", "cancelled", "interrupted"}
# The runtime's bounds (agent-runtime/src/subagent-tool.ts), enforced again here.
_MAX_SUBAGENT_TASKS = 4
_MAX_SUBAGENT_TITLE = 80
_MAX_SUBAGENT_RESULT = 4_000
_MAX_SUBAGENT_ERROR = 400
_MAX_SUBAGENT_ACTIVITY = 80


def _clip(value: str, limit: int) -> str:
    text = value.strip()
    return f"{text[:limit]}…" if len(text) > limit else text


def _finite_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def subagents_for_chat(value: Any) -> list[dict[str, Any]] | None:
    """The research tasks of a ``delegate_research`` call that the chat shows under its step.

    Only the known fields pass, bounded: position, title, status, timing, how many tool
    calls the subagent made, what it is doing, and its answer or error. Anything malformed
    is dropped. The subagents' prompts and tool data never reach the chat this way.
    """
    if not isinstance(value, list):
        return None
    shown: list[dict[str, Any]] = []
    for task in value[:_MAX_SUBAGENT_TASKS]:
        if not isinstance(task, dict):
            continue
        task_id = task.get("id")
        title = task.get("title")
        status = task.get("status")
        if (
            not isinstance(task_id, str)
            or not isinstance(title, str)
            or not isinstance(status, str)
            or status not in _SUBAGENT_STATUSES
        ):
            continue
        calls = task.get("toolCalls")
        item: dict[str, Any] = {
            "id": task_id[:8],
            "title": _clip(title, _MAX_SUBAGENT_TITLE),
            "status": status,
            "tool_calls": max(0, int(calls))
            if isinstance(calls, int | float) and _finite_number(calls)
            else 0,
        }
        for source, target in (("startedAt", "started_at"), ("endedAt", "ended_at")):
            if _finite_number(task.get(source)):
                item[target] = task[source]
        for key, limit in (
            ("activity", _MAX_SUBAGENT_ACTIVITY),
            ("result", _MAX_SUBAGENT_RESULT),
            ("error", _MAX_SUBAGENT_ERROR),
        ):
            text = task.get(key)
            if isinstance(text, str) and text:
                item[key] = _clip(text, limit)
        shown.append(item)
    return shown or None


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


def parse_sse(chunk: str) -> tuple[str, dict[str, Any]] | None:
    """The (event, data) of one SSE chunk this module produced, or None for comments."""
    name: str | None = None
    data: str | None = None
    for line in chunk.strip().splitlines():
        if line.startswith("event: "):
            name = line[len("event: ") :]
        elif line.startswith("data: "):
            data = line[len("data: ") :]
    if name is None or data is None:
        return None
    try:
        parsed = json.loads(data)
    except ValueError:
        return None
    return (name, parsed) if isinstance(parsed, dict) else None


def _thread_transcript(history: list[dict[str, str]]) -> str:
    lines = []
    for message in history:
        who = "AI" if message.get("role") == "assistant" else "User"
        content = (message.get("content") or "").strip()
        if content:
            lines.append(f"[{who}] {content}")
    return "\n\n".join(lines) or "(no earlier posts)"


async def thread_reply(
    *,
    username: str,
    auth: QDashAuth,
    config: AgentConfig,
    scope: str,
    instruction: str,
    history: list[dict[str, str]],
    user_message: str,
) -> AsyncGenerator[str | dict[str, Any], None]:
    """One planner turn that answers the latest post of a thread.

    Yields the runtime's SSE events for progress (tool calls, thinking) as
    strings, then the final blocks result as a dict. The turn runs in a
    throwaway conversation whose state is removed afterwards; the thread
    itself is the memory, passed in as ``history``. When the runtime fails,
    its error event is yielded and no dict follows.
    """
    conversation_id = f"{scope}-{uuid.uuid4().hex}"
    opening = (
        f"{instruction}\n\n{build_language_instruction(config)}\n\n"
        f"## Thread so far\n\n{_thread_transcript(history)}\n\n"
        f"## Latest post to answer\n\n{user_message}"
    )
    payload: dict[str, Any] = {
        "owner_id": username,
        "conversation_id": conversation_id,
        "request_id": uuid.uuid4().hex,
        "message": user_message,
        "initial_message": opening,
        "model": {"provider": config.model.provider, "name": config.model.name},
        "thinking_level": thinking_level(config),
    }
    result: dict[str, Any] | None = None
    try:
        async for sse in stream_payload(payload, step="run_chat", auth=auth):
            parsed = parse_sse(sse)
            if parsed is not None and parsed[0] == "result":
                result = parsed[1]
                continue
            if parsed is not None and parsed[0] == "status" and parsed[1].get("step") == "complete":
                # The caller reports completion once the reply is saved.
                continue
            yield sse
    finally:
        await delete_runtime_session_state(username, conversation_id)
    if result is not None:
        yield result


async def complete_once(
    *,
    username: str,
    auth: QDashAuth,
    config: AgentConfig,
    scope: str,
    prompt: str,
) -> str:
    """One planner turn on ``prompt`` with no history; returns the answer text.

    Raises RuntimeError with the runtime's error detail when the turn fails.
    """
    conversation_id = f"{scope}-{uuid.uuid4().hex}"
    payload: dict[str, Any] = {
        "owner_id": username,
        "conversation_id": conversation_id,
        "request_id": uuid.uuid4().hex,
        "message": prompt,
        "model": {"provider": config.model.provider, "name": config.model.name},
        "thinking_level": thinking_level(config),
    }
    error: str | None = None
    result: dict[str, Any] | None = None
    try:
        async for sse in stream_payload(payload, step="run_chat", auth=auth):
            parsed = parse_sse(sse)
            if parsed is None:
                continue
            if parsed[0] == "result":
                result = parsed[1]
            elif parsed[0] == "error":
                error = str(parsed[1].get("detail") or "Agent runtime error")
    finally:
        await delete_runtime_session_state(username, conversation_id)
    if result is None:
        raise RuntimeError(error or "Agent runtime closed the stream without a result")
    return "\n\n".join(
        str(block.get("content"))
        for block in result.get("blocks", [])
        if block.get("type") == "text" and block.get("content")
    )
