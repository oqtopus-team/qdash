from __future__ import annotations

import configparser
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from qdash.client.services.errors import QDashConfigError

_DEFAULT_CONFIG_PATH = object()
DEFAULT_SECTION = "default"
DEFAULT_BASE_URL_ENV = "QDASH_BASE_URL"
DEFAULT_API_TOKEN_ENV = "QDASH_API_TOKEN"  # noqa: S105
DEFAULT_PROJECT_ID_ENV = "QDASH_PROJECT_ID"
DEFAULT_CF_ACCESS_CLIENT_ID_ENV = "QDASH_CF_ACCESS_CLIENT_ID"
DEFAULT_CF_ACCESS_CLIENT_SECRET_ENV = "QDASH_CF_ACCESS_CLIENT_SECRET"  # noqa: S105
DEFAULT_TIMEOUT_ENV = "QDASH_TIMEOUT_SECONDS"
DEFAULT_RETRY_MAX_ATTEMPTS_ENV = "QDASH_RETRY_MAX_ATTEMPTS"
DEFAULT_RETRY_BACKOFF_SECONDS_ENV = "QDASH_RETRY_BACKOFF_SECONDS"
DEFAULT_RETRY_MAX_BACKOFF_SECONDS_ENV = "QDASH_RETRY_MAX_BACKOFF_SECONDS"
DEFAULT_VERIFY_TLS_ENV = "QDASH_VERIFY_TLS"
DEFAULT_PROXY_ENV = "QDASH_PROXY"
DEFAULT_USER_AGENT_ENV = "QDASH_USER_AGENT"


def _resolve_config_path(path: str | Path | object = _DEFAULT_CONFIG_PATH) -> Path:
    if path is _DEFAULT_CONFIG_PATH:
        xdg_config_home = os.getenv("XDG_CONFIG_HOME")
        return (
            Path(xdg_config_home, "qdash", "config.ini")
            if xdg_config_home
            else Path("~/.config/qdash/config.ini").expanduser()
        )
    return Path(str(path)).expanduser()


class QDashRetryConfig(BaseModel):
    """Retry tuning parameters for idempotent GET requests."""

    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(default=3, ge=1)
    base_delay_sec: float = Field(default=0.2, ge=0.0)
    max_delay_sec: float = Field(default=5.0, ge=0.0)


class QDashConfig(BaseModel):
    """Configuration for qdash-client."""

    model_config = ConfigDict(extra="forbid")

    base_url: str

    # Login-mode credentials (legacy compatibility)
    username: str | None = None
    password_env: str | None = None

    # Token-mode credentials (recommended)
    api_token: str | None = None

    # Optional per-project headers
    project_id: str | None = None
    cf_access_client_id: str | None = None
    cf_access_client_secret: str | None = None

    timeout_sec: float = Field(default=30.0, gt=0.0)
    max_workers: int = Field(default=4, ge=1)
    verify_tls: bool = True
    proxy: str | None = None
    user_agent: str = "qdash-client/dev"
    retry: QDashRetryConfig = Field(default_factory=QDashRetryConfig)

    @field_validator("base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @classmethod
    def from_file(
        cls,
        section: str = DEFAULT_SECTION,
        path: str | Path | object = _DEFAULT_CONFIG_PATH,
    ) -> QDashConfig:
        if section is None:
            raise QDashConfigError("section should not be None.")
        if path is None:
            raise QDashConfigError("path should not be None.")

        config_path = _resolve_config_path(path)
        parser = configparser.ConfigParser()
        if not parser.read(config_path):
            raise QDashConfigError(f"Config file not found: {config_path}")
        if section not in parser:
            raise QDashConfigError(f"Config section not found: {section}")

        sec = parser[section]
        raw: dict[str, Any] = {
            "base_url": sec.get("base_url"),
            "username": sec.get("username"),
            "password_env": sec.get("password_env"),
            "api_token": sec.get("api_token"),
            "project_id": sec.get("project_id"),
            "cf_access_client_id": sec.get("cf_access_client_id"),
            "cf_access_client_secret": sec.get("cf_access_client_secret"),
            "timeout_sec": sec.get("timeout_sec", sec.get("timeout_seconds", fallback="30")),
            "max_workers": sec.get("max_workers", fallback="4"),
            "verify_tls": sec.get("verify_tls", fallback="true"),
            "proxy": sec.get("proxy"),
            "user_agent": sec.get("user_agent", fallback="qdash-client/dev"),
            "retry": {
                "max_attempts": sec.get("retry_max_attempts", fallback="3"),
                "base_delay_sec": sec.get(
                    "retry_backoff_seconds", sec.get("retry_base_delay_sec", fallback="0.2")
                ),
                "max_delay_sec": sec.get(
                    "retry_max_backoff_seconds", sec.get("retry_max_delay_sec", fallback="5.0")
                ),
            },
        }
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            raise QDashConfigError(f"Invalid config values in section '{section}'.") from exc

    @classmethod
    def from_env(cls) -> QDashConfig:
        raw: dict[str, Any] = {
            "base_url": os.getenv(DEFAULT_BASE_URL_ENV),
            "username": os.getenv("QDASH_USERNAME"),
            "password_env": os.getenv("QDASH_PASSWORD_ENV", "QDASH_PASSWORD"),
            "api_token": os.getenv(DEFAULT_API_TOKEN_ENV),
            "project_id": os.getenv(DEFAULT_PROJECT_ID_ENV),
            "cf_access_client_id": os.getenv(DEFAULT_CF_ACCESS_CLIENT_ID_ENV),
            "cf_access_client_secret": os.getenv(DEFAULT_CF_ACCESS_CLIENT_SECRET_ENV),
            "timeout_sec": os.getenv(DEFAULT_TIMEOUT_ENV, "30"),
            "max_workers": os.getenv("QDASH_MAX_WORKERS", "4"),
            "verify_tls": os.getenv(DEFAULT_VERIFY_TLS_ENV, "true"),
            "proxy": os.getenv(DEFAULT_PROXY_ENV),
            "user_agent": os.getenv(DEFAULT_USER_AGENT_ENV, "qdash-client/dev"),
            "retry": {
                "max_attempts": os.getenv(DEFAULT_RETRY_MAX_ATTEMPTS_ENV, "3"),
                "base_delay_sec": os.getenv(DEFAULT_RETRY_BACKOFF_SECONDS_ENV, "0.2"),
                "max_delay_sec": os.getenv(DEFAULT_RETRY_MAX_BACKOFF_SECONDS_ENV, "5.0"),
            },
        }

        if not raw["base_url"]:
            raise QDashConfigError(f"Environment variable {DEFAULT_BASE_URL_ENV} is required.")

        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            raise QDashConfigError("Invalid config values loaded from environment.") from exc

    def save(
        self,
        section: str = DEFAULT_SECTION,
        path: str | Path | object = _DEFAULT_CONFIG_PATH,
    ) -> Path:
        if section is None:
            raise QDashConfigError("section should not be None.")
        if path is None:
            raise QDashConfigError("path should not be None.")

        config_path = _resolve_config_path(path)
        parser = configparser.ConfigParser()
        if config_path.exists():
            parser.read(config_path)

        parser[section] = self._to_file_section()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("w") as file:
            parser.write(file)
        config_path.chmod(0o600)
        return config_path

    def _to_file_section(self) -> dict[str, str]:
        values: dict[str, str] = {
            "base_url": self.base_url,
            "timeout_seconds": str(self.timeout_sec),
            "max_workers": str(self.max_workers),
            "verify_tls": str(self.verify_tls).lower(),
            "retry_max_attempts": str(self.retry.max_attempts),
            "retry_backoff_seconds": str(self.retry.base_delay_sec),
            "retry_max_backoff_seconds": str(self.retry.max_delay_sec),
        }

        optional_values = {
            "username": self.username,
            "password_env": self.password_env,
            "api_token": self.api_token,
            "project_id": self.project_id,
            "cf_access_client_id": self.cf_access_client_id,
            "cf_access_client_secret": self.cf_access_client_secret,
            "proxy": self.proxy,
            "user_agent": self.user_agent,
        }
        values.update({key: value for key, value in optional_values.items() if value})
        return values
