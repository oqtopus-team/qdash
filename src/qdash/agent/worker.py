"""Entrypoint placeholder for a hosted QDash agent worker container."""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


def main() -> None:
    """Keep the worker container alive until a queue adapter is added."""
    logging.basicConfig(level=logging.INFO)
    logger.info("QDash agent worker container is ready.")
    logger.info("No job queue adapter is configured yet; API local execution remains active.")
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
