"""Forum router for QDash API."""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from qdash.api.dependencies import get_forum_service  # noqa: TCH002
from qdash.api.lib.ai_labels import STATUS_LABELS as _AI_STATUS_LABELS
from qdash.api.lib.ai_labels import TOOL_LABELS as _AI_TOOL_LABELS
from qdash.api.lib.project import (  # noqa: TCH002
    ProjectContext,
    get_project_context,
    get_project_context_owner,
)
from qdash.api.lib.sse import SSETaskBridge, sse_event
from qdash.api.schemas.forum import (
    ForumAiReplyRequest,
    ForumCategoryCreate,
    ForumCategoryResponse,
    ForumCategoryUpdate,
    ForumPostCreate,
    ForumPostResponse,
    ForumPostUpdate,
    ListForumCategoriesResponse,
    ListForumPostsResponse,
)
from qdash.api.schemas.success import SuccessResponse
from qdash.api.services.forum_service import ForumService

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

router = APIRouter()
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
    is_closed: Annotated[
        bool | None,
        Query(
            description=(
                "Filter by closed status. Default false (open only). "
                "Set to true for closed, or omit/null for all."
            )
        ),
    ] = False,
) -> ListForumPostsResponse:
    """List root forum threads for the active project."""
    return service.list_posts(
        project_id=ctx.project_id,
        skip=skip,
        limit=limit,
        category=category,
        is_closed=is_closed,
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
        parent_id=body.parent_id,
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


@router.post("/forum/posts/{post_id}/ai-reply/stream", include_in_schema=False)
async def forum_ai_reply_stream(
    post_id: str,
    body: ForumAiReplyRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[ForumService, Depends(get_forum_service)],
) -> StreamingResponse:
    """SSE endpoint that generates an AI reply in a forum thread."""

    async def event_generator() -> AsyncGenerator[str, None]:
        from qdash.api.lib.copilot_config import load_copilot_config

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

        from qdash.api.services.copilot_data_service import CopilotDataService

        copilot_data_svc = CopilotDataService()
        tool_executors = copilot_data_svc.build_tool_executors()

        clean_message = ForumService.strip_mention(body.user_message)
        if not clean_message:
            clean_message = "この Forum スレッドについてコメントしてください"
        logger.info("Forum AI reply: original=%r, clean=%r", body.user_message, clean_message)

        yield sse_event("status", {"step": "run_chat", "message": "AIが応答中..."})
        bridge = SSETaskBridge(
            tool_labels=_AI_TOOL_LABELS,
            status_labels=_AI_STATUS_LABELS,
        )

        try:
            from qdash.api.lib.copilot_agent import run_chat

            coro = partial(
                run_chat,
                user_message=clean_message,
                config=config,
                chip_id=None,
                qid=None,
                qubit_params=None,
                conversation_history=conversation_history,
                tool_executors=tool_executors,
            )

            result: dict[str, Any] = {}
            async for event in bridge.drain(coro):
                if isinstance(event, str):
                    yield event
                else:
                    result = event
        except ImportError:
            yield sse_event(
                "error",
                {
                    "step": "run_chat",
                    "detail": "openai is not installed. Install with: pip install openai",
                },
            )
            return
        except Exception as e:
            logger.exception("Forum AI reply failed")
            yield sse_event(
                "error",
                {"step": "run_chat", "detail": f"AI reply failed: {e}"},
            )
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
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[ForumService, Depends(get_forum_service)],
) -> ForumPostResponse:
    """Update a forum post. Only the author can edit."""
    return service.update_post(
        project_id=ctx.project_id,
        post_id=post_id,
        username=ctx.user.username,
        title=body.title,
        content=body.content,
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
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[ForumService, Depends(get_forum_service)],
) -> SuccessResponse:
    """Close a forum thread. Only the author or project owner can close."""
    return service.close_post(
        project_id=ctx.project_id,
        post_id=post_id,
        username=ctx.user.username,
        role=ctx.role,
    )


@router.patch(
    "/forum/posts/{post_id}/reopen",
    summary="Reopen a forum thread",
    operation_id="reopenForumPost",
    response_model=SuccessResponse,
)
def reopen_forum_post(
    post_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[ForumService, Depends(get_forum_service)],
) -> SuccessResponse:
    """Reopen a forum thread. Only the author or project owner can reopen."""
    return service.reopen_post(
        project_id=ctx.project_id,
        post_id=post_id,
        username=ctx.user.username,
        role=ctx.role,
    )
