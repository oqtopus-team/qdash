from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel

from qdash.datamodel.system_info import SystemInfoModel
from qdash.datamodel.user import (
    USERNAME_PATTERN_DESCRIPTION,
    SystemRole,
    Username,
    generate_user_id,
)


class UserDocument(Document):
    """Data model for a user.

    Attributes
    ----------
        user_id (str): The immutable internal user identifier.
        username (str): The login username.
        hashed_password (str): The hashed password.
        access_token (str): The API access token for authentication.
        display_name (Optional[str]): The display name of the user.
        organization (Optional[str]): The user's organization or affiliation.
        avatar_key (Optional[str]): The selected avatar preset key.
        disabled (bool): Whether the user is disabled.
        system_role (SystemRole): The system-level role (admin/user).
        default_project_id (str): The user's default project ID.
        system_info (SystemInfo): The system information.

    """

    user_id: str = Field(default_factory=generate_user_id, description="Internal user ID")
    username: Username = Field(description=USERNAME_PATTERN_DESCRIPTION)
    hashed_password: str = Field(description="The hashed password")
    access_token: str = Field(description="The API access token for authentication")
    display_name: str | None = Field(default=None, description="The display name of the user")
    organization: str | None = Field(
        default=None,
        description="The user's organization or affiliation",
    )
    avatar_key: str | None = Field(default=None, description="The selected avatar preset key")
    default_project_id: str | None = Field(
        default=None,
        description="Project ID automatically provisioned for the user",
    )
    must_change_password: bool = Field(
        default=False,
        description="Whether the user must change password on next login",
    )
    disabled: bool = Field(default=False, description="Whether the user is disabled")
    system_role: SystemRole = Field(
        default=SystemRole.USER,
        description="System-level role (admin/user)",
    )
    system_info: SystemInfoModel = Field(description="The system information")

    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        """Settings for the document."""

        name = "user"
        indexes: ClassVar = [
            IndexModel(
                [("user_id", ASCENDING)],
                unique=True,
                partialFilterExpression={"user_id": {"$type": "string"}},
                name="user_id_unique_idx",
            ),
            IndexModel([("username", ASCENDING)], unique=True),
            IndexModel([("access_token", ASCENDING)], unique=True),
        ]
