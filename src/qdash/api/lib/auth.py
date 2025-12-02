import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from qdash.api.schemas.auth import User, UserInDB
from qdash.dbmodel.initialize import initialize
from qdash.dbmodel.user import UserDocument

# ロガーの設定
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# モジュールレベルで初期化
initialize()

# bcryptの設定を最適化
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=10,  # 開発環境では少なめに設定
    bcrypt__ident="2b",
    truncate_error=False,  # パスワードの長さチェックを無効化
)

# Bearer Token authentication scheme
bearer_scheme = HTTPBearer(auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password."""
    if not plain_password or not hashed_password:
        return False
    try:
        return bool(pwd_context.verify(plain_password, hashed_password))
    except Exception as e:
        logger.debug(f"Password verification failed: {e}")
        return False


def get_password_hash(password: str) -> str:
    """Generate a hashed password using bcrypt."""
    if not password:
        msg = "Password cannot be empty"
        logger.error(msg)
        raise ValueError(msg)
    return str(pwd_context.hash(password))


def get_user(username: str) -> UserInDB | None:
    """Retrieve a user from the database by username."""
    logger.debug(f"Looking up user in database: {username}")
    query = UserDocument.find_one({"username": username}).run()
    user = query
    logger.debug(f"Database lookup result: {user is not None}")

    if user:
        return UserInDB(
            username=user.username,
            full_name=user.full_name,
            disabled=user.disabled,
            hashed_password=user.hashed_password,
            access_token=user.access_token,
        )
    return None


def get_user_by_token(access_token: str) -> UserInDB | None:
    """Retrieve a user from the database by access token."""
    logger.debug("Looking up user by access token")
    query = UserDocument.find_one({"access_token": access_token}).run()
    user = query
    logger.debug(f"Database lookup result: {user is not None}")

    if user:
        return UserInDB(
            username=user.username,
            full_name=user.full_name,
            disabled=user.disabled,
            hashed_password=user.hashed_password,
            access_token=user.access_token,
        )
    return None


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


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> User:
    """Get user from Bearer token.

    Parameters
    ----------
    credentials : HTTPAuthorizationCredentials
        Bearer token credentials from Authorization header

    Returns
    -------
    User
        User information

    Raises
    ------
    HTTPException
        If token is not provided or invalid

    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    user = get_user_by_token(token)

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

    return User(username=user.username, full_name=user.full_name, disabled=user.disabled)


def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> User:
    """Get user from Bearer token if provided, otherwise return default user.

    Parameters
    ----------
    credentials : HTTPAuthorizationCredentials
        Bearer token credentials from Authorization header (optional)

    Returns
    -------
    User
        User information based on provided token or default user

    """
    if not credentials:
        logger.debug("No token provided, using default user")
        return User(username="default", full_name="Default User", disabled=False)

    token = credentials.credentials
    user = get_user_by_token(token)

    if not user:
        logger.debug("Invalid token, using default user")
        return User(username="default", full_name="Default User", disabled=False)

    logger.debug(f"Using authenticated user: {user.username}")
    return User(username=user.username, full_name=user.full_name, disabled=user.disabled)


def get_current_active_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> User:
    """Get the currently active user from Bearer token.

    Parameters
    ----------
    credentials : HTTPAuthorizationCredentials
        Bearer token credentials from Authorization header

    Returns
    -------
    User
        User information

    Raises
    ------
    HTTPException
        If token is not provided or invalid

    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header with Bearer token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    user = get_user_by_token(token)

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

    return User(username=user.username, full_name=user.full_name, disabled=user.disabled)
