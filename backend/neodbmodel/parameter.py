from typing import ClassVar

from bunnet import Document
from datamodel.parameter import ParameterModel
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel


class ParameterDocument(Document):
    """Document model for a parameter in the database.

    Attributes
    ----------
        parameter_name (str): The name of the parameter.
        description (str): Detailed description of the parameter.

    """

    username: str = Field(..., description="The username of the user who created the parameter")
    name: str = Field(..., description="The name of the parameter")
    unit: str = Field(..., description="The unit of the parameter")
    description: str = Field(..., description="Detailed description of the parameter")

    # Configuration to parse attributes automatically.
    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        """Database settings for ParameterDocument."""

        name = "parameter"
        indexes: ClassVar = [IndexModel([("name", ASCENDING), ("username")], unique=True)]

    @classmethod
    def from_parameter_model(cls, model: ParameterModel) -> "ParameterDocument":
        """Create a ParameterDocument from a ParameterModel.

        Parameters
        ----------
        model : ParameterModel
            The parameter model to convert.

        Returns
        -------
        ParameterDocument
            The converted parameter document.

        """
        return cls(
            username=model.username,
            name=model.name,
            unit=model.unit,
            description=model.description,
        )

    @classmethod
    def insert_parameters(cls, parameters: list[ParameterModel]) -> list["ParameterDocument"]:
        inserted_documents = []
        for param in parameters:
            doc = cls.find_one(cls.name == param.name).run()
            if doc is None:
                doc = cls.from_parameter_model(param)
                doc.save()
            else:
                doc.username = param.username
                doc.unit = param.unit
                doc.description = param.description
                doc.save()
            inserted_documents.append(doc)
        return inserted_documents
