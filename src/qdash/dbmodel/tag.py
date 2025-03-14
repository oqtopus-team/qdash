from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel


class TagDocument(Document):
    """Document model for a tag in the database.

    Attributes
    ----------
        name (str): The name of the parameter.

    """

    username: str = Field(..., description="The username of the user who created the tag")
    name: str = Field(..., description="The name of the tag")

    # Configuration to parse attributes automatically.
    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        """Database settings for TagDocument."""

        name = "tag"
        indexes: ClassVar = [IndexModel([("name", ASCENDING), ("username")], unique=True)]

    @classmethod
    def insert_tags(cls, tags: list[str], username: str) -> list["TagDocument"]:
        inserted_documents = []
        for tag in tags:
            doc = cls.find_one({"name": tag, "username": username}).run()
            if doc is None:
                doc = cls(username=username, name=tag)
                doc.save()
                inserted_documents.append(doc)
        return inserted_documents
