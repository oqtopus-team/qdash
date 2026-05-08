from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel
from qdash.dbmodel.user import UserDocument


class TagDocument(Document):
    """Document model for a tag in the database.

    Attributes
    ----------
        project_id (str): The owning project identifier.
        name (str): The name of the parameter.

    """

    project_id: str = Field(..., description="Owning project identifier")
    user_id: str | None = Field(default=None, description="Creator user ID")
    username: str = Field(..., description="Creator username snapshot")
    name: str = Field(..., description="The name of the tag")

    # Configuration to parse attributes automatically.
    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        """Database settings for TagDocument."""

        name = "tag"
        indexes: ClassVar = [
            IndexModel(
                [("project_id", ASCENDING), ("name", ASCENDING), ("username", ASCENDING)],
                unique=True,
            ),
            IndexModel([("project_id", ASCENDING), ("user_id", ASCENDING)]),
            IndexModel([("project_id", ASCENDING), ("username", ASCENDING)]),
        ]

    @staticmethod
    def _user_id_for_username(username: str) -> str | None:
        user = UserDocument.find_one({"username": username}).run()
        return user.user_id if user else None

    @classmethod
    def insert_tags(cls, tags: list[str], username: str, project_id: str) -> list["TagDocument"]:
        inserted_documents = []
        for tag in tags:
            doc = cls.find_one({"project_id": project_id, "name": tag, "username": username}).run()
            if doc is None:
                doc = cls(
                    project_id=project_id,
                    user_id=cls._user_id_for_username(username),
                    username=username,
                    name=tag,
                )
                doc.save()
                inserted_documents.append(doc)
        return inserted_documents
