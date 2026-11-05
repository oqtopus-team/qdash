from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import AnyHttpUrl, TypeAdapter, ValidationError, field_validator
from pydantic_settings import BaseSettings

_HTTP_URL_ADAPTER = TypeAdapter(AnyHttpUrl)


class Settings(BaseSettings):
    """Settings for the QDash application."""

    env: str
    client_url: str = ""
    api_cors_origins: tuple[str, ...] = ()
    prefect_api_url: str
    slack_bot_token: str = ""
    slack_channel_id: str = ""
    slack_forum_notification: bool = False
    slack_forum_channel_id: str = ""
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

    @field_validator("client_url", mode="before")
    @classmethod
    def _normalize_client_url(cls, value: object) -> str:
        """Canonicalize CLIENT_URL as an HTTP(S) origin and trim whitespace/trailing slashes."""
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError("CLIENT_URL must be an HTTP(S) origin")
        origin = value.strip().rstrip("/")
        if not origin:
            return ""
        if any(character.isspace() for character in origin):
            raise ValueError("CLIENT_URL must not contain whitespace")
        try:
            parsed = urlsplit(origin)
            port = parsed.port
        except ValueError as exc:
            raise ValueError("CLIENT_URL must be a valid HTTP(S) origin") from exc
        if (
            parsed.username is not None
            or parsed.password is not None
            or "?" in origin
            or "#" in origin
            or parsed.path
            or parsed.netloc.endswith(":")
            or (port is not None and port < 1)
        ):
            raise ValueError(
                "CLIENT_URL must contain only an HTTP(S) scheme, host, and optional port"
            )
        try:
            normalized_url = _HTTP_URL_ADAPTER.validate_python(origin)
        except ValidationError as exc:
            raise ValueError("CLIENT_URL must be a valid HTTP(S) origin") from exc
        return str(normalized_url).rstrip("/")

    @property
    def public_origin(self) -> str:
        """Return the configured public origin or the local UI origin as a fallback."""
        return self.client_url or f"http://localhost:{self.ui_port}"

    @field_validator("slack_forum_notification", mode="before")
    @classmethod
    def _empty_str_as_false(cls, value: object) -> object:
        """Treat unset env vars (empty strings) as False for boolean fields."""
        if isinstance(value, str) and value.strip() == "":
            return False
        return value


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
