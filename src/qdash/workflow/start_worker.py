"""Startup script for the Prefect worker with file logging configured."""

import os
import subprocess
import sys
from pathlib import Path

from qdash.workflow.logging_config import setup_logging

if __name__ == "__main__":
    setup_logging(service_name="worker")

    # Point Prefect to the custom logging config so that flow/task run logs
    # are also written to /app/logs/prefect.log via RotatingFileHandler.
    prefect_logging_yaml = Path("/app/config/logging/prefect.yaml")
    os.environ.setdefault("PREFECT_LOGGING_SETTINGS_PATH", str(prefect_logging_yaml))

    # Ensure the log directory exists for Prefect's file handler
    os.makedirs("/app/logs", exist_ok=True)

    # Run setup scripts then start the worker (all arguments are hardcoded)
    subprocess.run([sys.executable, "setup_work_pool.py"], check=True)  # noqa: S603
    subprocess.run([sys.executable, "register_system_flows.py"], check=True)  # noqa: S603
    subprocess.run(  # noqa: S603
        ["prefect", "worker", "start", "--pool", "user-flows-pool"],  # noqa: S607
        check=True,
    )
