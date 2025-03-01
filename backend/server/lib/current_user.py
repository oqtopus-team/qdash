import logging
from typing import Annotated, cast

from fastapi import Depends, HTTPException, status
from server.lib.auth import get_current_user, username_header
from server.schemas.auth import User

# ロガーの設定
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def get_current_user_id(username: str | None = Depends(username_header)) -> str:
    """Get the current user ID from the username header.

    Parameters
    ----------
    username : str | None
        Username from request header (optional)

    Returns
    -------
    str
        Current user ID

    """
    try:
        if username:
            logger.debug("Getting current user ID from username")
            user = get_current_user(username)
            if user and user.username:
                logger.debug(f"Current user ID: {user.username}")
                return cast(str, user.username)
    except Exception as e:
        logger.debug(f"Error getting user from username: {e}")

    # デフォルトユーザーを返す
    default_user = "default"
    logger.debug(f"Using default user: {default_user}")
    return default_user
