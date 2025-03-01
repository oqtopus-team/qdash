from datetime import timedelta
from typing import Annotated

from datamodel.system_info import SystemInfoModel
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.logger import logger
from fastapi.security import OAuth2PasswordRequestForm
from neodbmodel.initialize import initialize
from neodbmodel.user import UserDocument
from server.lib.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    authenticate_user,
    create_access_token,
    get_current_active_user,
    get_password_hash,
)
from server.schemas.auth import Token, User, UserCreate

initialize()

router = APIRouter(
    prefix="/auth",
    tags=["authentication"],
    responses={404: {"description": "Not found"}},
)


@router.post("/token", response_model=Token)
def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    logger.debug(f"Login attempt for user: {form_data.username}")
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    logger.debug(f"Access token created for user: {user.username}")
    return Token(access_token=access_token, token_type="bearer")


@router.post("/register", response_model=User)
def register_user(user_data: UserCreate) -> User:
    logger.debug(f"Registration attempt for user: {user_data.username}")
    # Check if username already exists
    initialize()
    query = UserDocument.find_one({"username": user_data.username}).run()
    existing_user = query
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    # Create new user
    hashed_password = get_password_hash(user_data.password)
    user = UserDocument(
        username=user_data.username,
        hashed_password=hashed_password,
        full_name=user_data.full_name,
        system_info=SystemInfoModel(),
    )
    user.insert()
    logger.debug(f"New user created: {user_data.username}")

    return User(
        username=user.username,
        full_name=user.full_name,
        disabled=user.disabled,
    )


@router.get("/me", response_model=User)
def read_users_me(current_user: Annotated[User, Depends(get_current_active_user)]) -> User:
    logger.debug(f"Reading user info for: {current_user.username}")
    return current_user


@router.post("/logout")
def logout():
    """Logout endpoint.

    This endpoint doesn't need to do anything on the backend since the token is managed client-side.
    The client will remove the token from cookies.
    """
    return {"message": "Successfully logged out"}
