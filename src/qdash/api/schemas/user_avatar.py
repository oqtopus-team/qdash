"""Schemas for generated user avatars."""

from typing import Literal

from pydantic import BaseModel, Field


class UserAvatarResponse(BaseModel):
    """The current user's saved avatar description."""

    source: Literal["automatic", "custom"] = Field(
        description="automatic (rendered from the username) or custom (chosen in the picker)"
    )
    spec: str = Field(description="Canonical glyph-avatar spec string of the saved avatar")
    generator: str = Field(description="Generator package that rendered the avatar")
    generator_version: str = Field(description="Generator package version")
    etag: str = Field(description="SHA-256 hex digest of the saved SVG")


class UserAvatarUpdate(BaseModel):
    """Avatar selection for the current user."""

    spec: str | None = Field(
        default=None,
        max_length=160,
        description=(
            "Canonical glyph-avatar v1 spec string from the avatar picker; "
            "null resets to the automatic avatar rendered from the username"
        ),
    )
