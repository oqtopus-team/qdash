"""Sandboxed Python execution for AI-driven data analysis.

Provides a restricted execution environment where LLM-generated Python code
can run safely with access to numerical/statistical libraries but no
filesystem, network, or OS access.
"""

from __future__ import annotations

import ast
import io
import logging
import signal
from contextlib import redirect_stdout
from typing import Any

logger = logging.getLogger(__name__)

EXECUTION_TIMEOUT_SECONDS = 5
MAX_OUTPUT_BYTES = 100 * 1024  # 100KB
MEMORY_LIMIT_BYTES = 256 * 1024 * 1024  # 256MB

ALLOWED_MODULES = frozenset(
    {
        "numpy",
        "pandas",
        "scipy",
        "scipy.stats",
        "scipy.optimize",
        "scipy.signal",
        "scipy.interpolate",
        "math",
        "statistics",
        "json",
        "datetime",
        "collections",
    }
)

FORBIDDEN_BUILTINS = frozenset({"eval", "exec", "compile", "open", "breakpoint", "exit", "quit"})

FORBIDDEN_DUNDER_ATTRS = frozenset(
    {
        "__subclasses__",
        "__bases__",
        "__mro__",
        "__globals__",
        "__code__",
        "__builtins__",
        "__import__",
        "__loader__",
        "__spec__",
    }
)

SAFE_BUILTINS = {
    "print": print,
    "len": len,
    "range": range,
    "dict": dict,
    "list": list,
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "tuple": tuple,
    "set": set,
    "frozenset": frozenset,
    "enumerate": enumerate,
    "zip": zip,
    "map": map,
    "filter": filter,
    "sorted": sorted,
    "reversed": reversed,
    "min": min,
    "max": max,
    "sum": sum,
    "abs": abs,
    "round": round,
    "isinstance": isinstance,
    "True": True,
    "False": False,
    "None": None,
    "ValueError": ValueError,
    "TypeError": TypeError,
    "KeyError": KeyError,
    "IndexError": IndexError,
    "ZeroDivisionError": ZeroDivisionError,
    "Exception": Exception,
}


def _safe_import(
    name: str,
    globals_: dict[str, Any] | None = None,
    locals_: dict[str, Any] | None = None,
    fromlist: tuple[str, ...] = (),
    level: int = 0,
) -> Any:
    """Custom __import__ that only allows whitelisted modules."""
    top_level = name.split(".")[0]
    if name not in ALLOWED_MODULES and top_level not in {m.split(".")[0] for m in ALLOWED_MODULES}:
        msg = f"Import of '{name}' is not allowed. Allowed modules: {', '.join(sorted(ALLOWED_MODULES))}"
        raise ImportError(msg)
    return __builtins__["__import__"](name, globals_, locals_, fromlist, level)  # type: ignore[index]


class _TimeoutError(Exception):
    """Raised when code execution exceeds the time limit."""


def _timeout_handler(signum: int, frame: Any) -> None:
    raise _TimeoutError(f"Execution timed out after {EXECUTION_TIMEOUT_SECONDS} seconds")


def _validate_ast(code: str) -> str | None:
    """Validate code using AST analysis.

    Returns an error message if the code is unsafe, or None if it passes validation.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"SyntaxError: {e}"

    for node in ast.walk(tree):
        # Check imports against allowed modules
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_level = alias.name.split(".")[0]
                if alias.name not in ALLOWED_MODULES and top_level not in {
                    m.split(".")[0] for m in ALLOWED_MODULES
                }:
                    return f"Import of '{alias.name}' is not allowed"

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                top_level = node.module.split(".")[0]
                if node.module not in ALLOWED_MODULES and top_level not in {
                    m.split(".")[0] for m in ALLOWED_MODULES
                }:
                    return f"Import from '{node.module}' is not allowed"

        # Check for forbidden builtin calls and forbidden name access
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in FORBIDDEN_BUILTINS:
                return f"Call to '{func.id}' is not allowed"

        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_DUNDER_ATTRS:
                return f"Access to '{node.id}' is not allowed"

        # Check for forbidden dunder attribute access
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_DUNDER_ATTRS:
                return f"Access to '{node.attr}' is not allowed"

    return None


def execute_python_analysis(
    code: str, context_data: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Execute Python analysis code in a sandboxed environment.

    Parameters
    ----------
    code : str
        Python code to execute. The code should set a ``result`` variable
        with the output. If ``result`` is not set, captured stdout is used.
    context_data : dict | None
        Optional data dict made available as ``data`` in the execution scope.

    Returns
    -------
    dict[str, Any]
        Execution result with keys:
        - ``output``: Text output (str)
        - ``chart``: Plotly chart spec (dict) or None
        - ``error``: Error message if execution failed (str or None)

    """
    # AST-based validation
    error = _validate_ast(code)
    if error is not None:
        return {"output": None, "chart": None, "error": error}

    # Build restricted globals
    restricted_globals: dict[str, Any] = {
        "__builtins__": {**SAFE_BUILTINS, "__import__": _safe_import},
        "data": context_data or {},
    }

    # Capture stdout
    stdout_capture = io.StringIO()

    # Set up timeout (Unix only)
    old_handler = None
    has_alarm = hasattr(signal, "SIGALRM")
    if has_alarm:
        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(EXECUTION_TIMEOUT_SECONDS)

    # Set up memory limit (Linux only)
    old_mem_limit = None
    try:
        import resource

        old_mem_limit = resource.getrlimit(resource.RLIMIT_AS)
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, old_mem_limit[1]))
    except (ImportError, ValueError, OSError):
        old_mem_limit = None

    try:
        with redirect_stdout(stdout_capture):
            exec(code, restricted_globals)  # noqa: S102

        # Cancel alarm
        if has_alarm:
            signal.alarm(0)

        # Extract result
        result_var = restricted_globals.get("result")
        if result_var is not None and isinstance(result_var, dict):
            output = result_var.get("output", "")
            chart = result_var.get("chart")
        else:
            # Fallback to stdout
            output = stdout_capture.getvalue()
            chart = None

        # Enforce output size limit
        output_str = str(output) if output else ""
        if len(output_str) > MAX_OUTPUT_BYTES:
            output_str = output_str[:MAX_OUTPUT_BYTES] + "\n... (output truncated)"

        # Validate chart structure
        if chart is not None:
            if not isinstance(chart, dict) or "data" not in chart:
                chart = None

        return {"output": output_str, "chart": chart, "error": None}

    except _TimeoutError:
        return {
            "output": None,
            "chart": None,
            "error": f"Execution timed out after {EXECUTION_TIMEOUT_SECONDS} seconds",
        }
    except MemoryError:
        return {
            "output": None,
            "chart": None,
            "error": f"Memory limit exceeded ({MEMORY_LIMIT_BYTES // (1024 * 1024)}MB)",
        }
    except ImportError as e:
        return {"output": None, "chart": None, "error": str(e)}
    except Exception as e:
        return {"output": None, "chart": None, "error": f"{type(e).__name__}: {e}"}
    finally:
        if has_alarm:
            signal.alarm(0)
            if old_handler is not None:
                signal.signal(signal.SIGALRM, old_handler)
        if old_mem_limit is not None:
            try:
                import resource

                resource.setrlimit(resource.RLIMIT_AS, old_mem_limit)
            except (ImportError, ValueError, OSError):
                pass
        stdout_capture.close()
