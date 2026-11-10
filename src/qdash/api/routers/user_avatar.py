"""Generated user avatar routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Response, status

from qdash.api.dependencies import get_user_avatar_service
from qdash.api.lib.auth import get_current_active_user
from qdash.api.schemas.auth import User
from qdash.api.schemas.error import Detail
from qdash.api.schemas.user_avatar import UserAvatarResponse, UserAvatarUpdate
from qdash.api.services.user_avatar_service import (
    AvatarGenerationError,
    InvalidAvatarSpecError,
    UserAvatarService,
    UserNotFoundError,
)
from qdash.datamodel.user import USERNAME_PATTERN
from qdash.datamodel.user_avatar import UserAvatarModel

router = APIRouter()

# Revalidate on every use: a 304 is cheap, and an avatar its owner changes shows up at once.
AVATAR_CACHE_CONTROL = "private, no-cache"
# The SVG is served as an image; even opened directly, it cannot run script or load resources.
AVATAR_CONTENT_SECURITY_POLICY = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
GENERATOR_UNAVAILABLE = "Avatar generator is unavailable"


def _etag_matches(if_none_match: str | None, etag: str) -> bool:
    if not if_none_match:
        return False
    candidates = {value.strip().removeprefix("W/") for value in if_none_match.split(",")}
    return "*" in candidates or f'"{etag}"' in candidates


def _avatar_response(avatar: UserAvatarModel) -> UserAvatarResponse:
    return UserAvatarResponse(
        source=avatar.source,
        spec=avatar.spec,
        generator=avatar.generator,
        generator_version=avatar.generator_version,
        etag=avatar.etag,
    )


@router.get(
    "/auth/me/avatar",
    response_model=UserAvatarResponse,
    responses={503: {"model": Detail}},
    summary="Get the current user's avatar settings",
    operation_id="getCurrentUserAvatar",
)
def get_current_user_avatar(
    current_user: Annotated[User, Depends(get_current_active_user)],
    avatar_service: Annotated[UserAvatarService, Depends(get_user_avatar_service)],
) -> UserAvatarResponse:
    """Return the current user's saved avatar spec, generating the automatic one on first use."""
    try:
        avatar = avatar_service.get_or_create(current_user.username)
    except AvatarGenerationError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, GENERATOR_UNAVAILABLE) from None
    if avatar is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return _avatar_response(avatar)


@router.put(
    "/auth/me/avatar",
    response_model=UserAvatarResponse,
    responses={422: {"model": Detail}, 503: {"model": Detail}},
    summary="Set or reset the current user's avatar",
    operation_id="updateCurrentUserAvatar",
)
def update_current_user_avatar(
    update: UserAvatarUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    avatar_service: Annotated[UserAvatarService, Depends(get_user_avatar_service)],
) -> UserAvatarResponse:
    """Render and save a picker spec, or reset to the automatic avatar when ``spec`` is null.

    The API renders the SVG itself from the spec; avatar markup is never accepted from the
    client. If rendering fails, the saved avatar is unchanged.
    """
    try:
        avatar = avatar_service.set_avatar(current_user.username, update.spec)
    except InvalidAvatarSpecError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    except UserNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found") from None
    except AvatarGenerationError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, GENERATOR_UNAVAILABLE) from None
    return _avatar_response(avatar)


@router.get(
    "/users/{username}/avatar",
    response_class=Response,
    responses={
        200: {"content": {"image/svg+xml": {"schema": {"type": "string"}}}},
        304: {"description": "The cached avatar is current"},
        404: {"model": Detail},
        503: {"model": Detail},
    },
    summary="Get a user's avatar image",
    operation_id="getUserAvatar",
)
def get_user_avatar(
    username: Annotated[str, Path(pattern=USERNAME_PATTERN)],
    avatar_service: Annotated[UserAvatarService, Depends(get_user_avatar_service)],
    if_none_match: Annotated[str | None, Header()] = None,
) -> Response:
    """Return a user's saved avatar SVG, generating the automatic avatar on first request.

    The response carries a strong ETag; a matching ``If-None-Match`` returns 304.
    """
    try:
        avatar = avatar_service.get_or_create(username)
    except AvatarGenerationError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, GENERATOR_UNAVAILABLE) from None
    if avatar is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    headers = {
        "ETag": f'"{avatar.etag}"',
        "Cache-Control": AVATAR_CACHE_CONTROL,
        "Content-Security-Policy": AVATAR_CONTENT_SECURITY_POLICY,
        "X-Content-Type-Options": "nosniff",
    }
    if _etag_matches(if_none_match, avatar.etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(content=avatar.svg, media_type="image/svg+xml", headers=headers)
