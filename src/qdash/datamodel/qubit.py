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


class QubitModel(BaseModel):
    """Model for a qubit.

    Attributes
    ----------
        qubit_id (str): The qubit ID. e.g. "0".
        status (str): The status of the qubit.
        data (dict): The data of the qubit.
        node_info (NodeInfo): The node information.

    """

    qid: str = Field(..., description="The qubit ID")
    status: str = Field("pending", description="The status of the qubit")
    chip_id: str | None = Field(None, description="The chip ID")
    data: dict = Field(..., description="The data of the qubit")
    node_info: NodeInfoModel = Field(..., description="The node information")
