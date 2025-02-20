from pydantic import BaseModel, Field


class PositionModel(BaseModel):
    """Data model for a position.

    Attributes
    ----------
        x (float): The x-coordinate.
        y (float): The y-coordinate.

    """

    x: float = Field(..., description="The x-coordinate")
    y: float = Field(..., description="The y-coordinate")


class NodeInfoModel(BaseModel):
    """Data model for a node information.

    Attributes
    ----------
        fill (str): The fill color.
        position (PositionModel): The position.

    """

    position: PositionModel = Field(..., description="The position")
