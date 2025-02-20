from bunnet import Document
from datamodel.parameter import ParameterModel
from pydantic import ConfigDict, Field


class ParameterDocument(Document):
    """Document model for a parameter in the database.

    Attributes
    ----------
        parameter_name (str): The name of the parameter.
        description (str): Detailed description of the parameter.

    """

    parameter_name: str = Field(..., description="The name of the parameter")
    description: str = Field(..., description="Detailed description of the parameter")

    # Configuration to parse attributes automatically.
    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        """Database settings for ParameterDocument."""

        name = "parameter"
        indexes = [("parameter_name",)]

    @classmethod
    def from_domain(
        cls, domain: ParameterModel, existing_doc: "ParameterDocument"
    ) -> "ParameterDocument":
        """Creates or updates a ParameterDocument from a domain model.

        Parameters
        ----------
            domain : ParameterModel
                The domain model instance.
            existing_doc : ParameterDocument
                The existing document instance.

        """
        if existing_doc:
            existing_data = existing_doc.model_dump()
            domain_data = domain.model_dump()
            merged_data = {**existing_data, **domain_data}
            return cls(**merged_data)
        else:
            return cls(**domain.model_dump())

    def to_domain(self) -> ParameterModel:
        """Converts this document instance back to the domain model.

        Returns
        -------
            Parameter: The domain model instance.

        """
        return ParameterModel(**self.model_dump())
