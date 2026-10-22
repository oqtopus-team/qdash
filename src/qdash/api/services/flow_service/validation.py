"""Validation and formatting rules for user flow sources."""

from __future__ import annotations

import ast
import logging
import re
import subprocess
from typing import TYPE_CHECKING

from fastapi import HTTPException

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger("uvicorn.app")

_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")


def validate_flow_name(name: str) -> None:
    """Reject a flow name that is not alphanumeric or underscores."""
    if not _NAME_PATTERN.match(name):
        raise HTTPException(
            status_code=400,
            detail="Flow name must contain only alphanumeric characters and underscores",
        )


def normalize_folder(folder: str) -> str:
    """Return the folder path in canonical form, or raise 400.

    A folder is zero or more segments joined by "/"; each segment uses the
    same characters as a flow name. Surrounding slashes and whitespace are
    dropped so "/daily/t1/" and "daily/t1" name the same folder.
    """
    normalized = folder.strip().strip("/")
    if normalized == "":
        return ""
    if not all(_NAME_PATTERN.match(part) for part in normalized.split("/")):
        raise HTTPException(
            status_code=400,
            detail=(
                "Folder must be segments of alphanumeric characters and underscores"
                ' separated by "/"'
            ),
        )
    return normalized


def validate_flow_code(code: str, expected_function_name: str) -> None:
    """Validate that Python code contains the expected @flow decorated function."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Python syntax error in code: {exc}",
        ) from exc

    flow_functions = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and _has_flow_decorator(node)
    ]

    if not flow_functions:
        raise HTTPException(
            status_code=400,
            detail=(
                "No @flow decorated function found in code."
                " Please add @flow decorator to your flow function."
            ),
        )

    if expected_function_name not in flow_functions:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Flow function '{expected_function_name}' not found"
                f" in code. Found: {', '.join(flow_functions)}."
                " Please ensure your flow function name"
                " matches the flow name."
            ),
        )


def _has_flow_decorator(node: ast.FunctionDef) -> bool:
    """Return whether the function is decorated with flow or flow(...)."""
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Name) and decorator.id == "flow":
            return True
        if (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Name)
            and decorator.func.id == "flow"
        ):
            return True
    return False


def format_with_ruff(file_path: Path) -> None:
    """Format a flow file in place; a missing or failing ruff is only logged."""
    try:
        result = subprocess.run(
            ["ruff", "format", str(file_path)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Ruff format timeout - skipping auto-format")
        return
    except FileNotFoundError:
        logger.warning("Ruff not found - skipping auto-format")
        return
    except Exception as exc:
        logger.warning(f"Failed to auto-format with ruff: {exc} - skipping")
        return

    if result.returncode == 0:
        logger.info(f"Auto-formatted flow code with ruff: {file_path}")
    else:
        logger.warning(f"Ruff format returned non-zero exit code: {result.stderr}")
