"""Unified configuration loader for QDash.

This module re-exports from qdash.common.config_loader for backward compatibility.
New code should import directly from qdash.common.config_loader.
"""

# Re-export from common for backward compatibility
from qdash.common.config_loader import ConfigLoader

__all__ = ["ConfigLoader"]
