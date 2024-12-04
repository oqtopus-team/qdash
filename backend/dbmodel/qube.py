from bunnet import Document
from pydantic import ConfigDict


class QubeModel(Document):
    label: str
    name: str
    type: str
    status: str
    address: str
    adapter: str

    class Settings:
        name = "quel"

    model_config = ConfigDict(
        from_attributes=True,
    )
