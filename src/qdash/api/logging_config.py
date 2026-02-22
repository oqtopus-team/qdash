"""Centralized logging configuration for the QDash API."""

import logging
import logging.config
import os


def setup_logging() -> None:
    """Configure application-wide logging with console and file handlers.

    - Console handler: JSON format for docker compose logs / jq filtering
    - File handler: JSON structured format with rotation (RotatingFileHandler)
    - Log level is controlled by LOG_LEVEL environment variable (default: INFO)
    """
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_dir = "/app/logs"
    log_file = os.path.join(log_dir, "api.log")

    # Ensure log directory exists
    os.makedirs(log_dir, exist_ok=True)

    json_format = "%(asctime)s %(name)s %(levelname)s %(message)s %(request_id)s"

    config: dict[str, object] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": "pythonjsonlogger.json.JsonFormatter",
                "fmt": json_format,
                "rename_fields": {
                    "asctime": "timestamp",
                    "levelname": "level",
                },
                "defaults": {
                    "request_id": "",
                },
            },
        },
        "filters": {
            "request_id": {
                "()": "qdash.api.middleware.request_id.RequestIdFilter",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "json",
                "filters": ["request_id"],
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": log_file,
                "maxBytes": 10 * 1024 * 1024,  # 10 MB
                "backupCount": 5,
                "formatter": "json",
                "filters": ["request_id"],
            },
        },
        "root": {
            "level": log_level,
            "handlers": ["console", "file"],
        },
        "loggers": {
            # Suppress noisy third-party loggers
            "uvicorn": {"level": "WARNING"},
            "uvicorn.access": {"level": "WARNING"},
            "uvicorn.error": {"level": "WARNING"},
            "gunicorn": {"level": "WARNING"},
            "gunicorn.access": {"level": "WARNING"},
            "gunicorn.error": {"level": "WARNING"},
            "pymongo": {"level": "WARNING"},
            "pymongo.command": {"level": "WARNING"},
            "pymongo.topology": {"level": "WARNING"},
            "pymongo.connection": {"level": "WARNING"},
        },
    }

    logging.config.dictConfig(config)

    logger = logging.getLogger(__name__)
    logger.info("Logging configured", extra={"log_level": log_level, "log_file": log_file})
