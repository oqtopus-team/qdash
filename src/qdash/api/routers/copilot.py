"""Copilot API router: configuration, chats (general and about a task result), sessions."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from fastapi.security import (
    HTTPAuthorizationCredentials,  # noqa: TC002 - FastAPI resolves annotations
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from qdash.api.dependencies import (
    get_copilot_chat_session_service,
    get_copilot_runtime,
    get_evaluation_service,
)
from qdash.api.lib.auth import bearer_scheme, get_current_active_user
from qdash.api.lib.project import get_project_id_from_header
from qdash.api.lib.sse import sse_event
from qdash.api.schemas.auth import User
from qdash.api.schemas.copilot_chat_session import (
    CopilotChatSessionResponse,
    CreateCopilotChatSessionRequest,
    ListCopilotChatSessionsResponse,
    UpdateCopilotChatSessionRequest,
)
from qdash.api.services import pi_chat_service
from qdash.api.services.copilot_chat_session_service import (
    CopilotChatSessionService,
)
from qdash.api.services.evaluation_service import EvaluationService
from qdash.copilot.config import (
    CopilotConfig,
    load_copilot_config,
    select_chat_model,
)
from qdash.copilot.contracts import (
    ChatRequest,
    ChatStopRequest,
    ChatStopResponse,
    SandboxPythonRequest,
    TaskContextBundle,
)
from qdash.copilot.runtime import CopilotRuntime
from qdash.datamodel.task_knowledge import get_task_knowledge

router = APIRouter()
public_router = APIRouter()
logger = logging.getLogger(__name__)


def _config_with_chat_model(config: CopilotConfig, request: ChatRequest) -> CopilotConfig:
    """Resolve the planner for a general chat into ``config.model``."""
    return config.model_copy(
        update={"model": select_chat_model(config, request.chat_model_override)}
    )


@router.get(
    "/config",
    summary="Get Copilot configuration",
    operation_id="getCopilotConfig",
)
async def get_copilot_config() -> dict[str, Any]:
    """Get Copilot configuration for the metrics assistant.

    Retrieves the Copilot configuration from YAML, including:
    - enabled: Whether Copilot is enabled
    - chat_models: The planner models the UI offers
    - evaluation_models: The calibration evaluation model

    Returns
    -------
    dict[str, Any]
        Copilot configuration dictionary

    """
    config = load_copilot_config()
    return dict(config.model_dump())


@public_router.get("/expected-image", include_in_schema=False)
def get_expected_image(task_name: str, index: int) -> Response:
    """Serve a reference/expected figure of a task's knowledge by index."""
    knowledge = get_task_knowledge(task_name)
    if not knowledge or index < 0 or index >= len(knowledge.figures):
        raise HTTPException(status_code=404, detail="Image not found")
    loaded = knowledge.load_figure(knowledge.figures[index].path)
    if loaded is None:
        raise HTTPException(status_code=404, detail="Image file not found")
    data, mime = loaded
    return Response(content=data, media_type=mime)


@router.post("/sandbox/python", include_in_schema=False)
async def run_sandboxed_python(
    request: SandboxPythonRequest,
    _current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict[str, Any]:
    """Run analysis code in the Copilot Python sandbox.

    The restricted sandbox behind the chat's ``run_python`` tool, so the Pi Agent
    Runtime can offer Python without running code itself.
    """
    from qdash.copilot.tooling import execute_python_analysis

    result = await execute_python_analysis(request.code)
    return dict(result)


@router.post("/chat/stop", include_in_schema=False)
async def chat_stop(
    request: ChatStopRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> ChatStopResponse:
    """Stop the turn running for a chat session.

    Closing the SSE stream alone does not cancel the runtime's turn, so the
    chat's Stop button calls this explicitly.
    """
    stopped = await pi_chat_service.abort_runtime_turn(current_user.username, request.session_id)
    return ChatStopResponse(stopped=stopped)


def _figures_status(bundle: TaskContextBundle) -> str | None:
    """Status line for the figures a task chat opens with."""
    has_experiment = bool(bundle.image_base64)
    num_expected = len(bundle.expected_images)
    if has_experiment and num_expected > 0:
        return f"実験結果画像と参照画像{num_expected}枚をAIに送信中..."
    if has_experiment:
        return "実験結果画像をAIに送信中..."
    if num_expected > 0:
        return f"参照画像{num_expected}枚をAIに送信中..."
    return None


@router.post("/chat/stream", include_in_schema=False)
async def chat_stream(
    request: ChatRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    copilot_runtime: Annotated[CopilotRuntime, Depends(get_copilot_runtime)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    project_id: Annotated[str | None, Depends(get_project_id_from_header)],
    evaluation_service: Annotated[EvaluationService, Depends(get_evaluation_service)],
) -> StreamingResponse:
    """SSE streaming chat endpoint.

    A chat is about one task result when ``task`` is set: its first turn then
    opens with the result's context and figures. Otherwise it is a general
    chat, optionally scoped by chip_id/qid.
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        config = load_copilot_config()
        if not config.enabled:
            yield sse_event("error", {"step": "init", "detail": "Copilot is not enabled"})
            return
        chat_config = _config_with_chat_model(config, request)

        task_bundle = None
        images_sent: dict[str, Any] | None = None
        if request.task is not None:
            yield sse_event(
                "status",
                {"step": "build_context", "message": "タスク結果のコンテキストを構築中..."},
            )
            await asyncio.sleep(0)
            task_bundle = copilot_runtime.build_task_context(
                task_name=request.task.task_name,
                chip_id=request.task.chip_id,
                qid=request.task.qid,
                task_id=request.task.task_id,
                image_base64=request.image_base64,
                config=chat_config,
            )
            img_msg = _figures_status(task_bundle)
            if img_msg:
                yield sse_event("status", {"step": "load_images", "message": img_msg})
                await asyncio.sleep(0)
            images_sent = CopilotRuntime.build_images_sent_metadata(
                task_bundle.image_base64,
                task_bundle.figure_paths,
                task_bundle.expected_images,
                request.task.task_name,
                task_bundle.experiment_images,
            )

        effective_project = project_id or current_user.default_project_id
        # The planner's own qcal_evaluate calls are kept as evaluations
        # (trigger "chat"), so every model judgement is on one ledger.
        recorder = (
            evaluation_service.chat_recorder(
                project_id=effective_project,
                username=current_user.username,
                session_id=request.session_id,
                planner_model=f"{chat_config.model.provider}/{chat_config.model.name}",
                task_id=request.task.task_id if request.task else None,
            )
            if effective_project
            else None
        )
        async for event in pi_chat_service.stream(
            request,
            chat_config,
            username=current_user.username,
            auth=pi_chat_service.QDashAuth(
                access_token=credentials.credentials,
                project_id=effective_project,
            ),
            task=task_bundle,
            images_sent=images_sent,
            recorder=recorder,
        ):
            yield event

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/chat/sessions",
    summary="List the current user's chat sessions",
    operation_id="listCopilotChatSessions",
    response_model=ListCopilotChatSessionsResponse,
)
def list_copilot_chat_sessions(
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[CopilotChatSessionService, Depends(get_copilot_chat_session_service)],
) -> ListCopilotChatSessionsResponse:
    """Return all persisted chat sessions owned by the current user."""
    return service.list_sessions(username=current_user.username)


@router.get(
    "/chat/sessions/{session_id}",
    summary="Get a chat session with messages",
    operation_id="getCopilotChatSession",
    response_model=CopilotChatSessionResponse,
)
def get_copilot_chat_session(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[CopilotChatSessionService, Depends(get_copilot_chat_session_service)],
) -> CopilotChatSessionResponse:
    """Return one chat session including the full message list."""
    return service.get_session(username=current_user.username, session_id=session_id)


@router.post(
    "/chat/sessions",
    summary="Create a new chat session",
    operation_id="createCopilotChatSession",
    response_model=CopilotChatSessionResponse,
)
def create_copilot_chat_session(
    request: CreateCopilotChatSessionRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[CopilotChatSessionService, Depends(get_copilot_chat_session_service)],
) -> CopilotChatSessionResponse:
    """Create a new chat session owned by the current user."""
    return service.create_session(username=current_user.username, request=request)


@router.patch(
    "/chat/sessions/{session_id}",
    summary="Update a chat session",
    operation_id="updateCopilotChatSession",
    response_model=CopilotChatSessionResponse,
)
def update_copilot_chat_session(
    session_id: str,
    request: UpdateCopilotChatSessionRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[CopilotChatSessionService, Depends(get_copilot_chat_session_service)],
) -> CopilotChatSessionResponse:
    """Update title, context, or messages of an existing chat session."""
    return service.update_session(
        username=current_user.username,
        session_id=session_id,
        request=request,
    )


@router.delete(
    "/chat/sessions/{session_id}",
    summary="Delete a chat session",
    operation_id="deleteCopilotChatSession",
    response_model=dict[str, bool],
)
async def delete_copilot_chat_session(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[CopilotChatSessionService, Depends(get_copilot_chat_session_service)],
) -> dict[str, bool]:
    """Delete a chat session owned by the current user."""
    service.delete_session(username=current_user.username, session_id=session_id)
    await pi_chat_service.delete_runtime_session_state(current_user.username, session_id)
    return {"deleted": True}
