"""Public settings schemas for the API."""

from pydantic import BaseModel


# Response model for GET /settings. Named ``Settings`` so the OpenAPI schema keeps
# the name generated clients depend on; unlike ``qdash.config.Settings`` it must
# never contain secrets such as tokens or webhook URLs.
class Settings(BaseModel):
    """Settings for the QDash application."""

    env: str
    client_url: str = ""
    api_cors_origins: tuple[str, ...] = ()
    prefect_api_url: str
    slack_channel_id: str = ""
    postgres_data_path: str
    mongo_data_path: str
    calib_data_path: str
    mongo_db_name: str = "qdash"
    mongo_port: int = 27017
    mongo_express_port: int = 8081
    postgres_port: int = 5432
    prefect_port: int = 4200
    api_port: int = 5715
    ui_port: int = 5714
    log_level: str = "INFO"
    timezone: str = "Asia/Tokyo"
    enable_local_codex_agent: bool = False
