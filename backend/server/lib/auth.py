import logging
from datetime import datetime, timedelta
from typing import Any, Optional, cast

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from neodbmodel.initialize import initialize
from neodbmodel.user import UserDocument
from passlib.context import CryptContext
from server.schemas.auth import TokenData, User, UserInDB

# ロガーの設定
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# モジュールレベルで初期化
initialize()

# JWT設定
SECRET_KEY = "your-secret-key"  # 本番環境では環境変数から取得すべき
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return cast(bool, pwd_context.verify(plain_password, hashed_password))


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
            email=user.email,
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


def create_access_token(data: dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode: dict[str, Any] = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = cast(str, jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM))
    return encoded_jwt


from functools import lru_cache


# ユーザー情報のキャッシュ
@lru_cache(maxsize=1024)
def _get_cached_user(token_str: str) -> User | None:
    try:
        payload = jwt.decode(token_str, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if not username:
            return None
        user = get_user(username)
        if not user:
            return None
        return User(
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            disabled=user.disabled,
        )
    except Exception:
        return None


def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """Get current user from token.

    Parameters
    ----------
    token : str
        JWT token from request header

    Returns
    -------
    User
        Current user information

    Raises
    ------
    HTTPException
        If token is invalid or user not found

    """
    logger.debug("Getting user from cache")
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        user = _get_cached_user(token)
        if user is None:
            logger.error("User not found in cache or invalid token")
            raise credentials_exception
        logger.debug(f"User found in cache: {user.username}")
        return user
    except Exception as e:
        logger.error(f"Error getting user from cache: {e}")
        raise credentials_exception


def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user
