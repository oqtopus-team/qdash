"""SDK configuration: the same ``QDASH_*`` variables and profile file as qdash-client."""

from __future__ import annotations

import configparser
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from qdash.sdk.errors import QDashConfigError

DEFAULT_PROFILE = "default"


def default_config_path() -> Path:
    """``$XDG_CONFIG_HOME/qdash/config.ini``, else ``~/.config/qdash/config.ini``."""
    xdg_config_home = os.getenv("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home, "qdash", "config.ini")
    return Path("~/.config/qdash/config.ini").expanduser()


class QDashConfig(BaseModel):
    """Where and how a :class:`~qdash.sdk.QDash` session reaches the API.

    Authenticate with ``api_token``, or with ``username`` and the password in the environment
    variable ``password_env``. ``project_id`` is sent as ``X-Project-Id`` on every request;
    without it the server uses the user's default project. ``cf_access_client_id`` and
    ``cf_access_client_secret`` are sent as Cloudflare Access service-token headers.
    ``read_attempts`` bounds how often the SDK sends a read (GET) again after a transport
    error or a transient status; writes are sent once.
    """

    model_config = ConfigDict(extra="forbid")

    base_url: str
    api_token: str | None = None
    username: str | None = None
    password_env: str | None = None
    project_id: str | None = None
    cf_access_client_id: str | None = None
    cf_access_client_secret: str | None = None
    timeout_sec: float = Field(default=30.0, gt=0.0)
    verify_tls: bool = True
    proxy: str | None = None
    user_agent: str | None = None
    read_attempts: int = Field(default=3, ge=1)

    @field_validator("base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @classmethod
    def from_env(cls) -> QDashConfig:
        """Read ``QDASH_BASE_URL``, ``QDASH_API_TOKEN``, ``QDASH_PROJECT_ID`` and the rest."""
        raw: dict[str, Any] = {
            "base_url": os.getenv("QDASH_BASE_URL"),
            "api_token": os.getenv("QDASH_API_TOKEN"),
            "username": os.getenv("QDASH_USERNAME"),
            "password_env": os.getenv("QDASH_PASSWORD_ENV", "QDASH_PASSWORD"),
            "project_id": os.getenv("QDASH_PROJECT_ID"),
            "cf_access_client_id": os.getenv("QDASH_CF_ACCESS_CLIENT_ID"),
            "cf_access_client_secret": os.getenv("QDASH_CF_ACCESS_CLIENT_SECRET"),
            "timeout_sec": os.getenv("QDASH_TIMEOUT_SECONDS", "30"),
            "verify_tls": os.getenv("QDASH_VERIFY_TLS", "true"),
            "proxy": os.getenv("QDASH_PROXY"),
            "user_agent": os.getenv("QDASH_USER_AGENT"),
            "read_attempts": os.getenv("QDASH_RETRY_MAX_ATTEMPTS", "3"),
        }
        if not raw["base_url"]:
            raise QDashConfigError("Environment variable QDASH_BASE_URL is required.")
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            raise QDashConfigError("Invalid config values loaded from environment.") from exc

    @classmethod
    def from_file(
        cls, profile: str = DEFAULT_PROFILE, path: str | Path | None = None
    ) -> QDashConfig:
        """Read ``profile`` of the config file shared with qdash-client, which writes it."""
        config_path = default_config_path() if path is None else Path(path).expanduser()
        parser = configparser.ConfigParser()
        if not parser.read(config_path):
            raise QDashConfigError(f"Config file not found: {config_path}")
        if profile not in parser:
            raise QDashConfigError(f"Config profile not found: {profile}")
        section = parser[profile]
        keys = (
            "base_url",
            "api_token",
            "username",
            "password_env",
            "project_id",
            "cf_access_client_id",
            "cf_access_client_secret",
            "verify_tls",
            "proxy",
            "user_agent",
        )
        raw: dict[str, Any] = {key: section[key] for key in keys if section.get(key)}
        timeout = section.get("timeout_sec", section.get("timeout_seconds"))
        if timeout:
            raw["timeout_sec"] = timeout
        attempts = section.get("retry_max_attempts")
        if attempts:
            raw["read_attempts"] = attempts
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            raise QDashConfigError(f"Invalid config values in profile '{profile}'.") from exc
