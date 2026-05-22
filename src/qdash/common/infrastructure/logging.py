"""Shared logging setup that loads configuration from a YAML file."""

import logging
import logging.config
import os
import re
from pathlib import Path

import yaml

_CONFIG_DIR = Path("/app/config/app/logging")
_LEGACY_CONFIG_DIR = Path("/app/config/logging")
_REPO_ROOT = Path(__file__).resolve().parents[4]
_LOCAL_CONFIG_DIR = _REPO_ROOT / "config" / "app" / "logging"
_LEGACY_LOCAL_CONFIG_DIR = _REPO_ROOT / "config" / "logging"


def _resolve_config_dir(config_dir: Path) -> Path:
    if config_dir.exists():
        return config_dir
    if config_dir == _CONFIG_DIR and _LEGACY_CONFIG_DIR.exists():
        return _LEGACY_CONFIG_DIR
    if config_dir == _CONFIG_DIR and _LOCAL_CONFIG_DIR.exists():
        return _LOCAL_CONFIG_DIR
    if config_dir == _CONFIG_DIR and _LEGACY_LOCAL_CONFIG_DIR.exists():
        return _LEGACY_LOCAL_CONFIG_DIR
    return config_dir


def setup_logging(
    config_name: str,
    *,
    log_file: str | None = None,
    config_dir: Path | None = None,
) -> None:
    """Load a YAML logging config and apply it via ``logging.config.dictConfig``."""
    config_dir = _resolve_config_dir(config_dir or _CONFIG_DIR)
    yaml_path = config_dir / f"{config_name}.yaml"

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_file = log_file or f"/app/logs/{config_name}.log"

    try:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
    except OSError:
        if not log_file.startswith("/app/logs/"):
            raise
        log_file = str(_REPO_ROOT / "logs" / f"{config_name}.log")
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

    raw = yaml_path.read_text()
    raw = raw.replace("${LOG_LEVEL}", log_level)
    raw = raw.replace("${LOG_FILE}", log_file)

    def _env_sub(match: re.Match[str]) -> str:
        return os.getenv(match.group(1), match.group(0))

    raw = re.sub(r"\$\{(\w+)\}", _env_sub, raw)

    config = yaml.safe_load(raw)
    logging.config.dictConfig(config)

    logger = logging.getLogger(__name__)
    logger.info("Logging configured", extra={"log_level": log_level, "log_file": log_file})
