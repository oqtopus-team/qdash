"""Domain model for a user's chosen glyph avatar."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from qdash.common.utils.datetime import now

UserAvatarSource = Literal["automatic", "custom"]


class UserAvatarModel(BaseModel):
    """Avatar settings a user chose in the avatar picker.

    Only the canonical ``glyph-avatar`` spec string and the generator version are stored; the
    browser renders the SVG locally with the bundled package. A user without a custom record
    shows the automatic avatar derived from the username, so no record is needed for it.
    """

    user_id: str = Field(description="Internal ID of the user that owns the avatar")
    username: str = Field(description="Username of the user when the avatar was saved")
    source: UserAvatarSource = Field(
        default="custom",
        description=(
            "custom for a picker choice. Records with automatic were written by an earlier "
            "version and are ignored"
        ),
    )
    spec: str = Field(description="Canonical glyph-avatar spec string")
    seed: str = Field(description="Seed part of the spec")
    generator: str = Field(description="Generator package name")
    generator_version: str = Field(description="Generator package version the spec was chosen with")
    created_at: datetime = Field(default_factory=now, description="First save time")
    updated_at: datetime = Field(default_factory=now, description="Last save time")
