"""Service for application configuration operations."""

from __future__ import annotations

import logging
from typing import Any

from qdash.api.lib.config_loader import ConfigLoader

logger = logging.getLogger(__name__)


class ConfigService:
    """Service for retrieving application configuration.

    Provides methods to load and assemble configuration from YAML files
    with support for local overrides.
    """

    def get_all_config(self) -> dict[str, Any]:
        """Get all application configuration.

        Loads settings, metrics, and copilot configuration from YAML files.

        Returns
        -------
        dict[str, Any]
            Dictionary with ui, metrics, and copilot configuration.

        """
        settings = ConfigLoader.load_settings()
        metrics = ConfigLoader.load_metrics()
        copilot = ConfigLoader.load_copilot()

        ui_config = settings.get("ui", {})
        task_files = ui_config.get("task_files", {})

        return {
            "ui": {
                "task_files": {
                    "default_backend": task_files.get("default_backend"),
                    "default_view_mode": task_files.get("default_view_mode"),
                    "sort_order": task_files.get("sort_order"),
                },
            },
            "metrics": metrics,
            "copilot": copilot,
        }
