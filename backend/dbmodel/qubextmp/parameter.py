from bunnet import Document
from pydantic import BaseModel, ConfigDict, Field


class ParameterSchema(BaseModel):
    """Schema for a parameter.

    Attributes:
        parameter_name (str): The name of the parameter.
        description (str): Detailed description of the parameter.
    """

    parameter_name: str = Field(..., description="The name of the parameter")
    description: str = Field("", description="Detailed description of the parameter")

    class Config:
        orm_mode = True


class ParameterDocument(Document):
    """Document model for a parameter in the database.

    Attributes:
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
        cls, domain: ParameterSchema, existing_doc: "ParameterDocument"
    ) -> "ParameterDocument":
        """Creates or updates a ParameterDocument from a domain model.

        If an existing document is provided, its data is merged with the domain data.

        Args:
            domain (Parameter): The domain model instance.
            existing_doc (ParameterDocument): An existing document instance, if available.

        Returns:
            ParameterDocument: The created or updated document.
        """
        if existing_doc:
            existing_data = existing_doc.model_dump()
            domain_data = domain.model_dump()
            merged_data = {**existing_data, **domain_data}
            return cls(**merged_data)
        else:
            return cls(**domain.model_dump())

    def to_domain(self) -> ParameterSchema:
        """Converts this document instance back to the domain model.

        Returns:
            Parameter: The domain model instance.
        """
        return ParameterSchema(**self.model_dump())
