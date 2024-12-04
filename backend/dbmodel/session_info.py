from bunnet import Document
from pydantic import ConfigDict
from pymongo import IndexModel


class SessionInfoModel(Document):
    labrad_hostname: str
    labrad_username: str
    labrad_password: str
    cooling_down_id: str
    experiment_username: str
    package_name: str
    active: bool
    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        name = "session_info"
        indexes = [IndexModel([("experiment_username", 1)], unique=True)]

    @classmethod
    def get_active_session_info(cls):
        return cls.find_one(cls.active == True).run()

    @classmethod
    def get_active_session_info_dict(cls):
        return cls.get_active_session_info().dict()
