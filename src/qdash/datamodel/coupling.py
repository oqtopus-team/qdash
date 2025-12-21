from typing import Any

from pydantic import BaseModel, Field


class EdgeInfoModel(BaseModel):
    """Data model for an edge information.

    Attributes
    ----------
        fill (str): The fill color.
        position (PositionModel): The position.

    """

    source: str = Field(..., description="The source node")
    target: str = Field(..., description="The target node")
    size: int = Field(..., description="The size of the edge")
    fill: str = Field(..., description="The fill color")


class CouplingModel(BaseModel):
    """Data model for a coupling.

    Attributes
    ----------
        qid (str): The coupling ID. e.g. "0-1".
        chip_id (str): The chip ID. e.g. "chip1".
        data (dict): The data of the coupling. e.g. {"coupling_strength": 0.1}.
        edge_info (EdgeInfoModel): The edge information. e.g. {"fill": "red", "position": {"x": 0.0, "y": 0.0}}.

    """

    project_id: str | None = Field(None, description="Owning project identifier")
    username: str | None = Field(
        None, description="The username of the user who created the coupling"
    )
    qid: str = Field(..., description="The coupling ID")
    status: str = Field(default="pending", description="The status of the coupling")
    chip_id: str | None = Field(None, description="The chip ID")
    data: dict[str, Any] = Field(..., description="The data of the coupling")
    edge_info: EdgeInfoModel | None = Field(
        default=None, description="The edge information (deprecated)"
    )
