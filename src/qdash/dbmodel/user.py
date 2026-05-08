from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel
from qdash.datamodel.system_info import SystemInfoModel
from qdash.datamodel.user import SystemRole, generate_user_id


class UserDocument(Document):
    """Data model for a user.

    Attributes
    ----------
        user_id (str): The immutable internal user identifier.
        username (str): The login username.
        hashed_password (str): The hashed password.
        access_token (str): The API access token for authentication.
        full_name (Optional[str]): The full name of the user.
        disabled (bool): Whether the user is disabled.
        system_role (SystemRole): The system-level role (admin/user).
        default_project_id (str): The user's default project ID.
        system_info (SystemInfo): The system information.

    """

    user_id: str = Field(default_factory=generate_user_id, description="Internal user ID")
    username: str = Field(description="The login username")
    hashed_password: str = Field(description="The hashed password")
    access_token: str = Field(description="The API access token for authentication")
    full_name: str | None = Field(default=None, description="The full name of the user")
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
