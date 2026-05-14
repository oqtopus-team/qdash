"""Database model for project-defined flows."""

from datetime import datetime
from typing import Any

from bunnet import Document, SortDirection
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from qdash.common.utils.datetime import now


class FlowDocument(Document):
    """Project-defined Flow metadata.

    Attributes
    ----------
        name (str): Flow name (filename without .py extension).
        username (str): Creator username.
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
    user_id: str | None = Field(default=None, description="Creator user ID")
    username: str = Field(..., description="Creator username snapshot")
    chip_id: str = Field(..., description="Target chip ID")
    description: str = Field(default="", description="Flow description")
    flow_function_name: str = Field(..., description="Entry point function name")
    default_parameters: dict[str, Any] = Field(
        default_factory=dict, description="Default parameters for execution"
    )
    default_run_parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Default run parameters applied to all tasks (e.g., interval, shots)",
    )
    file_path: str = Field(..., description="Relative path to .py file")
    deployment_id: str | None = Field(default=None, description="Prefect deployment ID")
    created_at: datetime = Field(default_factory=now, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=now, description="Last update timestamp")
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
            ],  # Legacy lookup by project+user+name
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("name", ASCENDING),
                ],
                unique=True,
            ),  # Unique project-scoped flow name
            [
                ("project_id", ASCENDING),
                ("username", ASCENDING),
                ("created_at", DESCENDING),
            ],  # List by project+user, sorted by creation date
            [
                ("project_id", ASCENDING),
                ("user_id", ASCENDING),
                ("created_at", DESCENDING),
            ],  # List by project+user_id, sorted by creation date
            [
                ("project_id", ASCENDING),
                ("updated_at", DESCENDING),
            ],  # List by project, sorted by update date
            [("project_id", ASCENDING), ("chip_id", ASCENDING)],  # Lookup by project+chip
        ]

    @classmethod
    def find_by_project_and_name(cls, project_id: str, name: str) -> "FlowDocument | None":
        """Find flow by project and name.

        Args:
        ----
            project_id: Project identifier
            name: Flow name

        Returns:
        -------
            FlowDocument if found, None otherwise

        """
        return cls.find_one({"project_id": project_id, "name": name}).run()

    @classmethod
    def list_by_project(cls, project_id: str) -> list["FlowDocument"]:
        """List all flows for a project, sorted by update time (newest first).

        Args:
        ----
            project_id: Project identifier

        Returns:
        -------
            List of FlowDocument objects

        """
        return list(
            cls.find(
                {"project_id": project_id},
                sort=[("updated_at", SortDirection.DESCENDING)],
            ).run()
        )

    @classmethod
    def delete_by_project_and_name(cls, project_id: str, name: str) -> bool:
        """Delete flow by project and name.

        Args:
        ----
            project_id: Project identifier
            name: Flow name

        Returns:
        -------
            True if deleted, False if not found

        """
        doc = cls.find_one({"project_id": project_id, "name": name}).run()
        if doc:
            doc.delete()
            return True
        return False

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
