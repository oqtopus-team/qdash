"""Database model for user-defined flows."""

from datetime import datetime
from typing import Any

from bunnet import Document
from pydantic import ConfigDict, Field
from bunnet import SortDirection
from pymongo import ASCENDING, DESCENDING


class FlowDocument(Document):
    """User-defined Flow metadata.

    Attributes
    ----------
        name (str): Flow name (filename without .py extension).
        username (str): Owner username.
        chip_id (str): Target chip ID.
        description (str): Flow description.
        flow_function_name (str): Entry point function name in the Python file.
        default_parameters (dict): Default parameters for flow execution.
        file_path (str): Relative path to .py file from project root.
        created_at (datetime): Timestamp when flow was created.
        updated_at (datetime): Timestamp when flow was last updated.
        tags (list[str]): Tags for categorization and search.

    """

    project_id: str = Field(..., description="Owning project identifier")
    name: str = Field(..., description="Flow name (filename without .py)")
    username: str = Field(..., description="Owner username")
    chip_id: str = Field(..., description="Target chip ID")
    description: str = Field(default="", description="Flow description")
    flow_function_name: str = Field(..., description="Entry point function name")
    default_parameters: dict[str, Any] = Field(
        default_factory=dict, description="Default parameters for execution"
    )
    file_path: str = Field(..., description="Relative path to .py file")
    deployment_id: str | None = Field(default=None, description="Prefect deployment ID")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(), description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(), description="Last update timestamp"
    )
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")

    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        """Settings for the document."""

        name = "flows"
        indexes = [
            [
                ("project_id", ASCENDING),
                ("username", ASCENDING),
                ("name", ASCENDING),
            ],  # Unique per project+user
            [
                ("project_id", ASCENDING),
                ("username", ASCENDING),
                ("created_at", DESCENDING),
            ],  # List by project+user, sorted by creation date
            [("project_id", ASCENDING), ("chip_id", ASCENDING)],  # Lookup by project+chip
        ]

    @classmethod
    def find_by_user_and_name(
        cls, username: str, name: str, project_id: str
    ) -> "FlowDocument | None":
        """Find flow by username and name.

        Args:
        ----
            username: Username of the flow owner
            name: Flow name
            project_id: Optional project identifier

        Returns:
        -------
            FlowDocument if found, None otherwise

        """
        return cls.find_one({"project_id": project_id, "username": username, "name": name}).run()

    @classmethod
    def list_by_user(cls, username: str, project_id: str) -> list["FlowDocument"]:
        """List all flows for a user, sorted by update time (newest first).

        Args:
        ----
            username: Username of the flow owner
            project_id: Optional project identifier

        Returns:
        -------
            List of FlowDocument objects

        """
        return list(
            cls.find(
                {"project_id": project_id, "username": username},
                sort=[("updated_at", SortDirection.DESCENDING)],
            ).run()
        )

    @classmethod
    def delete_by_user_and_name(cls, username: str, name: str, project_id: str) -> bool:
        """Delete flow by username and name.

        Args:
        ----
            username: Username of the flow owner
            name: Flow name
            project_id: Optional project identifier

        Returns:
        -------
            True if deleted, False if not found

        """
        doc = cls.find_one({"project_id": project_id, "username": username, "name": name}).run()
        if doc:
            doc.delete()
            return True
        return False
