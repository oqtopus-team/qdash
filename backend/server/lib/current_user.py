import logging
from typing import Annotated, cast

from fastapi import Depends, HTTPException, status
from server.lib.auth import get_current_user, oauth2_scheme
from server.schemas.auth import User

# ロガーの設定
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def get_current_user_id(token: str | None = None) -> str:
    """Get the current user ID from the token.

    Parameters
    ----------
    token : str | None
        JWT token from request header (optional)

    Returns
    -------
    str
        Current user ID

    """
    try:
        if token:
            logger.debug("Getting current user ID from token")
            user = get_current_user(token)
            if user and user.username:
                logger.debug(f"Current user ID: {user.username}")
                return cast(str, user.username)
    except Exception as e:
        logger.debug(f"Error getting user from token: {e}")

    # デフォルトユーザーを返す
    default_user = "default_user"
    logger.debug(f"Using default user: {default_user}")
    return default_user
