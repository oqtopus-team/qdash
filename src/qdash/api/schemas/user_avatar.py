"""Schemas for glyph avatar settings."""

from typing import Literal

from pydantic import BaseModel, Field


class UserAvatarResponse(BaseModel):
    """The avatar the current user shows."""

    source: Literal["automatic", "custom"] = Field(
        description="automatic (derived from the username) or custom (chosen in the picker)"
    )
    spec: str = Field(description="Canonical glyph-avatar spec string the UI renders")
    generator: str = Field(description="Generator package the spec is for")
    generator_version: str = Field(description="Generator package version")


class UserAvatarUpdate(BaseModel):
    """Avatar selection for the current user."""

    spec: str | None = Field(
        default=None,
        max_length=160,
        description=(
            "Canonical glyph-avatar v1 spec string from the avatar picker; "
            "null resets to the automatic avatar derived from the username"
        ),
    )


class UserAvatarSpec(BaseModel):
    """A user's custom avatar spec."""

    username: str = Field(description="Username")
    spec: str = Field(description="Canonical glyph-avatar spec string the UI renders")


class UserAvatarSpecList(BaseModel):
    """Custom avatar specs of the requested users.

    Users that show the automatic avatar are omitted.
    """

    avatars: list[UserAvatarSpec] = Field(description="Custom avatar specs")
