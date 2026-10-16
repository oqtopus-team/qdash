"""Forum router for QDash API."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import (
    HTTPAuthorizationCredentials,  # noqa: TC002 - FastAPI resolves annotations
)

from qdash.api.dependencies import get_forum_service
from qdash.api.lib.auth import bearer_scheme
from qdash.api.lib.project import (
    ProjectContext,
    get_project_context,
    get_project_context_owner,
)
from qdash.api.lib.sse import sse_event
from qdash.api.schemas.forum import (
    ForumAiReplyRequest,
    ForumCategoryCreate,
    ForumCategoryResponse,
    ForumCategoryUpdate,
    ForumImageUploadResponse,
    ForumPostCreate,
    ForumPostResponse,
    ForumPostUpdate,
    ListForumCategoriesResponse,
    ListForumPostsResponse,
)
from qdash.api.schemas.success import SuccessResponse
from qdash.api.services import pi_chat_service
from qdash.api.services.forum_service import ForumService

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

router = APIRouter()
public_router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    "/forum/categories",
    summary="List forum categories",
    operation_id="listForumCategories",
    response_model=ListForumCategoriesResponse,
)
def list_forum_categories(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[ForumService, Depends(get_forum_service)],
    include_archived: Annotated[
        bool,
        Query(description="Include archived categories"),
    ] = False,
) -> ListForumCategoriesResponse:
    """List forum categories for the active project."""
    return service.list_categories(project_id=ctx.project_id, include_archived=include_archived)


@router.post(
    "/forum/categories",
    summary="Create a forum category",
    operation_id="createForumCategory",
    response_model=ForumCategoryResponse,
    status_code=201,
)
def create_forum_category(
    body: ForumCategoryCreate,
    ctx: Annotated[ProjectContext, Depends(get_project_context_owner)],
    service: Annotated[ForumService, Depends(get_forum_service)],
) -> ForumCategoryResponse:
    """Create a forum category. Only project owners can manage categories."""
    return service.create_category(
        project_id=ctx.project_id,
        key=body.key,
        name=body.name,
        description=body.description,
        color=body.color,
        icon=body.icon,
        sort_order=body.sort_order,
    )


@router.patch(
    "/forum/categories/{category_key}",
    summary="Update a forum category",
    operation_id="updateForumCategory",
    response_model=ForumCategoryResponse,
)
def update_forum_category(
    category_key: str,
    body: ForumCategoryUpdate,
    ctx: Annotated[ProjectContext, Depends(get_project_context_owner)],
    service: Annotated[ForumService, Depends(get_forum_service)],
) -> ForumCategoryResponse:
    """Update a forum category. Only project owners can manage categories."""
    return service.update_category(
        project_id=ctx.project_id,
        key=category_key,
        name=body.name,
        description=body.description,
        color=body.color,
        icon=body.icon,
        sort_order=body.sort_order,
        is_archived=body.is_archived,
    )


@router.delete(
    "/forum/categories/{category_key}",
    summary="Archive a forum category",
    operation_id="deleteForumCategory",
    response_model=SuccessResponse,
)
def delete_forum_category(
    category_key: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context_owner)],
    service: Annotated[ForumService, Depends(get_forum_service)],
) -> SuccessResponse:
    """Archive a forum category. Existing threads keep their category key."""
    return service.delete_category(project_id=ctx.project_id, key=category_key)


@router.get(
    "/forum/posts",
    summary="List forum threads",
    operation_id="listForumPosts",
    response_model=ListForumPostsResponse,
)
def list_forum_posts(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[ForumService, Depends(get_forum_service)],
    skip: Annotated[int, Query(ge=0, description="Number of items to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=200, description="Max items to return")] = 50,
    category: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=64,
            pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$",
            description="Filter by category key",
        ),
    ] = None,
    label: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=32,
            pattern=r"^[a-z0-9][a-z0-9_-]{0,31}$",
            description="Filter by thread label",
        ),
    ] = None,
    chip_id: Annotated[
        str | None,
        Query(max_length=128, description="Filter by linked chip ID"),
    ] = None,
    target_type: Annotated[
        str | None,
        Query(pattern=r"^(qubit|coupling)$", description="Filter by linked target type"),
    ] = None,
    target_id: Annotated[
        str | None,
        Query(max_length=128, description="Filter by linked target ID"),
    ] = None,
    cooldown_id: Annotated[
        str | None,
        Query(max_length=128, description="Filter by linked cool-down ID"),
    ] = None,
    task_id: Annotated[
        str | None,
        Query(max_length=128, description="Only threads about this task result"),
    ] = None,
    number: Annotated[
        int | None,
        Query(ge=1, description="Filter by project-scoped forum thread number"),
    ] = None,
    status: Annotated[
        str | None,
        Query(
            pattern=r"^(open|investigating|identified|resolved|all)$",
            description="Filter by workflow status. Default open; 'all' lists every status.",
        ),
    ] = "open",
    q: Annotated[
        str | None,
        Query(
            max_length=128, description="Search title, content, number, target, assignee, or status"
        ),
    ] = None,
) -> ListForumPostsResponse:
    """List root forum threads for the active project."""
    return service.list_posts(
        project_id=ctx.project_id,
        skip=skip,
        limit=limit,
        category=category,
        label=label,
        chip_id=chip_id,
        target_type=target_type,
        target_id=target_id,
        cooldown_id=cooldown_id,
        task_id=task_id,
        number=number,
        status=status,
        q=q,
    )


@router.post(
    "/forum/posts",
    summary="Create a forum thread or reply",
    operation_id="createForumPost",
    response_model=ForumPostResponse,
    status_code=201,
)
def create_forum_post(
    body: ForumPostCreate,
    background_tasks: BackgroundTasks,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[ForumService, Depends(get_forum_service)],
) -> ForumPostResponse:
    """Create a new project forum thread or reply."""
    return service.create_post(
        project_id=ctx.project_id,
        username=ctx.user.username,
        category=body.category,
        title=body.title,
        content=body.content,
        content_blocks=body.content_blocks,
        parent_id=body.parent_id,
        labels=body.labels,
        chip_id=body.chip_id,
        target_type=body.target_type,
        target_id=body.target_id,
        cooldown_id=body.cooldown_id,
        task_id=body.task_id,
        assignee_username=body.assignee_username,
        status=body.status,
        background_tasks=background_tasks,
    )


@router.get(
    "/forum/posts/{post_id}",
    summary="Get a forum post",
    operation_id="getForumPost",
    response_model=ForumPostResponse,
)
def get_forum_post(
    post_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[ForumService, Depends(get_forum_service)],
) -> ForumPostResponse:
    """Get a forum post by ID."""
    return service.get_post(project_id=ctx.project_id, post_id=post_id)


@router.get(
    "/forum/posts/{post_id}/replies",
    summary="List forum replies",
    operation_id="getForumPostReplies",
    response_model=list[ForumPostResponse],
)
def get_forum_post_replies(
    post_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[ForumService, Depends(get_forum_service)],
    skip: Annotated[int, Query(ge=0, description="Number of replies to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=200, description="Max replies to return")] = 100,
) -> list[ForumPostResponse]:
    """List replies for a forum thread."""
    return service.get_replies(project_id=ctx.project_id, post_id=post_id, skip=skip, limit=limit)


@router.post(
    "/forum/upload-image",
    summary="Upload an image for a forum post",
    operation_id="uploadForumImage",
    response_model=ForumImageUploadResponse,
    responses={400: {"description": "Unsupported image type or image exceeds the 5 MB limit"}},
)
async def upload_forum_image(
    file: UploadFile,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> ForumImageUploadResponse:
    """Upload an image to attach to a forum post. Returns the image URL."""
    data = await file.read()
    url = ForumService.upload_image(data, file.content_type or "")
    return ForumImageUploadResponse(url=url)


@public_router.get(
    "/forum/images/{filename}",
    summary="Serve a forum image",
    include_in_schema=False,
)
def get_forum_image(filename: str) -> FileResponse:
    """Serve an uploaded forum image."""
    filepath, media_type = ForumService.get_image_path(filename)
    return FileResponse(filepath, media_type=media_type)


_FORUM_REPLY_INSTRUCTION = """\
You are replying inside a QDash forum thread of a quantum calibration team.
Answer the latest post as a reply: concise markdown, grounded in the thread and in
QDash data (use your tools when the question needs data that is not in the thread).
Do not repeat the thread or restate the question."""


@router.post("/forum/posts/{post_id}/ai-reply/stream", include_in_schema=False)
async def forum_ai_reply_stream(
    post_id: str,
    body: ForumAiReplyRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[ForumService, Depends(get_forum_service)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> StreamingResponse:
    """SSE endpoint that generates an AI reply in a forum thread."""

    async def event_generator() -> AsyncGenerator[str, None]:
        """Yield SSE-formatted events as the AI reply is generated."""
        from qdash.copilot.config import load_copilot_config

        config = load_copilot_config()
        if not config.enabled:
            yield sse_event("error", {"step": "init", "detail": "Copilot is not enabled"})
            return

        yield sse_event("status", {"step": "load_forum", "message": "Forumを読み込み中..."})
        await asyncio.sleep(0)

        ai_context = service.build_ai_reply_context(project_id=ctx.project_id, post_id=post_id)
        if ai_context["root_doc"] is None:
            yield sse_event("error", {"step": "load_forum", "detail": "Forum post not found"})
            return

        yield sse_event("status", {"step": "build_history", "message": "スレッド履歴を構築中..."})
        await asyncio.sleep(0)

        conversation_history: list[dict[str, str]] = ai_context["conversation_history"]
        actual_root_id: str = ai_context["actual_root_id"]
        conversation_history = ForumService.deduplicate_last_message(
            conversation_history,
            body.user_message,
        )

        clean_message = ForumService.strip_mention(body.user_message)
        if not clean_message:
            clean_message = "この Forum スレッドについてコメントしてください"
        logger.info("Forum AI reply: original=%r, clean=%r", body.user_message, clean_message)

        yield sse_event("status", {"step": "run_chat", "message": "AIが応答中..."})
        result: dict[str, Any] | None = None
        async for event in pi_chat_service.thread_reply(
            username=ctx.user.username,
            auth=pi_chat_service.QDashAuth(credentials.credentials, ctx.project_id),
            config=config,
            scope="forum",
            instruction=_FORUM_REPLY_INSTRUCTION,
            history=conversation_history,
            user_message=clean_message,
        ):
            if isinstance(event, dict):
                result = event
            else:
                yield event
        if result is None:
            # The runtime's error event has already been forwarded.
            return

        yield sse_event("status", {"step": "save_reply", "message": "返信を保存中..."})
        await asyncio.sleep(0)

        markdown_content = ForumService.format_ai_response_as_markdown(result)
        if not markdown_content:
            yield sse_event(
                "error",
                {"step": "save_reply", "detail": "AIが空の応答を返しました"},
            )
            return

        saved_response = service.save_ai_reply(
            project_id=ctx.project_id,
            parent_id=actual_root_id,
            content=markdown_content,
        )

        yield sse_event("status", {"step": "complete", "message": "完了"})
        yield sse_event("result", saved_response.model_dump(mode="json"))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.patch(
    "/forum/posts/{post_id}",
    summary="Update a forum post",
    operation_id="updateForumPost",
    response_model=ForumPostResponse,
)
def update_forum_post(
    post_id: str,
    body: ForumPostUpdate,
    background_tasks: BackgroundTasks,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[ForumService, Depends(get_forum_service)],
) -> ForumPostResponse:
    """Update a forum post, or update root-thread metadata as a project editor."""
    # Distinguish "content_blocks omitted" (leave unchanged) from "explicitly []"
    # (clear); the default_factory makes both look like [] on the model otherwise.
    content_blocks = body.content_blocks if "content_blocks" in body.model_fields_set else None
    update_target_context = bool(
        {"chip_id", "target_type", "target_id"}.intersection(body.model_fields_set)
    )
    update_cooldown_context = "cooldown_id" in body.model_fields_set
    update_assignee_context = "assignee_username" in body.model_fields_set
    update_status_context = "status" in body.model_fields_set
    return service.update_post(
        project_id=ctx.project_id,
        post_id=post_id,
        username=ctx.user.username,
        category=body.category,
        title=body.title,
        content=body.content,
        content_blocks=content_blocks,
        labels=body.labels,
        chip_id=body.chip_id,
        target_type=body.target_type,
        target_id=body.target_id,
        cooldown_id=body.cooldown_id,
        assignee_username=body.assignee_username,
        status=body.status,
        update_cooldown_context=update_cooldown_context,
        update_target_context=update_target_context,
        update_assignee_context=update_assignee_context,
        update_status_context=update_status_context,
        role=ctx.role,
        background_tasks=background_tasks,
    )


@router.delete(
    "/forum/posts/{post_id}",
    summary="Delete a forum post",
    operation_id="deleteForumPost",
    response_model=SuccessResponse,
)
def delete_forum_post(
    post_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[ForumService, Depends(get_forum_service)],
) -> SuccessResponse:
    """Delete a forum post. Only the author can delete."""
    return service.delete_post(
        project_id=ctx.project_id,
        post_id=post_id,
        username=ctx.user.username,
        role=ctx.role,
    )


@router.patch(
    "/forum/posts/{post_id}/close",
    summary="Close a forum thread",
    operation_id="closeForumPost",
    response_model=SuccessResponse,
)
def close_forum_post(
    post_id: str,
    background_tasks: BackgroundTasks,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[ForumService, Depends(get_forum_service)],
) -> SuccessResponse:
    """Close a forum thread. Only the author or project owner can close."""
    return service.close_post(
        project_id=ctx.project_id,
        post_id=post_id,
        username=ctx.user.username,
        role=ctx.role,
        background_tasks=background_tasks,
    )


@router.patch(
    "/forum/posts/{post_id}/reopen",
    summary="Reopen a forum thread",
    operation_id="reopenForumPost",
    response_model=SuccessResponse,
)
def reopen_forum_post(
    post_id: str,
    background_tasks: BackgroundTasks,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[ForumService, Depends(get_forum_service)],
) -> SuccessResponse:
    """Reopen a forum thread. Only the author or project owner can reopen."""
    return service.reopen_post(
        project_id=ctx.project_id,
        post_id=post_id,
        username=ctx.user.username,
        role=ctx.role,
        background_tasks=background_tasks,
    )
