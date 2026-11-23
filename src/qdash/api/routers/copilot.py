"""Copilot API router: configuration, chats (general and about a task result), sessions."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from fastapi.security import (
    HTTPAuthorizationCredentials,  # noqa: TC002 - FastAPI resolves annotations
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from qdash.api.dependencies import (
    get_copilot_chat_session_service,
    get_copilot_investigation_service,
    get_copilot_runtime,
    get_evaluation_service,
    get_source_access_service,
)
from qdash.api.lib.auth import bearer_scheme, get_current_active_user
from qdash.api.lib.project import (
    ProjectContext,
    get_project_context,
    get_project_id_from_header,
)
from qdash.api.lib.sse import ClosingStreamingResponse, sse_event
from qdash.api.schemas.auth import User
from qdash.api.schemas.copilot_chat_session import (
    CopilotChatSessionResponse,
    CreateCopilotChatBranchRequest,
    CreateCopilotChatSessionRequest,
    ListCopilotChatSessionsResponse,
    UpdateCopilotChatSessionRequest,
)
from qdash.api.schemas.copilot_preferences import (
    CopilotPreferences,
    CopilotPreferencesUpdate,
    CopilotSkillList,
    CopilotSystemPrompt,
)
from qdash.api.schemas.copilot_source import (
    ListSourceRootsResponse,
    SearchSourceResponse,
    SourceFileResponse,
    SourceRootResponse,
    SourceSearchMatch,
)
from qdash.api.services import pi_chat_service
from qdash.api.services.copilot_chat_session_service import (
    ChatUnavailableError,
    CopilotChatSessionService,
    ForkedBranch,
    ReleaseStore,
    RuntimeTarget,
    StopChat,
    StopOutcome,
)
from qdash.api.services.copilot_investigation_service import (
    CopilotInvestigationService,
    InvestigationNotFoundError,
)
from qdash.api.services.evaluation_service import ChatTurnRefusedError, EvaluationService
from qdash.api.services.source_access_service import SourceAccessError, SourceAccessService
from qdash.copilot.config import (
    CopilotConfig,
    load_copilot_config,
    select_chat_model,
)
from qdash.copilot.contracts import (
    ChatRequest,
    ChatSteerRequest,
    ChatSteerResponse,
    ChatSteerStatusRequest,
    ChatStopRequest,
    ChatStopResponse,
    TaskContextBundle,
)
from qdash.copilot.prompts.task_chat import build_language_instruction
from qdash.copilot.runtime import CopilotRuntime
from qdash.datamodel.task_knowledge import get_task_knowledge

router = APIRouter()
public_router = APIRouter()
logger = logging.getLogger(__name__)


async def _runtime_target(username: str, session_id: str) -> RuntimeTarget:
    """Where the runtime keeps the user's chat, from its stored session; never from the request."""
    try:
        return await pi_chat_service.runtime_target(username, session_id)
    except ChatUnavailableError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


def _store_release(username: str, *, attempts: int) -> ReleaseStore:
    """Remove a store no session of the user uses any more, stopping deleted chats' turns."""

    async def release(
        store: str, generation: str, deleted_chats: list[tuple[str, RuntimeTarget]]
    ) -> bool:
        return await pi_chat_service.remove_runtime_store(
            username, store, generation, deleted_chats, attempts=attempts
        )

    return release


def _deleted_chat_stopper(username: str, auth: pi_chat_service.QDashAuth) -> StopChat:
    """Stop exactly one deleted chat's turn, and the work its store kept for it from
    before a restart, reporting whether the runtime confirmed it."""

    async def stop(session_id: str, target: RuntimeTarget) -> StopOutcome:
        return await pi_chat_service.abort_runtime_turn(
            username, session_id, target, stored_with=auth
        )

    return stop


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


@router.post("/chat/stop", include_in_schema=False)
async def chat_stop(
    request: ChatStopRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> ChatStopResponse:
    """Stop the turn running for a chat session.

    Closing the SSE stream alone does not cancel the runtime's turn, so the
    chat's Stop button calls this explicitly. It stops only this chat's turn,
    never one of another branch that shares its store.
    """
    try:
        target = await pi_chat_service.runtime_target(current_user.username, request.session_id)
    except ChatUnavailableError:
        return ChatStopResponse(stopped=False)
    outcome = await pi_chat_service.abort_runtime_turn(
        current_user.username,
        request.session_id,
        target,
        turn_request_id=request.turn_request_id,
    )
    return ChatStopResponse(stopped=outcome == "stopped")


@router.post("/chat/steer", include_in_schema=False)
async def chat_steer(
    request: ChatSteerRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    project_id: Annotated[str | None, Depends(get_project_id_from_header)],
) -> ChatSteerResponse:
    """Send a message to the answer being written for a chat session.

    The running turn reads it after its current step, without starting a new
    one. It reaches only the current user's own running turn, in the same
    project; ``rejected`` means nothing was running and the message should be
    sent as a new one.
    """
    auth = pi_chat_service.QDashAuth(
        access_token=credentials.credentials,
        project_id=project_id or current_user.default_project_id,
    )
    target = await _runtime_target(current_user.username, request.session_id)
    try:
        result = await pi_chat_service.steer_runtime_turn(
            current_user.username,
            request.session_id,
            request_id=request.request_id,
            turn_request_id=request.turn_request_id,
            message=request.message,
            auth=auth,
            target=target,
        )
    except pi_chat_service.SteerRefusedError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except (httpx.HTTPError, RuntimeError) as exc:
        logger.warning("Could not steer Pi turn for session %s", request.session_id, exc_info=True)
        raise HTTPException(status_code=502, detail="The Copilot runtime is not reachable") from exc
    return ChatSteerResponse(**result)


@router.post("/chat/steer/status", include_in_schema=False)
async def chat_steer_status(
    request: ChatSteerStatusRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    project_id: Annotated[str | None, Depends(get_project_id_from_header)],
) -> ChatSteerResponse:
    """Where a message sent while an answer was written stands, without sending it.

    Read-only: it never sends the message or starts a run. The chat asks after
    its stream ended before it saw where the message landed. ``not_found`` means
    it was never admitted, and a request with the same ID will not be admitted
    later; a steer from another project is refused.
    """
    auth = pi_chat_service.QDashAuth(
        access_token=credentials.credentials,
        project_id=project_id or current_user.default_project_id,
    )
    target = await _runtime_target(current_user.username, request.session_id)
    try:
        result = await pi_chat_service.steer_runtime_status(
            current_user.username,
            request.session_id,
            request_id=request.request_id,
            auth=auth,
            target=target,
        )
    except pi_chat_service.SteerRefusedError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except (httpx.HTTPError, RuntimeError) as exc:
        logger.warning("Could not read a steer for session %s", request.session_id, exc_info=True)
        raise HTTPException(status_code=502, detail="The Copilot runtime is not reachable") from exc
    return ChatSteerResponse(**result)


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
    investigation_service: Annotated[
        CopilotInvestigationService, Depends(get_copilot_investigation_service)
    ],
) -> StreamingResponse:
    """SSE streaming chat endpoint.

    A chat is about one task result when ``task`` is set: its first turn then
    opens with the result's context and figures. With ``investigation`` its
    first turn opens with a failed execution's logs, loaded from the user's
    project, and the source the assistant can read. Otherwise it is a general
    chat, optionally scoped by chip_id/qid.
    """
    # Refused here, before streaming, for a branch still being created or a deleted chat.
    target = (
        await _runtime_target(current_user.username, request.session_id)
        if request.session_id
        else None
    )
    investigation_message: str | None = None
    # A continue adds no message: the conversation already holds its opening context.
    # A reattach sends nothing at all.
    if request.investigation is not None and not request.continue_run and not request.reattach:
        if request.task is not None:
            raise HTTPException(
                status_code=400, detail="A chat cannot set both task and investigation"
            )
        # The logs come from the project the user may read, checked before streaming.
        ctx: ProjectContext = await asyncio.to_thread(get_project_context, current_user, project_id)
        try:
            investigation = await asyncio.to_thread(
                investigation_service.build,
                project_id=ctx.project_id,
                target=request.investigation,
                user_message=request.message,
                language_instruction=build_language_instruction(load_copilot_config()),
            )
        except InvestigationNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail=f"Execution {exc} not found in this project"
            ) from exc
        investigation_message = investigation.opening_message

    async def event_generator() -> AsyncGenerator[str, None]:
        config = load_copilot_config()
        if not config.enabled:
            yield sse_event("error", {"step": "init", "detail": "Copilot is not enabled"})
            return
        chat_config = _config_with_chat_model(config, request)

        task_bundle = None
        images_sent: dict[str, Any] | None = None
        if request.task is not None and not request.continue_run and not request.reattach:
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
        # (trigger "chat"), so every model judgement is on one ledger. The turn's
        # first request stores the project, planner model and task it was sent
        # with; every later request of the turn (a retry, or a reattach replaying
        # it) files the turn's evaluations under that record, never under what it
        # says itself. Each call is named by its result's durable entry, so a call
        # two streams of the turn both saw is stored once.
        recorder = None
        if effective_project:
            try:
                recorder = await asyncio.to_thread(
                    evaluation_service.chat_turn_recorder,
                    project_id=effective_project,
                    username=current_user.username,
                    session_id=request.session_id,
                    request_id=request.request_id,
                    planner_model=f"{chat_config.model.provider}/{chat_config.model.name}",
                    task_id=request.task.task_id if request.task else None,
                    reattach=request.reattach,
                )
            except ChatTurnRefusedError as exc:
                yield sse_event(
                    "error", {"step": "init", "detail": exc.detail, "code": "wrong_project"}
                )
                return
            except Exception:
                # The chat still answers; what it evaluates is not filed, as its
                # provenance could not be stored.
                logger.exception("Could not store the chat turn of session %s", request.session_id)
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
            opening_message=investigation_message,
            target=target,
        ):
            yield event

    return ClosingStreamingResponse(
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
async def list_copilot_chat_sessions(
    current_user: Annotated[User, Depends(get_current_active_user)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    service: Annotated[CopilotChatSessionService, Depends(get_copilot_chat_session_service)],
) -> ListCopilotChatSessionsResponse:
    """Return all persisted chat sessions owned by the current user.

    First cleans up, best effort, what failed requests of the user left: a
    branch still pending after its request's lease, and a deleted chat's store
    the runtime could not remove yet.
    """
    username = current_user.username
    try:
        await service.reclaim(
            username=username,
            release_store=_store_release(username, attempts=1),
            stop_chat=_deleted_chat_stopper(
                username,
                pi_chat_service.QDashAuth(
                    access_token=credentials.credentials,
                    project_id=current_user.default_project_id,
                ),
            ),
        )
    except Exception:
        logger.warning("Could not clean up chat sessions of %s", username, exc_info=True)
    return await asyncio.to_thread(service.list_sessions, username=username)


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
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    service: Annotated[CopilotChatSessionService, Depends(get_copilot_chat_session_service)],
) -> dict[str, bool]:
    """Delete a chat session owned by the current user.

    The chat's own running turn is stopped; a turn of another branch is not.
    Its runtime store and workspace are removed with the last session that uses
    them: a chat and its branches share one, so it stays while one is left.
    When the runtime cannot remove the store yet, the deleted chat is kept,
    hidden, and the removal is retried by deleting it again or by the next
    listing of the user's chats.
    """
    username = current_user.username
    # Only proves the user to the runtime: stopping work kept in the store opens no project data.
    auth = pi_chat_service.QDashAuth(
        access_token=credentials.credentials, project_id=current_user.default_project_id
    )
    await service.delete_session(
        username=username,
        session_id=session_id,
        stop_chat=_deleted_chat_stopper(username, auth),
        release_store=_store_release(username, attempts=3),
    )
    return {"deleted": True}


@router.post(
    "/chat/sessions/{session_id}/branches",
    summary="Branch a chat session from one of its answers",
    operation_id="branchCopilotChatSession",
    response_model=CopilotChatSessionResponse,
)
async def branch_copilot_chat_session(
    session_id: str,
    request: CreateCopilotChatBranchRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[CopilotChatSessionService, Depends(get_copilot_chat_session_service)],
) -> CopilotChatSessionResponse:
    """Start a new chat session from a saved answer of one of the user's chats.

    The new session continues the conversation as it was at that answer, in the
    same runtime store: it shares the chat's current workspace files, and the
    chat and its branches answer one at a time. Only a completed answer the chat
    saved with its runtime entry ID qualifies, and only while nothing runs in
    the chat or its branches. The same request again returns the same session.
    """
    username = current_user.username
    auth = pi_chat_service.QDashAuth(
        access_token=credentials.credentials, project_id=ctx.project_id
    )

    async def fork(
        store: str, source_conversation: str | None, entry_id: str, target: str
    ) -> ForkedBranch:
        return await pi_chat_service.fork_runtime_branch(
            username, store, source_conversation, entry_id, target, auth=auth
        )

    try:
        return await service.branch_session(
            username=username,
            source_session_id=session_id,
            request=request,
            project_id=ctx.project_id,
            fork=fork,
            release_store=_store_release(username, attempts=3),
        )
    except (httpx.HTTPError, RuntimeError) as exc:
        logger.warning("Could not branch chat session %s", session_id, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail="The Copilot runtime could not create the branch; try again",
        ) from exc


def _source_error(exc: SourceAccessError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=str(exc))


@router.get(
    "/source/roots",
    response_model=ListSourceRootsResponse,
    summary="List the source trees the Copilot can read",
    operation_id="listCopilotSourceRoots",
)
def list_copilot_source_roots(
    _user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[SourceAccessService, Depends(get_source_access_service)],
) -> ListSourceRootsResponse:
    """QDash and allowlisted dependency source served read-only, with known revisions."""
    return ListSourceRootsResponse(
        roots=[
            SourceRootResponse(
                name=root.name,
                kind=root.kind,
                version=root.version,
                revision=root.revision,
                revision_source=root.revision_source,
                dirty=root.dirty,
            )
            for root in service.roots
        ],
        missing_dependencies=service.missing_dependencies(),
        execution_revision_recorded=False,
    )


@router.get(
    "/source/search",
    response_model=SearchSourceResponse,
    summary="Search the source the Copilot can read",
    operation_id="searchCopilotSource",
)
def search_copilot_source(
    _user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[SourceAccessService, Depends(get_source_access_service)],
    query: Annotated[str, Query(min_length=1, max_length=200)],
    root: Annotated[str | None, Query(max_length=100)] = None,
    path_prefix: Annotated[str | None, Query(max_length=300)] = None,
    mode: Annotated[str, Query(pattern="^(content|path)$")] = "content",
    case_sensitive: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> SearchSourceResponse:
    """Literal search in file contents or file paths; read-only and size-limited."""
    try:
        matches, truncated = service.search(
            query,
            root_name=root,
            path_prefix=path_prefix,
            mode=mode,
            case_sensitive=case_sensitive,
            limit=limit,
        )
    except SourceAccessError as exc:
        raise _source_error(exc) from exc
    return SearchSourceResponse(
        query=query,
        mode=mode,
        matches=[
            SourceSearchMatch(root=m.root, path=m.path, line=m.line, text=m.text) for m in matches
        ],
        truncated=truncated,
    )


@router.get(
    "/source/file",
    response_model=SourceFileResponse,
    summary="Read a line range of a source file",
    operation_id="getCopilotSourceFile",
)
def get_copilot_source_file(
    _user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[SourceAccessService, Depends(get_source_access_service)],
    path: Annotated[str, Query(min_length=1, max_length=500)],
    root: Annotated[str | None, Query(max_length=100)] = None,
    start_line: Annotated[int, Query(ge=1)] = 1,
    end_line: Annotated[int | None, Query(ge=1)] = None,
) -> SourceFileResponse:
    """Read up to 400 numbered lines; without ``root`` the path is matched as a traceback prints it."""
    try:
        source = service.read(root, path, start_line=start_line, end_line=end_line)
    except SourceAccessError as exc:
        raise _source_error(exc) from exc
    revision = next((r.revision for r in service.roots if r.name == source.root), None)
    return SourceFileResponse(
        root=source.root,
        path=source.path,
        start_line=source.start_line,
        end_line=source.end_line,
        total_lines=source.total_lines,
        content=source.content,
        truncated=source.truncated,
        revision=revision,
    )


@router.get(
    "/preferences",
    response_model=CopilotPreferences,
    summary="Get the current user's Copilot preferences",
    operation_id="getCopilotPreferences",
)
def get_copilot_preferences(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> CopilotPreferences:
    """The instructions this user added to their chats."""
    from qdash.dbmodel.user import UserDocument

    user = UserDocument.find_one({"username": current_user.username}).run()
    return CopilotPreferences(instructions=(user.copilot_instructions or "") if user else "")


@router.put(
    "/preferences",
    response_model=CopilotPreferences,
    summary="Update the current user's Copilot preferences",
    operation_id="updateCopilotPreferences",
)
def update_copilot_preferences(
    body: CopilotPreferencesUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> CopilotPreferences:
    """Replace this user's chat instructions; an empty text clears them."""
    from qdash.dbmodel.user import UserDocument

    user = UserDocument.find_one({"username": current_user.username}).run()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    text = body.instructions.strip()
    user.copilot_instructions = text or None
    user.save()
    return CopilotPreferences(instructions=text)


@router.get(
    "/system-prompt",
    response_model=CopilotSystemPrompt,
    summary="Show what QDash tells the chat model",
    operation_id="getCopilotSystemPrompt",
)
async def get_copilot_system_prompt(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> CopilotSystemPrompt:
    """QDash's chat system prompt and this user's instructions as appended to it (read-only)."""
    try:
        result = await pi_chat_service.system_prompt(current_user.username)
    except Exception as exc:
        logger.warning("system prompt unavailable: %s", exc)
        raise HTTPException(status_code=503, detail="The Copilot runtime is not reachable") from exc
    return CopilotSystemPrompt(**result)


@router.get(
    "/skills",
    response_model=CopilotSkillList,
    summary="List the skills a chat message can invoke",
    operation_id="listCopilotSkills",
)
async def list_copilot_skills(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> CopilotSkillList:
    """Skills loaded by the Copilot runtime; a message starting ``/skill:<name>`` runs one."""
    try:
        result = await pi_chat_service.skills()
    except Exception as exc:
        logger.warning("skills unavailable: %s", exc)
        raise HTTPException(status_code=503, detail="The Copilot runtime is not reachable") from exc
    return CopilotSkillList(**result)
