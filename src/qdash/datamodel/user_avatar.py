"""Domain model for a user's generated avatar."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from qdash.common.utils.datetime import now

UserAvatarSource = Literal["automatic", "custom"]


class UserAvatarModel(BaseModel):
    """Generated avatar SVG saved for a user.

    An automatic avatar is rendered the first time the user's avatar is requested; a custom
    avatar is rendered when the user saves a picker selection. The SVG is kept as rendered, so
    a later generator upgrade never changes an existing avatar.
    """

    user_id: str = Field(description="Internal ID of the user that owns the avatar")
    username: str = Field(description="Username of the user when the avatar was saved")
    source: UserAvatarSource = Field(description="automatic (from the username) or custom")
    spec: str = Field(description="Canonical glyph-avatar spec string rendered into the SVG")
    seed: str = Field(description="Seed part of the spec")
    svg: str = Field(description="Generated SVG markup")
    etag: str = Field(description="SHA-256 hex digest of the SVG bytes")
    generator: str = Field(description="Generator package name")
    generator_version: str = Field(description="Generator package version")
    options: dict[str, str | int] = Field(description="Render options used for the SVG")
    created_at: datetime = Field(default_factory=now, description="First save time")
    updated_at: datetime = Field(default_factory=now, description="Last save time")
