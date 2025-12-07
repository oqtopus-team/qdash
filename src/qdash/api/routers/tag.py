"""Tag router for QDash API."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from qdash.api.lib.project import ProjectContext, get_project_context
from qdash.api.schemas.tag import ListTagResponse, Tag
from qdash.dbmodel.tag import TagDocument

router = APIRouter()

# ロガーの設定
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@router.get(
    "/tags",
    response_model=ListTagResponse,
    summary="List all tags",
    operation_id="listTags",
)
def list_tags(
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
) -> ListTagResponse:
    """List all tags for the current project.

    Retrieves all tags associated with the current project's calibration data.
    Tags are used to categorize and filter task results.

    Parameters
    ----------
    ctx : ProjectContext
        Project context with user and project information

    Returns
    -------
    ListTagResponse
        Wrapped list of tag names

    """
    tags = TagDocument.find({"project_id": ctx.project_id}).run()
    tags = [Tag(name=tag.name) for tag in tags]
    return ListTagResponse(tags=tags)
