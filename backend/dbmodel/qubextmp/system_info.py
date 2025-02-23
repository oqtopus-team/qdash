from pydantic import BaseModel


class SystemInfo(BaseModel):
    created_at: str
    updated_at: str

    class Config:
        orm_mode = True
