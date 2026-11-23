"""Glyph avatar settings routes.

The UI renders avatars locally from spec strings; these routes only read and save specs.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from qdash.api.dependencies import get_user_avatar_service
from qdash.api.lib.auth import get_current_active_user
from qdash.api.schemas.auth import User
from qdash.api.schemas.error import Detail
from qdash.api.schemas.user_avatar import (
    UserAvatarResponse,
    UserAvatarSpec,
    UserAvatarSpecList,
    UserAvatarUpdate,
)
from qdash.api.services.user_avatar_service import (
    GLYPH_AVATAR_GENERATOR,
    InvalidAvatarSpecError,
    ResolvedAvatar,
    UserAvatarService,
    UserNotFoundError,
)
from qdash.datamodel.user import is_valid_username

router = APIRouter()

MAX_AVATAR_LOOKUP = 100


def _avatar_response(avatar: ResolvedAvatar) -> UserAvatarResponse:
    return UserAvatarResponse(
        source=avatar.source,
        spec=avatar.spec,
        generator=GLYPH_AVATAR_GENERATOR,
        generator_version=avatar.generator_version,
    )


@router.get(
    "/auth/me/avatar",
    response_model=UserAvatarResponse,
    responses={404: {"model": Detail}},
    summary="Get the current user's avatar settings",
    operation_id="getCurrentUserAvatar",
)
def get_current_user_avatar(
    current_user: Annotated[User, Depends(get_current_active_user)],
    avatar_service: Annotated[UserAvatarService, Depends(get_user_avatar_service)],
) -> UserAvatarResponse:
    """Return the current user's custom avatar spec, or the automatic spec if none is saved."""
    try:
        avatar = avatar_service.get(current_user.username)
    except UserNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found") from None
    return _avatar_response(avatar)


@router.put(
    "/auth/me/avatar",
    response_model=UserAvatarResponse,
    responses={404: {"model": Detail}, 422: {"model": Detail}},
    summary="Set or reset the current user's avatar",
    operation_id="updateCurrentUserAvatar",
)
def update_current_user_avatar(
    update: UserAvatarUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    avatar_service: Annotated[UserAvatarService, Depends(get_user_avatar_service)],
) -> UserAvatarResponse:
    """Save a picker spec, or reset to the automatic avatar when ``spec`` is null.

    Only the validated spec string is stored; avatar markup is never accepted.
    """
    try:
        avatar = avatar_service.set_avatar(current_user.username, update.spec)
    except InvalidAvatarSpecError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    except UserNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found") from None
    return _avatar_response(avatar)


@router.get(
    "/users/avatars",
    response_model=UserAvatarSpecList,
    summary="List custom avatar specs of users",
    operation_id="listUserAvatars",
)
def list_user_avatars(
    _current_user: Annotated[User, Depends(get_current_active_user)],
    avatar_service: Annotated[UserAvatarService, Depends(get_user_avatar_service)],
    username: Annotated[
        list[str],
        Query(min_length=1, max_length=MAX_AVATAR_LOOKUP, description="Usernames to look up"),
    ],
) -> UserAvatarSpecList:
    """Return the custom avatar specs of the listed users in one request.

    Users that show the automatic avatar, and unknown or malformed usernames, are omitted.
    """
    specs = avatar_service.custom_specs([name for name in username if is_valid_username(name)])
    return UserAvatarSpecList(
        avatars=[UserAvatarSpec(username=name, spec=spec) for name, spec in sorted(specs.items())]
    )
