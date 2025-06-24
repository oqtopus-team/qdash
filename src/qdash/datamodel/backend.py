from pydantic import BaseModel, Field


class BackendModel(BaseModel):
    """Data model for a chip.

    Attributes
    ----------
        name (str): The name of the backend. e.g. "backend1".
        username (str): The username of the user who created the backend.
        system_info (SystemInfo): The system information. e.g. {"created_at": "2021-01-01T00:00:00Z", "updated_at": "2021-01-01T00:00:00Z"}.

    """

    name: str = Field(..., description="The name of the backend")
    username: str = Field(..., description="The username of the user who created the chip")
