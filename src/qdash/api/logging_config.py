"""Centralized logging configuration for the QDash API.

Delegates to the shared YAML-based loader in :mod:`qdash.common.infrastructure.logging`.
"""

from qdash.common.infrastructure.logging import setup_logging as _setup


def setup_logging() -> None:
    """Configure application-wide logging from ``config/app/logging/api.yaml``."""
    _setup("api", log_file="/app/logs/api.log")
