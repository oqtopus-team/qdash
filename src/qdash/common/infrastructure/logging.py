"""Shared logging setup that loads configuration from a YAML file."""

import atexit
import logging
import logging.config
import os
import re
import shutil
import tempfile
from pathlib import Path

import yaml

_CONFIG_DIR = Path("/app/config/app/logging")
_REPO_ROOT = Path(__file__).resolve().parents[4]
_LOCAL_CONFIG_DIR = _REPO_ROOT / "config" / "app" / "logging"


def _resolve_config_dir(config_dir: Path) -> Path:
    if config_dir.exists():
        return config_dir
    if config_dir == _CONFIG_DIR and _LOCAL_CONFIG_DIR.exists():
        return _LOCAL_CONFIG_DIR
    return config_dir


def _resolve_log_file(log_file: str) -> str:
    path = Path(log_file)

    def prepare(candidate: Path) -> str:
        candidate.parent.mkdir(parents=True, exist_ok=True)
        with candidate.open("a"):
            pass
        return str(candidate)

    try:
        return prepare(path)
    except OSError:
        if not path.is_relative_to("/app/logs"):
            raise

    state_dir = Path(os.getenv("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    try:
        return prepare(state_dir / "qdash" / "logs" / path.name)
    except OSError:
        pass

    fallback_dir = Path(tempfile.mkdtemp(prefix="qdash-logs-"))
    atexit.register(shutil.rmtree, fallback_dir, ignore_errors=True)
    return prepare(fallback_dir / path.name)


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
    log_file = _resolve_log_file(log_file or f"/app/logs/{config_name}.log")

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
