"""Startup script for the Prefect worker with file logging configured."""

import os
import subprocess
import sys
from pathlib import Path

from qdash.workflow.logging_config import setup_logging


def _prefect_logging_yaml_path() -> Path:
    path = Path("/app/config/app/logging/prefect.yaml")
    if path.exists():
        return path
    legacy_path = Path("/app/config/logging/prefect.yaml")
    if legacy_path.exists():
        return legacy_path
    return path


if __name__ == "__main__":
    setup_logging(service_name="worker")

    # Point Prefect to the custom logging config so that flow/task run logs
    # are also written to /app/logs/prefect.log via RotatingFileHandler.
    prefect_logging_yaml = _prefect_logging_yaml_path()
    os.environ.setdefault("PREFECT_LOGGING_SETTINGS_PATH", str(prefect_logging_yaml))

    # Ensure the log directory exists for Prefect's file handler
    os.makedirs("/app/logs", exist_ok=True)

    # Run setup scripts then start the worker (all arguments are hardcoded)
    subprocess.run([sys.executable, "setup_work_pool.py"], check=True)
    subprocess.run([sys.executable, "register_system_flows.py"], check=True)
    subprocess.run(
        ["prefect", "worker", "start", "--pool", "user-flows-pool"],  # noqa: S607
        check=True,
    )
