"""Shared file path validation utilities for QDash API."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException

if TYPE_CHECKING:
    from pathlib import Path


def validate_relative_path(relative_path: str, base_path: Path) -> Path:
    """Validate relative path to prevent path traversal attacks.

    Args:
    ----
        relative_path: Relative path from base_path
        base_path: The base directory that the path must stay within

    Returns:
    -------
        Resolved absolute path

    Raises:
    ------
        HTTPException: If validation fails (path traversal or outside base)

    """
    if ".." in relative_path:
        raise HTTPException(status_code=400, detail="Path traversal detected")

    target_path = base_path / relative_path
    resolved_path = target_path.resolve()

    if not str(resolved_path).startswith(str(base_path.resolve())):
        raise HTTPException(status_code=400, detail="Path outside allowed directory")

    return resolved_path
