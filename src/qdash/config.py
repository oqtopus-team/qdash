from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Settings for the QDash application."""

    env: str
    client_url: str
    prefect_api_url: str
    slack_bot_token: str
    slack_channel_id: str
    postgres_data_path: str
    mongo_data_path: str
    calib_data_path: str
    backend: str = "qubex"  # Default backend is 'qubex'
    # Ports
    mongo_port: int = 27017
    mongo_express_port: int = 8081
    postgres_port: int = 5432
    prefect_port: int = 4200
    api_port: int = 5715
    ui_port: int = 5714
    # Logging
    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get the application settings."""
    return Settings()
