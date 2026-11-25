"""Validation rules for user flow sources."""

from __future__ import annotations

import ast
import re

from fastapi import HTTPException

from qdash.api.services.flow_service.flow_metadata import (
    is_flow_decorator,
    validate_session_name_declaration,
)

# Use full-string matching (fullmatch) so trailing newlines are rejected
_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")


def validate_flow_name(name: str) -> None:
    """Reject a flow name that is not alphanumeric or underscores."""
    if not _NAME_PATTERN.fullmatch(name):
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
    if not all(_NAME_PATTERN.fullmatch(part) for part in normalized.split("/")):
        raise HTTPException(
            status_code=400,
            detail="Folder must be segments of alphanumeric characters and underscores separated by /",
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

    try:
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                validate_session_name_declaration(node)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    flow_functions = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and _has_flow_decorator(node)
    ]

    if not flow_functions:
        raise HTTPException(
            status_code=400,
            detail=(
                "No @flow or @calibration_flow decorated function found in code. Please add "
                "@calibration_flow (or Prefect's @flow) to your flow function."
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
    """Return whether the function is decorated with flow or calibration_flow, bare or called."""
    return any(is_flow_decorator(decorator) for decorator in node.decorator_list)
