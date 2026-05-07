"""Forum router for QDash API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from qdash.api.dependencies import get_forum_service  # noqa: TCH002
from qdash.api.lib.project import (  # noqa: TCH002
    ProjectContext,
    get_project_context,
    get_project_context_owner,
)
from qdash.api.schemas.forum import (
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
from qdash.api.services.forum_service import ForumService  # noqa: TCH002

router = APIRouter()


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
) -> list[ForumPostResponse]:
    """List replies for a forum thread."""
    return service.get_replies(project_id=ctx.project_id, post_id=post_id)


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
