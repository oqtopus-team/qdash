"""Launch metadata a saved flow declares in its source, read without importing it.

A workflow names the calibration session QDash creates for its launches with
``@calibration_flow(session_name="Coherence Check")``. The API reads that literal
from the entrypoint's decorator with :mod:`ast`; the source is never imported or
evaluated. A name that is not a plain string literal is not read, and the launch
keeps the automatic session's default name, as a flow without one does.
"""

from __future__ import annotations

import ast

# Decorators that make a function a Prefect flow: Prefect's own and QDash's.
FLOW_DECORATORS = frozenset({"flow", "calibration_flow"})

SESSION_NAME_MAX_LENGTH = 500
"""The longest calibration session objective the API stores."""


def _decorator_name(node: ast.expr) -> str | None:
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return None


def is_flow_decorator(node: ast.expr) -> bool:
    """Whether ``node`` is ``@flow``, ``@flow(...)``, ``@calibration_flow`` or a call of it."""
    return _decorator_name(node) in FLOW_DECORATORS


def checked_session_name(value: object) -> str | None:
    """A session name as QDash stores it, or None when it is not a usable name."""
    if not isinstance(value, str):
        return None
    name = value.strip()
    if not name or len(name) > SESSION_NAME_MAX_LENGTH:
        return None
    return name


def declared_session_name(code: str, function_name: str) -> str | None:
    """The literal ``session_name`` of the entrypoint's ``@calibration_flow(...)``, if any."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if node.name != function_name:
            continue
        for decorator in node.decorator_list:
            if not (
                isinstance(decorator, ast.Call) and _decorator_name(decorator) == "calibration_flow"
            ):
                continue
            for keyword in decorator.keywords:
                if keyword.arg == "session_name" and isinstance(keyword.value, ast.Constant):
                    return checked_session_name(keyword.value.value)
    return None
