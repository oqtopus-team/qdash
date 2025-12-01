"""Schema definitions for parameter router."""

from pydantic import BaseModel
from qdash.datamodel.parameter import ParameterModel


class ListParameterResponse(BaseModel):
    """Response model for a list of parameters."""

    parameters: list[ParameterModel]
