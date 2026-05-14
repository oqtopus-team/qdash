"""Shared logging setup that loads configuration from a YAML file."""

import logging
import logging.config
import os
import re
from pathlib import Path

import yaml

_CONFIG_DIR = Path("/app/config/logging")


def setup_logging(
    config_name: str,
    *,
    log_file: str | None = None,
    config_dir: Path | None = None,
) -> None:
    """Load a YAML logging config and apply it via ``logging.config.dictConfig``."""
    config_dir = config_dir or _CONFIG_DIR
    yaml_path = config_dir / f"{config_name}.yaml"

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_file = log_file or f"/app/logs/{config_name}.log"

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
