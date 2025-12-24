import math
from typing import Any

from pydantic import BaseModel, Field, field_validator


class QubitModel(BaseModel):
    """Model for a qubit.

    Attributes
    ----------
        qubit_id (str): The qubit ID. e.g. "0".
        status (str): The status of the qubit.
        data (dict): The data of the qubit.

    """

    project_id: str | None = Field(None, description="Owning project identifier")
    username: None | str = Field(None, description="The username of the user who created the qubit")
    qid: str = Field(..., description="The qubit ID")
    status: str = Field(default="pending", description="The status of the qubit")
    chip_id: str | None = Field(None, description="The chip ID")
    data: dict[str, Any] = Field(..., description="The data of the qubit")

    @field_validator("data", mode="before")
    @classmethod
    def sanitize_data(cls, v: object) -> dict[str, Any]:
        def replace_nan(obj: object) -> object:
            if isinstance(obj, float) and math.isnan(obj):
                return 0
            if isinstance(obj, dict):
                return {k: replace_nan(val) for k, val in obj.items()}
            if isinstance(obj, list):
                return [replace_nan(val) for val in obj]
            return obj

        cleaned = replace_nan(v)
        if not isinstance(cleaned, dict):
            msg = "data must be a dictionary"
            raise TypeError(msg)
        return cleaned

    def get_qubit_frequency(self) -> float | None:
        """Get the bare frequency of the qubit."""
        v = self.data.get("qubit_frequency")
        if v is None:
            return None
        return float(v.get("value", 0.0))
