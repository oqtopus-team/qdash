"""Tag router for QDash API."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from qdash.api.lib.auth import get_current_active_user
from qdash.api.schemas.auth import User
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
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> ListTagResponse:
    """List all tags for the current user.

    Retrieves all tags associated with the current user's calibration data.
    Tags are used to categorize and filter task results.

    Parameters
    ----------
    current_user : User
        Current authenticated user

    Returns
    -------
    ListTagResponse
        Wrapped list of tag names

    """
    tags = TagDocument.find({"username": current_user.username}).run()
    tags = [Tag(name=tag.name) for tag in tags]
    return ListTagResponse(tags=tags)
