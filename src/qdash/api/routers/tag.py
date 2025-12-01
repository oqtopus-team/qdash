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
    "/tag",
    response_model=ListTagResponse,
    summary="list all tag",
    operation_id="listAllTag",
)
def list_all_tag(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> ListTagResponse:
    """Fetch all tasks.

    Args:
    ----
        current_user (User): The current user.

    Returns:
    -------
        ListTaskResponse: The list of tasks.

    """
    tags = TagDocument.find({"username": current_user.username}).run()
    tags = [Tag(name=tag.name) for tag in tags]
    return ListTagResponse(tags=tags)
