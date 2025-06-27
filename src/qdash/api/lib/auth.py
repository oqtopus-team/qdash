import logging

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader
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

# Optional authentication scheme
# Simple username header authentication
username_header = APIKeyHeader(name="X-Username", auto_error=False)


def get_optional_current_user(username: str = Depends(username_header)) -> User:
    """Get user from username header if provided, otherwise return default user.

    Parameters
    ----------
    username : str
        Username from request header (optional)

    Returns
    -------
    User
        User information based on provided username or default user

    """
    if not username:
        logger.debug("No username provided, using default user")
        return User(username="default", full_name="Default User", disabled=False)

    logger.debug(f"Using provided username: {username}")
    return User(username=username, full_name=f"User {username}", disabled=False)


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
    # hash関数は既にstrを返すため、キャストは不要
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


def get_current_user(username: str = Depends(username_header)) -> User:
    """Get user from username header.

    Parameters
    ----------
    username : str
        Username from request header

    Returns
    -------
    User
        User information

    Raises
    ------
    HTTPException
        If username is not provided

    """
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username header is required",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # ユーザー情報をキャッシュから取得（実際のユーザー情報は不要なため、シンプルなオブジェクトを返す）
    return User(username=username, full_name=username, disabled=False)


def get_current_active_user(request: Request) -> User:
    """Get the currently active user."""
    username = request.headers.get("X-Username")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username header is required",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    # ユーザー情報を直接生成（get_current_userを呼び出さない）
    return User(username=username, full_name=username, disabled=False)
