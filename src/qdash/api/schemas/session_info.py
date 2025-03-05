from pydantic import BaseModel


class SessionInfo(BaseModel):
    labrad_hostname: str
    labrad_username: str
    labrad_password: str
    cooling_down_id: str
    experiment_username: str
    package_name: str
