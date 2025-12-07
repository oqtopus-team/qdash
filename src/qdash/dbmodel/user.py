from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel
from qdash.datamodel.system_info import SystemInfoModel
from qdash.datamodel.user import SystemRole


class UserDocument(Document):
    """Data model for a user.

    Attributes
    ----------
        username (str): The username.
        hashed_password (str): The hashed password.
        access_token (str): The API access token for authentication.
        full_name (Optional[str]): The full name of the user.
        disabled (bool): Whether the user is disabled.
        system_role (SystemRole): The system-level role (admin/user).
        default_project_id (str): The user's default project ID.
        system_info (SystemInfo): The system information.

    """

    username: str = Field(description="The username")
    hashed_password: str = Field(description="The hashed password")
    access_token: str = Field(description="The API access token for authentication")
    full_name: str | None = Field(default=None, description="The full name of the user")
    default_project_id: str | None = Field(
        default=None,
        description="Project ID automatically provisioned for the user",
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
            IndexModel([("username", ASCENDING)], unique=True),
            IndexModel([("access_token", ASCENDING)], unique=True),
        ]
