"""SDK configuration: ``QDASH_*`` variables, or a profile of the TOML config file.

The SDK reads ``config.toml``, where each profile is a top-level table and the optional root
``default_profile`` names the profile used when none is given::

    default_profile = "local"

    [local]
    base_url = "http://localhost:5714/api"
    api_token_env = "QDASH_LOCAL_TOKEN"

``qdash config init`` writes such a file. The ``config.ini`` file of qdash-client is still
read when no ``config.toml`` exists, with a
:class:`~qdash.sdk.errors.QDashConfigDeprecationWarning`.
"""

from __future__ import annotations

import configparser
import os
import warnings
from pathlib import Path
from typing import Any

import tomllib
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from qdash.sdk.errors import QDashConfigDeprecationWarning, QDashConfigError

DEFAULT_PROFILE = "default"

# Profile keys of config.toml: the QDashConfig fields, plus api_token_env.
_TOML_STRING_KEYS = frozenset(
    {
        "base_url",
        "api_token",
        "api_token_env",
        "username",
        "password_env",
        "project_id",
        "cf_access_client_id",
        "cf_access_client_secret",
        "proxy",
        "user_agent",
    }
)
_TOML_PROFILE_KEYS = _TOML_STRING_KEYS | {"timeout_sec", "verify_tls", "read_attempts"}
# Root keys of config.toml that are not profile tables. "profiles" held the profiles of the
# earlier [profiles.<name>] layout; it stays reserved so that layout fails with a migration hint.
DEFAULT_PROFILE_KEY = "default_profile"
LEGACY_PROFILES_KEY = "profiles"
RESERVED_PROFILE_NAMES = frozenset({DEFAULT_PROFILE_KEY, LEGACY_PROFILES_KEY})


def _config_dir() -> Path:
    xdg_config_home = os.getenv("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home, "qdash")
    return Path("~/.config/qdash").expanduser()


def default_config_path() -> Path:
    """``$XDG_CONFIG_HOME/qdash/config.toml``, else ``~/.config/qdash/config.toml``."""
    return _config_dir() / "config.toml"


def legacy_config_path() -> Path:
    """The deprecated ``config.ini`` next to :func:`default_config_path`."""
    return _config_dir() / "config.ini"


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
    def from_file(cls, profile: str | None = None, path: str | Path | None = None) -> QDashConfig:
        """Read ``profile`` of a config file.

        Without ``path``, read :func:`default_config_path` (``config.toml``); only when that
        file does not exist, read the deprecated :func:`legacy_config_path` (``config.ini``).
        An explicit ``path`` is read as TOML (``.toml``) or deprecated INI (``.ini``), with no
        fallback. Without ``profile``, use the TOML ``default_profile``, else ``"default"``.
        Reading an INI file emits :class:`~qdash.sdk.errors.QDashConfigDeprecationWarning`.
        """
        # Level 1 is _load_config, 2 this method, 3 the caller.
        return _load_config(profile, path, stacklevel=3)


def _load_config(profile: str | None, path: str | Path | None, *, stacklevel: int) -> QDashConfig:
    """Resolve and read the config file.

    ``stacklevel`` locates the caller to blame for a deprecation warning, counted from this
    function: 1 is ``_load_config``, 2 the public method calling it, 3 that method's caller.
    """
    config, _ = _load_profile(profile, path, stacklevel=stacklevel + 1)
    return config


def _load_profile(
    profile: str | None, path: str | Path | None, *, stacklevel: int
) -> tuple[QDashConfig, str]:
    """Resolve and read the config file, and return the config with its profile name.

    The name is the profile actually read: ``profile`` when given, else the TOML
    ``default_profile``, else ``"default"``. ``stacklevel`` counts as in :func:`_load_config`,
    from this function.
    """
    if profile is not None and not isinstance(profile, str):
        raise QDashConfigError("Config profile must be a string.")
    if path is None:
        toml_path = default_config_path()
        if toml_path.exists():
            return _from_toml(toml_path, profile)
        ini_path = legacy_config_path()
        if ini_path.exists():
            _warn_ini(ini_path, stacklevel=stacklevel + 1)
            return _from_ini(ini_path, profile)
        raise QDashConfigError(f"Config file not found: {toml_path}")

    config_path = Path(path).expanduser()
    suffix = config_path.suffix.lower()
    if suffix == ".toml":
        return _from_toml(config_path, profile)
    if suffix == ".ini":
        _warn_ini(config_path, stacklevel=stacklevel + 1)
        return _from_ini(config_path, profile)
    raise QDashConfigError(
        f"Unsupported config file extension {suffix or '(none)'!r} for {config_path}: "
        "use a .toml file (.ini is deprecated)."
    )


def _warn_ini(path: Path, *, stacklevel: int) -> None:
    warnings.warn(
        f"qdash-sdk read the INI config file {path}. Reading INI config files is deprecated "
        f"in qdash-sdk; move the profiles to {default_config_path()} as top-level "
        "[<name>] tables (TOML); `qdash config init` creates a starting file. qdash-client keeps using config.ini; this deprecation applies to "
        "qdash-sdk only.",
        QDashConfigDeprecationWarning,
        stacklevel=stacklevel,
    )


def _from_ini(config_path: Path, profile: str | None) -> tuple[QDashConfig, str]:
    """The profile section of a qdash-client ``config.ini``; keys keep their INI meaning."""
    profile = DEFAULT_PROFILE if profile is None else profile
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
        return QDashConfig.model_validate(raw), profile
    except ValidationError as exc:
        raise QDashConfigError(f"Invalid config values in profile '{profile}'.") from exc


def _read_toml(config_path: Path) -> dict[str, Any]:
    try:
        content = config_path.read_bytes()
    except FileNotFoundError:
        raise QDashConfigError(f"Config file not found: {config_path}") from None
    except OSError as exc:
        raise QDashConfigError(
            f"Cannot read config file {config_path}: {exc.strerror or type(exc).__name__}"
        ) from None
    try:
        return tomllib.loads(content.decode("utf-8"))
    except UnicodeDecodeError:
        raise QDashConfigError(f"Config file {config_path} is not valid UTF-8.") from None
    except tomllib.TOMLDecodeError as exc:
        # The decoder message names the position, not the content of the line.
        raise QDashConfigError(f"Invalid TOML in config file {config_path}: {exc}") from None


def _from_toml(config_path: Path, profile: str | None) -> tuple[QDashConfig, str]:
    document = _read_toml(config_path)
    if LEGACY_PROFILES_KEY in document:
        raise QDashConfigError(
            f"Config file {config_path} uses the removed [profiles.<name>] layout: move each "
            "[profiles.<name>] table to a top-level [<name>] table and keep default_profile "
            "at the top."
        )
    default_profile = document.get(DEFAULT_PROFILE_KEY)
    if default_profile is not None and (
        not isinstance(default_profile, str) or not default_profile
    ):
        raise QDashConfigError(
            f"default_profile in config file {config_path} must be a non-empty string."
        )
    # Every other root key is a profile table; a root value holds a misplaced setting.
    unknown = sorted(
        key
        for key, value in document.items()
        if key != DEFAULT_PROFILE_KEY and not isinstance(value, dict)
    )
    if unknown:
        raise QDashConfigError(
            f"Unknown top-level keys in config file {config_path}: {', '.join(unknown)}. "
            "Put profile settings under a [<name>] table."
        )
    if "" in document:
        raise QDashConfigError(f"A profile in config file {config_path} has an empty name.")

    selected = profile if profile is not None else (default_profile or DEFAULT_PROFILE)
    if selected in RESERVED_PROFILE_NAMES:
        raise QDashConfigError(f"Config profile name '{selected}' is reserved.")
    if selected not in document:
        raise QDashConfigError(f"Config profile not found: {selected}")
    return _profile_config(selected, document[selected]), selected


def _profile_config(profile: str, table: dict[str, Any]) -> QDashConfig:
    """Validate one ``[<name>]`` profile table; error messages never carry values."""
    unknown = sorted(set(table) - _TOML_PROFILE_KEYS)
    if unknown:
        raise QDashConfigError(f"Unknown keys in profile '{profile}': {', '.join(unknown)}")
    for key in sorted(_TOML_STRING_KEYS & set(table)):
        if not isinstance(table[key], str):
            raise QDashConfigError(f"'{key}' in profile '{profile}' must be a string.")
    if "verify_tls" in table and not isinstance(table["verify_tls"], bool):
        raise QDashConfigError(f"'verify_tls' in profile '{profile}' must be a boolean.")
    timeout = table.get("timeout_sec")
    if timeout is not None and (isinstance(timeout, bool) or not isinstance(timeout, int | float)):
        raise QDashConfigError(f"'timeout_sec' in profile '{profile}' must be a number.")
    attempts = table.get("read_attempts")
    if attempts is not None and (isinstance(attempts, bool) or not isinstance(attempts, int)):
        raise QDashConfigError(f"'read_attempts' in profile '{profile}' must be an integer.")

    # Empty strings mean unset, as in config.ini.
    raw: dict[str, Any] = {key: value for key, value in table.items() if value != ""}
    if "api_token_env" in table:
        variable = raw.pop("api_token_env", None)
        if not variable:
            raise QDashConfigError(
                f"'api_token_env' in profile '{profile}' must name an environment variable."
            )
        if raw.get("api_token"):
            raise QDashConfigError(
                f"Profile '{profile}' sets both 'api_token' and 'api_token_env'; set one."
            )
        token = os.environ.get(variable)
        if not token:
            raise QDashConfigError(
                f"Environment variable {variable} named by 'api_token_env' in profile "
                f"'{profile}' is not set or empty."
            )
        raw["api_token"] = token
    if "base_url" not in raw:
        raise QDashConfigError(f"'base_url' is required in profile '{profile}'.")
    try:
        return QDashConfig.model_validate(raw)
    except ValidationError as exc:
        fields = sorted({".".join(str(part) for part in error["loc"]) for error in exc.errors()})
        raise QDashConfigError(
            f"Invalid config values in profile '{profile}': {', '.join(fields)}"
        ) from None
