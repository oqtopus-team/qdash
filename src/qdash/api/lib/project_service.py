"""Backward-compatible re-export of ProjectService.

The canonical implementation has moved to ``qdash.api.services.project_service``.
This module re-exports the class so that existing imports continue to work.
"""

from qdash.api.services.project_service import ProjectService

__all__ = ["ProjectService"]
