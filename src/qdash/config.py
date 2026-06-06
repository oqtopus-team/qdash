from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Settings for the QDash application."""

    env: str
    client_url: str = ""
    api_cors_origins: tuple[str, ...] = ()
    prefect_api_url: str
    slack_bot_token: str = ""
    slack_channel_id: str = ""
    postgres_data_path: str
    mongo_data_path: str
    calib_data_path: str
    # MongoDB
    mongo_db_name: str = "qdash"  # MongoDB database name
    # Ports
    mongo_port: int = 27017
    mongo_express_port: int = 8081
    postgres_port: int = 5432
    prefect_port: int = 4200
    api_port: int = 5715
    ui_port: int = 5714
    # Logging
    log_level: str = "INFO"
    # Timezone
    timezone: str = "Asia/Tokyo"
    # Local agent integrations
    enable_local_codex_agent: bool = False


def resolve_api_cors_origins(settings: Settings) -> list[str]:
    """Resolve allowed CORS origins from explicit settings or local defaults."""
    if settings.api_cors_origins:
        return list(settings.api_cors_origins)
    if settings.client_url:
        return [settings.client_url]
    if settings.env in {"local", "development", "dev"}:
        return [
            f"http://localhost:{settings.ui_port}",
            f"http://127.0.0.1:{settings.ui_port}",
        ]
    return []


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get the application settings."""
    return Settings()
