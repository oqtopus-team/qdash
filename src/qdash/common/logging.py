"""Shared logging setup that loads configuration from a YAML file.

Usage::

    from qdash.common.logging import setup_logging

    # API
    setup_logging("api", log_file="/app/logs/api.log")

    # Workflow services
    setup_logging("workflow", log_file="/app/logs/deployment.log")
"""

import logging
import logging.config
import os
import re
from pathlib import Path

import yaml

# Default directory where logging YAML files are stored.
_CONFIG_DIR = Path("/app/config/logging")


def setup_logging(
    config_name: str,
    *,
    log_file: str | None = None,
    config_dir: Path | None = None,
) -> None:
    """Load a YAML logging config and apply it via :func:`logging.config.dictConfig`.

    The YAML file may contain ``${LOG_LEVEL}`` and ``${LOG_FILE}`` placeholders.
    These are resolved from environment variables / function arguments at load time.

    Parameters
    ----------
    config_name:
        Base name of the YAML file (without extension), e.g. ``"api"`` or ``"workflow"``.
    log_file:
        Override for ``${LOG_FILE}``.  Defaults to ``/app/logs/<config_name>.log``.
    config_dir:
        Directory containing YAML files.  Defaults to ``/app/config/logging``.

    """
    config_dir = config_dir or _CONFIG_DIR
    yaml_path = config_dir / f"{config_name}.yaml"

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_file = log_file or f"/app/logs/{config_name}.log"

    # Ensure log directory exists
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    raw = yaml_path.read_text()

    # Substitute ${LOG_LEVEL} and ${LOG_FILE} placeholders
    raw = raw.replace("${LOG_LEVEL}", log_level)
    raw = raw.replace("${LOG_FILE}", log_file)

    # Substitute any remaining ${ENV_VAR} from environment (best-effort)
    def _env_sub(match: re.Match[str]) -> str:
        return os.getenv(match.group(1), match.group(0))

    raw = re.sub(r"\$\{(\w+)\}", _env_sub, raw)

    config = yaml.safe_load(raw)
    logging.config.dictConfig(config)

    logger = logging.getLogger(__name__)
    logger.info("Logging configured", extra={"log_level": log_level, "log_file": log_file})
