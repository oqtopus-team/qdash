from typing import Any

from pydantic import BaseModel, Field


class CouplingModel(BaseModel):
    """Data model for a coupling.

    Attributes
    ----------
        qid (str): The coupling ID. e.g. "0-1".
        chip_id (str): The chip ID. e.g. "chip1".
        data (dict): The data of the coupling. e.g. {"coupling_strength": 0.1}.

    """

    project_id: str | None = Field(None, description="Owning project identifier")
    username: str | None = Field(
        None, description="The username of the user who created the coupling"
    )
    qid: str = Field(..., description="The coupling ID")
    status: str = Field(default="pending", description="The status of the coupling")
    chip_id: str | None = Field(None, description="The chip ID")
    data: dict[str, Any] = Field(..., description="The data of the coupling")
