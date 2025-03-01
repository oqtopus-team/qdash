import logging
from datetime import datetime, timedelta
from typing import Any, Optional, cast

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from jose import jwt
from jose.constants import ALGORITHMS
from neodbmodel.initialize import initialize
from neodbmodel.user import UserDocument
from passlib.context import CryptContext
from server.schemas.auth import User, UserInDB

# ロガーの設定
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# モジュールレベルで初期化
initialize()

# 認証設定
SECRET_KEY = "your-secret-key"  # 本番環境では環境変数から取得すべき
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# bcryptのバージョン問題を回避するための設定
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,  # デフォルトのラウンド数
    bcrypt__ident="2b",  # bcryptのバージョン識別子
)


def create_access_token(data: dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    # jose.jwt.encode returns str in Python 3 when using HS256
    encoded_jwt: str = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHMS.HS256)
    return encoded_jwt


# Optional authentication scheme
# Simple username header authentication
username_header = APIKeyHeader(name="X-Username", auto_error=False)


def get_optional_current_user(username: str = Depends(username_header)) -> User:
    """Get user from username header if provided, otherwise return default user.
    This allows endpoints to support both authenticated and unauthenticated access.

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
    try:
        return cast(bool, pwd_context.verify(plain_password, hashed_password))
    except Exception as e:
        logger.error(f"Password verification failed: {e}")
        return False


def get_password_hash(password: str) -> str:
    return cast(str, pwd_context.hash(password))


def get_user(username: str) -> Optional[UserInDB]:
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


def authenticate_user(username: str, password: str) -> Optional[UserInDB]:
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

    logger.debug(f"Using provided username: {username}")
    return User(username=username, full_name=f"User {username}", disabled=False)


def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user
