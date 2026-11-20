"""Import and builtin guardrails for metric scripts.

This is a guardrail for trusted project editors, **not a sandbox**. It stops accidental use
of files, processes and the network from script code and gives clear diagnostics, but
Python offers many ways around an AST/import filter. Isolation comes from the separate,
resource-bounded worker process that holds no credentials (see
:mod:`qdash.api.metric_runtime.executor`).

Ported from qdash-playground ``script_policy.py`` (Apache License 2.0).
"""

from __future__ import annotations

import ast
import builtins
import traceback
from typing import Any

from qdash.api.metric_runtime.sdk import SCRIPT_FILENAME

# Add a library here only when the API image ships it and its results are supported.
ALLOWED_IMPORTS = frozenset({"numpy", "scipy", "math", "statistics", "qdash_metrics"})
DISABLED_BUILTINS = frozenset(
    {"open", "exec", "eval", "compile", "input", "breakpoint", "help", "exit", "quit"}
)
SCRIPT_PREFIX = SCRIPT_FILENAME.split(":", 1)[0] + ":"


class ScriptPolicyError(ValueError):
    """A script statement violates the import policy."""

    def __init__(self, message: str, line: int | None = None, column: int | None = None):
        super().__init__(message)
        self.line, self.column = line, column


def permitted(module: str) -> bool:
    """Whether a source-level import of ``module`` is allowed (public names only)."""
    parts = module.split(".")
    return (
        parts[0] in ALLOWED_IMPORTS
        and not any(not part or part.startswith("_") for part in parts)
        and (parts[0] != "qdash_metrics" or len(parts) == 1)
    )


def _allowed_list() -> str:
    return ", ".join(sorted(ALLOWED_IMPORTS))


def validate_imports(source: str, filename: str = SCRIPT_FILENAME) -> None:
    """Reject import statements outside :data:`ALLOWED_IMPORTS`.

    Raises:
        SyntaxError: If the source does not parse.
        ScriptPolicyError: On the first disallowed import, with its position.
    """
    tree = ast.parse(source, filename=filename)
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [""] if node.level else [node.module or ""]
            if any(alias.name.startswith("_") for alias in node.names):
                raise ScriptPolicyError(
                    "Import public API names only", node.lineno, node.col_offset + 1
                )
        for name in names:
            if not permitted(name):
                raise ScriptPolicyError(
                    f"Import '{name or 'relative import'}' is not allowed. Use {_allowed_list()}.",
                    getattr(node, "lineno", None),
                    getattr(node, "col_offset", 0) + 1,
                )


def script_builtins() -> dict[str, Any]:
    """Builtins for script namespaces: disabled names removed, ``__import__`` checked."""
    values = {
        name: value for name, value in vars(builtins).items() if name not in DISABLED_BUILTINS
    }

    def safe_import(
        name: str,
        globals: Any = None,
        locals: Any = None,
        fromlist: Any = (),
        level: int = 0,
    ) -> Any:
        # Scientific C extensions can call the current frame's import hook at run time
        # (ndarray.sum() imports numpy internals). Allow their internal modules here;
        # validate_imports still restricts the script's own import statements.
        scientific_module = name.partition(".")[0] in {"numpy", "scipy"}
        if (
            level
            or not (permitted(name) or scientific_module)
            or any(str(part).startswith("_") for part in (fromlist or ()))
        ):
            raise ScriptPolicyError(f"Import '{name}' is not allowed. Use {_allowed_list()}.")
        return builtins.__import__(name, globals, locals, fromlist, level)

    values["__import__"] = safe_import
    return values


def diagnostic(exc: BaseException) -> dict[str, Any]:
    """``{message, line?, column?, function?}`` pointing at the script's own frame."""
    result: dict[str, Any] = {"message": f"{type(exc).__name__}: {exc}"}
    if isinstance(exc, SyntaxError) and (exc.filename or "").startswith(SCRIPT_PREFIX):
        result.update(line=exc.lineno, column=exc.offset)
    elif isinstance(exc, ScriptPolicyError):
        result.update(line=exc.line, column=exc.column)
    for frame in reversed(traceback.extract_tb(exc.__traceback__)):
        if frame.filename.startswith(SCRIPT_PREFIX):
            result.update(line=frame.lineno, function=frame.name)
            if frame.name == "<module>":
                result.pop("function")
            break
    return {key: value for key, value in result.items() if value is not None}


def error_message(exc: BaseException) -> str:
    """One-line message with the script line and function when known."""
    detail = diagnostic(exc)
    suffix = ""
    if "line" in detail:
        suffix = f" (line {detail['line']}"
        if "function" in detail:
            suffix += f", {detail['function']}"
        suffix += ")"
    return str(detail["message"]) + suffix
