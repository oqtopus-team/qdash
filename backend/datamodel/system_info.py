from pydantic import BaseModel, Field


class SystemInfoModel(BaseModel):
    """Data model for system information.

    Attributes:
        created_at (str): The time when the system information was created. e.g. "2021-01-01T00:00:00Z".
        updated_at (str): The time when the system information was updated. e.g. "2021-01-01T00:00:00Z".
    """

    created_at: str = Field(..., description="The time when the system information was created")
    updated_at: str = Field(..., description="The time when the system information was updated")

    class Config:
        orm_mode = True
