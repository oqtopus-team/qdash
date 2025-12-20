"""Tag router for QDash API."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from qdash.api.lib.project import ProjectContext, get_project_context
from qdash.api.schemas.tag import ListTagResponse, Tag
from qdash.repository.tag import MongoTagRepository

router = APIRouter()

logger = logging.getLogger(__name__)


def get_tag_repository() -> MongoTagRepository:
    """Get tag repository instance."""
    return MongoTagRepository()


@router.get(
    "/tags",
    response_model=ListTagResponse,
    summary="List all tags",
    operation_id="listTags",
)
def list_tags(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    tag_repo: Annotated[MongoTagRepository, Depends(get_tag_repository)],
) -> ListTagResponse:
    """List all tags for the current project.

    Retrieves all tags associated with the current project's calibration data.
    Tags are used to categorize and filter task results.

    Parameters
    ----------
    ctx : ProjectContext
        Project context with user and project information
    tag_repo : MongoTagRepository
        Repository for tag operations

    Returns
    -------
    ListTagResponse
        Wrapped list of tag names

    """
    tag_names = tag_repo.list_by_project(ctx.project_id)
    return ListTagResponse(tags=[Tag(name=name) for name in tag_names])
