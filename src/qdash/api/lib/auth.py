import logging
from typing import cast

import bcrypt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from qdash.api.schemas.auth import User, UserInDB
from qdash.datamodel.user import SystemRole
from qdash.dbmodel.initialize import initialize
from qdash.dbmodel.user import UserDocument

logger = logging.getLogger(__name__)

# Initialize at module level
initialize()

BCRYPT_ROUNDS = 10
BCRYPT_MAX_PASSWORD_BYTES = 72

# Bearer Token authentication scheme
bearer_scheme = HTTPBearer(auto_error=False)


def username_header(x_username: str | None = Header(None, alias="X-Username")) -> str | None:
    """Extract username from X-Username header.

    Parameters
    ----------
    x_username : str | None
        Username from X-Username header (optional)

    Returns
    -------
    str | None
        Username or None if not provided

    """
    return x_username


def _password_bytes(password: str) -> bytes:
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > BCRYPT_MAX_PASSWORD_BYTES:
        msg = "Password cannot be longer than 72 bytes"
        logger.error(msg)
        raise ValueError(msg)
    return password_bytes


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password."""
    if not plain_password or not hashed_password:
        return False
    try:
        return bool(
            bcrypt.checkpw(_password_bytes(plain_password), hashed_password.encode("utf-8"))
        )
    except Exception as e:
        logger.debug(f"Password verification failed: {e}")
        return False


def get_password_hash(password: str) -> str:
    """Generate a hashed password using bcrypt."""
    if not password:
        msg = "Password cannot be empty"
        logger.error(msg)
        raise ValueError(msg)
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS, prefix=b"2b")
    return cast("str", bcrypt.hashpw(_password_bytes(password), salt).decode("utf-8"))


def _user_in_db(user: UserDocument | None) -> UserInDB | None:
    logger.debug(f"Database lookup result: {user is not None}")
    return UserInDB.model_validate(user, from_attributes=True) if user else None


def get_user(username: str) -> UserInDB | None:
    """Retrieve a user from the database by username."""
    logger.debug(f"Looking up user in database: {username}")
    return _user_in_db(UserDocument.find_one({"username": username}).run())


def get_user_by_token(access_token: str) -> UserInDB | None:
    """Retrieve a user from the database by access token."""
    logger.debug("Looking up user by access token")
    return _user_in_db(UserDocument.find_one({"access_token": access_token}).run())


def authenticate_user(username: str, password: str) -> UserInDB | None:
    """Authenticate a user by username and password."""
    logger.debug(f"Authenticating user: {username}")
    user = get_user(username)
    if not user:
        logger.error(f"User not found: {username}")
        return None
    if not verify_password(password, user.hashed_password):
        logger.error(f"Invalid password for user: {username}")
        return None
    logger.debug(f"Authentication successful for user: {username}")
    return user


def _authenticated_user(
    credentials: HTTPAuthorizationCredentials | None, *, missing_detail: str
) -> User:
    """Resolve an enabled user from Bearer token credentials, or raise 401/403."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=missing_detail,
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = get_user_by_token(credentials.credentials)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.disabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    return User.model_validate(user.model_dump(include=set(User.model_fields)))


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> User:
    """Get user from Bearer token.

    Raises
    ------
    HTTPException
        If token is not provided or invalid, or the user is disabled

    """
    return _authenticated_user(credentials, missing_detail="Authorization header is required")


def get_current_active_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> User:
    """Get the currently active user from Bearer token.

    Raises
    ------
    HTTPException
        If token is not provided or invalid, or the user is disabled

    """
    return _authenticated_user(
        credentials, missing_detail="Authorization header with Bearer token is required"
    )


def get_admin_user(
    user: User = Depends(get_current_user),
) -> User:
    """Get the current user and verify they have admin privileges.

    Parameters
    ----------
    user : User
        Current authenticated user

    Returns
    -------
    User
        User information (admin only)

    Raises
    ------
    HTTPException
        If user is not an admin

    """
    if user.system_role != SystemRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return user
