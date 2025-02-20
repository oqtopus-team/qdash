from pydantic import BaseModel, Field


class ParameterModel(BaseModel):
    """Data model for a parameter.

    Attributes
    ----------
        parameter_name (str): The name of the parameter.
        description (str): Detailed description of the parameter.

    """

    parameter_name: str = Field(..., description="The name of the parameter")
    description: str = Field("", description="Detailed description of the parameter")
