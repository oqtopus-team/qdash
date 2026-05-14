"""Centralized logging configuration for the QDash Workflow services.

Delegates to the shared YAML-based loader in :mod:`qdash.common.infrastructure.logging`.
"""

from qdash.common.infrastructure.logging import setup_logging as _setup


def setup_logging(service_name: str = "workflow") -> None:
    """Configure application-wide logging from ``config/logging/workflow.yaml``."""
    _setup("workflow", log_file=f"/app/logs/{service_name}.log")
