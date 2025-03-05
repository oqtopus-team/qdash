from pydantic import BaseModel, Field


class ParameterModel(BaseModel):
    """Data model for a parameter.

    Attributes
    ----------
        name (str): The name of the parameter.
        unit (str): The unit of the parameter.
        description (str): Detailed description of the parameter.

    """

    username: str = Field(..., description="The username of the user who created the parameter")
    name: str = Field(..., description="The name of the parameter")
    unit: str = Field("", description="The unit of the parameter")
    description: str = Field("", description="Detailed description of the parameter")
