"""Centralized logging configuration for the QDash Workflow services.

Delegates to the shared YAML-based loader in :mod:`qdash.common.logging`.
"""

from qdash.common.logging import setup_logging as _setup


def setup_logging(service_name: str = "workflow") -> None:
    """Configure application-wide logging from ``config/logging/workflow.yaml``."""
    _setup("workflow", log_file=f"/app/logs/{service_name}.log")
