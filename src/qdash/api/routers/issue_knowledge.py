"""Router for issue-derived knowledge case management."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from qdash.api.dependencies import get_issue_knowledge_service, get_issue_service  # noqa: TCH002
from qdash.api.lib.project import (  # noqa: TCH002
    ProjectContext,
    get_project_context,
)
from qdash.api.schemas.issue_knowledge import (
    IssueKnowledgeResponse,
    IssueKnowledgeUpdate,
    ListIssueKnowledgeResponse,
)
from qdash.api.schemas.success import SuccessResponse
from qdash.api.services.issue_knowledge_service import IssueKnowledgeService  # noqa: TCH002
from qdash.api.services.issue_service import IssueService  # noqa: TCH002

router = APIRouter()


@router.get(
    "/issue-knowledge",
    summary="List knowledge cases",
    operation_id="listIssueKnowledge",
    response_model=ListIssueKnowledgeResponse,
)
def list_issue_knowledge(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[IssueKnowledgeService, Depends(get_issue_knowledge_service)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    status: Annotated[
        str | None, Query(description="Filter by status: draft, approved, rejected")
    ] = None,
    task_name: Annotated[str | None, Query(description="Filter by task name")] = None,
) -> ListIssueKnowledgeResponse:
    """List issue-derived knowledge cases with optional filters."""
    return service.list_knowledge(
        project_id=ctx.project_id,
        skip=skip,
        limit=limit,
        status=status,
        task_name=task_name,
    )


@router.get(
    "/issue-knowledge/{knowledge_id}",
    summary="Get a knowledge case",
    operation_id="getIssueKnowledge",
    response_model=IssueKnowledgeResponse,
)
def get_issue_knowledge(
    knowledge_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[IssueKnowledgeService, Depends(get_issue_knowledge_service)],
) -> IssueKnowledgeResponse:
    """Get a single knowledge case by ID."""
    return service.get_knowledge(project_id=ctx.project_id, knowledge_id=knowledge_id)


@router.post(
    "/issues/{issue_id}/extract-knowledge",
    summary="Generate knowledge draft from issue",
    operation_id="extractIssueKnowledge",
    response_model=IssueKnowledgeResponse,
    status_code=201,
)
async def extract_issue_knowledge(
    issue_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[IssueKnowledgeService, Depends(get_issue_knowledge_service)],
    issue_service: Annotated[IssueService, Depends(get_issue_service)],
) -> IssueKnowledgeResponse:
    """Generate an AI knowledge draft from a closed issue thread."""
    return await service.generate_draft(
        project_id=ctx.project_id,
        issue_id=issue_id,
        issue_service=issue_service,
    )


@router.patch(
    "/issue-knowledge/{knowledge_id}",
    summary="Update a knowledge draft",
    operation_id="updateIssueKnowledge",
    response_model=IssueKnowledgeResponse,
)
def update_issue_knowledge(
    knowledge_id: str,
    body: IssueKnowledgeUpdate,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[IssueKnowledgeService, Depends(get_issue_knowledge_service)],
) -> IssueKnowledgeResponse:
    """Update a knowledge draft's content. Only drafts can be edited."""
    return service.update_knowledge(
        project_id=ctx.project_id,
        knowledge_id=knowledge_id,
        title=body.title,
        severity=body.severity,
        symptom=body.symptom,
        root_cause=body.root_cause,
        resolution=body.resolution,
        lesson_learned=body.lesson_learned,
    )


@router.patch(
    "/issue-knowledge/{knowledge_id}/approve",
    summary="Approve a knowledge draft",
    operation_id="approveIssueKnowledge",
    response_model=IssueKnowledgeResponse,
)
def approve_issue_knowledge(
    knowledge_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[IssueKnowledgeService, Depends(get_issue_knowledge_service)],
) -> IssueKnowledgeResponse:
    """Approve a knowledge draft for inclusion in task knowledge."""
    return service.approve_knowledge(
        project_id=ctx.project_id,
        knowledge_id=knowledge_id,
        username=ctx.user.username,
    )


@router.patch(
    "/issue-knowledge/{knowledge_id}/reject",
    summary="Reject a knowledge draft",
    operation_id="rejectIssueKnowledge",
    response_model=IssueKnowledgeResponse,
)
def reject_issue_knowledge(
    knowledge_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[IssueKnowledgeService, Depends(get_issue_knowledge_service)],
) -> IssueKnowledgeResponse:
    """Reject a knowledge draft."""
    return service.reject_knowledge(
        project_id=ctx.project_id,
        knowledge_id=knowledge_id,
        username=ctx.user.username,
    )


@router.delete(
    "/issue-knowledge/{knowledge_id}",
    summary="Delete a knowledge case",
    operation_id="deleteIssueKnowledge",
    response_model=SuccessResponse,
)
def delete_issue_knowledge(
    knowledge_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[IssueKnowledgeService, Depends(get_issue_knowledge_service)],
) -> SuccessResponse:
    """Delete a knowledge case."""
    return service.delete_knowledge(
        project_id=ctx.project_id,
        knowledge_id=knowledge_id,
    )
