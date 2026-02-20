"""Issue router for QDash API."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from qdash.api.lib.project import (  # noqa: TCH002
    ProjectContext,
    get_project_context,
)
from qdash.api.schemas.issue import (
    IssueCreate,
    IssueResponse,
    ListIssuesResponse,
)
from qdash.api.schemas.success import SuccessResponse
from qdash.datamodel.project import ProjectRole
from qdash.dbmodel.issue import IssueDocument
from starlette.exceptions import HTTPException

router = APIRouter()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# =============================================================================
# Issue endpoints under /issues
# =============================================================================


@router.get(
    "/issues",
    summary="List all issues across tasks",
    operation_id="listIssues",
    response_model=ListIssuesResponse,
)
def list_issues(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    skip: Annotated[int, Query(ge=0, description="Number of items to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=200, description="Max items to return")] = 50,
    task_id: Annotated[str | None, Query(description="Filter by task ID")] = None,
    is_closed: Annotated[
        bool | None,
        Query(
            description="Filter by closed status. Default false (open only). Set to true for closed, or omit/null for all."
        ),
    ] = False,
) -> ListIssuesResponse:
    """List all root issues across the project, with reply counts."""
    query: dict[str, object] = {
        "project_id": ctx.project_id,
        "parent_id": None,
    }
    if task_id:
        query["task_id"] = task_id
    if is_closed is not None:
        query["is_closed"] = is_closed

    total = IssueDocument.find(query).count()

    docs = (
        IssueDocument.find(query)
        .sort("-system_info.created_at")
        .skip(skip)
        .limit(limit)
        .to_list()
    )

    # Collect root issue IDs to get reply counts
    root_ids = [str(doc.id) for doc in docs]

    # Aggregate reply counts for these root issues
    reply_counts: dict[str, int] = {}
    if root_ids:
        pipeline = [
            {
                "$match": {
                    "project_id": ctx.project_id,
                    "parent_id": {"$in": root_ids},
                }
            },
            {"$group": {"_id": "$parent_id", "count": {"$sum": 1}}},
        ]
        results = IssueDocument.aggregate(pipeline).to_list()
        for item in results:
            reply_counts[item["_id"]] = item["count"]

    issues = [
        IssueResponse(
            id=str(doc.id),
            task_id=doc.task_id,
            username=doc.username,
            title=doc.title,
            content=doc.content,
            created_at=doc.system_info.created_at,
            parent_id=doc.parent_id,
            reply_count=reply_counts.get(str(doc.id), 0),
            is_closed=doc.is_closed,
        )
        for doc in docs
    ]

    return ListIssuesResponse(
        issues=issues,
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/issues/{issue_id}",
    summary="Get a single issue by ID",
    operation_id="getIssue",
    response_model=IssueResponse,
)
def get_issue(
    issue_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> IssueResponse:
    """Get a single root issue by its ID, including reply count."""
    from bson import ObjectId

    doc = IssueDocument.find_one(
        {
            "_id": ObjectId(issue_id),
            "project_id": ctx.project_id,
        },
    ).run()

    if doc is None:
        raise HTTPException(status_code=404, detail="Issue not found")

    # Count replies if this is a root issue
    reply_count = 0
    if doc.parent_id is None:
        reply_count = IssueDocument.find(
            {
                "project_id": ctx.project_id,
                "parent_id": issue_id,
            },
        ).count()

    return IssueResponse(
        id=str(doc.id),
        task_id=doc.task_id,
        username=doc.username,
        title=doc.title,
        content=doc.content,
        created_at=doc.system_info.created_at,
        parent_id=doc.parent_id,
        reply_count=reply_count,
        is_closed=doc.is_closed,
    )


@router.get(
    "/issues/{issue_id}/replies",
    summary="List replies for an issue",
    operation_id="getIssueReplies",
    response_model=list[IssueResponse],
)
def get_issue_replies(
    issue_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> list[IssueResponse]:
    """List all replies to a specific issue, sorted by creation time ascending."""
    docs = (
        IssueDocument.find(
            {
                "project_id": ctx.project_id,
                "parent_id": issue_id,
            },
        )
        .sort("system_info.created_at")
        .to_list()
    )

    return [
        IssueResponse(
            id=str(doc.id),
            task_id=doc.task_id,
            username=doc.username,
            title=doc.title,
            content=doc.content,
            created_at=doc.system_info.created_at,
            parent_id=doc.parent_id,
            is_closed=doc.is_closed,
        )
        for doc in docs
    ]


@router.delete(
    "/issues/{issue_id}",
    summary="Delete an issue",
    operation_id="deleteIssue",
    response_model=SuccessResponse,
)
def delete_issue(
    issue_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> SuccessResponse:
    """Delete an issue. Only the author can delete their own issue."""
    from bson import ObjectId

    doc = IssueDocument.find_one(
        {
            "_id": ObjectId(issue_id),
            "project_id": ctx.project_id,
        },
    ).run()

    if doc is None:
        raise HTTPException(status_code=404, detail="Issue not found")

    if doc.username != ctx.user.username:
        raise HTTPException(status_code=403, detail="You can only delete your own issues")

    doc.delete()

    return SuccessResponse(message="Issue deleted")


@router.patch(
    "/issues/{issue_id}/close",
    summary="Close an issue",
    operation_id="closeIssue",
    response_model=SuccessResponse,
)
def close_issue(
    issue_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> SuccessResponse:
    """Close an issue thread. Only the author or project owner can close."""
    from bson import ObjectId

    doc = IssueDocument.find_one(
        {
            "_id": ObjectId(issue_id),
            "project_id": ctx.project_id,
            "parent_id": None,
        },
    ).run()

    if doc is None:
        raise HTTPException(status_code=404, detail="Issue not found")

    if doc.username != ctx.user.username and ctx.role != ProjectRole.OWNER:
        raise HTTPException(
            status_code=403, detail="Only the author or project owner can close this issue"
        )

    doc.is_closed = True
    doc.save()

    return SuccessResponse(message="Issue closed")


@router.patch(
    "/issues/{issue_id}/reopen",
    summary="Reopen an issue",
    operation_id="reopenIssue",
    response_model=SuccessResponse,
)
def reopen_issue(
    issue_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> SuccessResponse:
    """Reopen a closed issue thread. Only the author or project owner can reopen."""
    from bson import ObjectId

    doc = IssueDocument.find_one(
        {
            "_id": ObjectId(issue_id),
            "project_id": ctx.project_id,
            "parent_id": None,
        },
    ).run()

    if doc is None:
        raise HTTPException(status_code=404, detail="Issue not found")

    if doc.username != ctx.user.username and ctx.role != ProjectRole.OWNER:
        raise HTTPException(
            status_code=403, detail="Only the author or project owner can reopen this issue"
        )

    doc.is_closed = False
    doc.save()

    return SuccessResponse(message="Issue reopened")


# =============================================================================
# Issue endpoints under /task-results/{task_id}/issues
# =============================================================================


@router.get(
    "/task-results/{task_id}/issues",
    summary="List issues for a task result",
    operation_id="getTaskResultIssues",
    response_model=list[IssueResponse],
)
def get_task_result_issues(
    task_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> list[IssueResponse]:
    """List all issues for a task result, sorted by creation time ascending."""
    docs = (
        IssueDocument.find(
            {
                "project_id": ctx.project_id,
                "task_id": task_id,
            },
        )
        .sort("system_info.created_at")
        .to_list()
    )

    return [
        IssueResponse(
            id=str(doc.id),
            task_id=doc.task_id,
            username=doc.username,
            title=doc.title,
            content=doc.content,
            created_at=doc.system_info.created_at,
            parent_id=doc.parent_id,
            is_closed=doc.is_closed,
        )
        for doc in docs
    ]


@router.post(
    "/task-results/{task_id}/issues",
    summary="Create an issue on a task result",
    operation_id="createIssue",
    response_model=IssueResponse,
    status_code=201,
)
def create_issue(
    task_id: str,
    body: IssueCreate,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> IssueResponse:
    """Create a new issue on a task result."""
    # Validate: root issues must have a title
    if body.parent_id is None and not body.title:
        raise HTTPException(status_code=422, detail="Title is required for root issues")

    doc = IssueDocument(
        project_id=ctx.project_id,
        task_id=task_id,
        username=ctx.user.username,
        title=body.title if body.parent_id is None else None,
        content=body.content,
        parent_id=body.parent_id,
    )
    doc.insert()

    return IssueResponse(
        id=str(doc.id),
        task_id=doc.task_id,
        username=doc.username,
        title=doc.title,
        content=doc.content,
        created_at=doc.system_info.created_at,
        parent_id=doc.parent_id,
        is_closed=doc.is_closed,
    )
