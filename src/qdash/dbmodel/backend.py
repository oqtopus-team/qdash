import logging
from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel
from qdash.datamodel.backend import BackendModel
from qdash.datamodel.system_info import SystemInfoModel

logger = logging.getLogger(__name__)


class BackendDocument(Document):
    """Document model for a task in the database.

    Attributes
    ----------
        name (str): The name of the task. e.g. "CheckT1" ,"CheckT2Echo" ".
        description (str): Detailed description of the task.

    """

    username: str = Field(..., description="The username of the user who created the task")
    name: str = Field(..., description="The name of backend")
    system_info: SystemInfoModel = Field(
        default_factory=SystemInfoModel, description="The system information"
    )

    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        """Database settings for ParameterDocument."""

        name = "backend"
        indexes: ClassVar = [IndexModel([("name", ASCENDING), ("username")], unique=True)]

    @classmethod
    def from_backend_model(cls, model: BackendModel) -> "BackendDocument":
        """Create a BackendDocument from a BackendModel."""
        return cls(
            username=model.username,
            name=model.name,
        )

    @classmethod
    def insert_backend(cls, backend: BackendModel) -> list["BackendDocument"]:
        """Insert a backend into the database."""
        backend_doc = cls.from_backend_model(backend)
        backend_doc.save()
        return [backend_doc]
