"""Core sandbox execution logic for AI-driven Python analysis."""

from __future__ import annotations

import ast
import io
import signal
from contextlib import redirect_stdout
from typing import Any, TypedDict

EXECUTION_TIMEOUT_SECONDS = 5
# Wall-clock budget granted to the worker on top of the execution timeout, to
# absorb interpreter startup. The worker is launched as a standalone script so
# startup is ~0.05s, but a cold page cache or a loaded host can be slower.
WORKER_STARTUP_GRACE_SECONDS = 5
MAX_OUTPUT_BYTES = 100 * 1024
MAX_WORKER_INPUT_BYTES = 2 * 1024 * 1024
MAX_WORKER_OUTPUT_BYTES = 256 * 1024
MEMORY_LIMIT_BYTES = 1024 * 1024 * 1024

ALLOWED_MODULES = frozenset(
    {
        "numpy",
        "pandas",
        "scipy",
        "scipy.stats",
        "scipy.optimize",
        "scipy.signal",
        "scipy.interpolate",
        "plotly",
        "plotly.graph_objects",
        "plotly.express",
        "plotly.subplots",
        "math",
        "statistics",
        "json",
        "datetime",
        "_strptime",
        "collections",
        "io",
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


class SandboxChartSpec(TypedDict, total=False):
    data: list[Any]
    layout: dict[str, Any]


class SandboxResult(TypedDict):
    output: str | None
    chart: SandboxChartSpec | list[SandboxChartSpec] | None
    error: str | None


def _safe_import(
    name: str,
    globals_: dict[str, Any] | None = None,
    locals_: dict[str, Any] | None = None,
    fromlist: tuple[str, ...] = (),
    level: int = 0,
) -> Any:
    """Custom __import__ that only allows whitelisted modules."""
    top_level = name.split(".", maxsplit=1)[0]
    if name not in ALLOWED_MODULES and top_level not in {m.split(".")[0] for m in ALLOWED_MODULES}:
        msg = f"Import of '{name}' is not allowed. Allowed modules: {', '.join(sorted(ALLOWED_MODULES))}"
        raise ImportError(msg)
    return __builtins__["__import__"](name, globals_, locals_, fromlist, level)  # type: ignore[index]


class _TimeoutError(Exception):
    """Raised when code execution exceeds the time limit."""


def _timeout_handler(signum: int, frame: Any) -> None:
    raise _TimeoutError(f"Execution timed out after {EXECUTION_TIMEOUT_SECONDS} seconds")


def validate_code(code: str) -> str | None:
    """Validate code using AST analysis.

    Pure and side-effect free, so the parent process runs it before spawning a worker.
    The worker runs it again as an independent defence layer.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"SyntaxError: {e}"

    for node in ast.walk(tree):
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
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in FORBIDDEN_BUILTINS:
                return f"Call to '{func.id}' is not allowed"
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_DUNDER_ATTRS:
                return f"Access to '{node.id}' is not allowed"
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_DUNDER_ATTRS:
                return f"Access to '{node.attr}' is not allowed"

    return None


def _ensure_serializable(obj: Any) -> Any:
    """Convert Plotly objects to plain JSON-compatible structures."""
    if hasattr(obj, "to_plotly_json") and callable(obj.to_plotly_json):
        return obj.to_plotly_json()
    if isinstance(obj, dict):
        return {k: _ensure_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_ensure_serializable(item) for item in obj]
    return obj


def execute_python_analysis_in_process(
    code: str,
    context_data: dict[str, Any] | None = None,
) -> SandboxResult:
    """Execute Python analysis code inside the sandbox worker process."""
    error = validate_code(code)
    if error is not None:
        return {"output": None, "chart": None, "error": error}

    restricted_globals: dict[str, Any] = {
        "__builtins__": {**SAFE_BUILTINS, "__import__": _safe_import},
        "data": context_data or {},
    }
    stdout_capture = io.StringIO()

    old_handler = None
    has_alarm = hasattr(signal, "SIGALRM")
    if has_alarm:
        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(EXECUTION_TIMEOUT_SECONDS)

    try:
        with redirect_stdout(stdout_capture):
            exec(code, restricted_globals)  # noqa: S102

        if has_alarm:
            signal.alarm(0)

        result_var = restricted_globals.get("result")
        if result_var is not None and isinstance(result_var, dict):
            output = result_var.get("output", "")
            chart = result_var.get("chart")
        else:
            output = stdout_capture.getvalue()
            chart = None

        output_str = str(output) if output else ""
        if len(output_str.encode("utf-8")) > MAX_OUTPUT_BYTES:
            output_bytes = output_str.encode("utf-8")[:MAX_OUTPUT_BYTES]
            output_str = output_bytes.decode("utf-8", errors="ignore") + "\n... (output truncated)"

        if chart is not None:
            chart = _ensure_serializable(chart)

        if chart is not None:
            if isinstance(chart, list):
                validated = [c for c in chart if isinstance(c, dict) and "data" in c]
                chart = validated if validated else None
            elif not isinstance(chart, dict) or "data" not in chart:
                chart = None

        return {"output": output_str, "chart": chart, "error": None}
    except _TimeoutError:
        return {
            "output": None,
            "chart": None,
            "error": f"Execution timed out after {EXECUTION_TIMEOUT_SECONDS} seconds",
        }
    except MemoryError:
        return {"output": None, "chart": None, "error": "Memory limit exceeded"}
    except ImportError as e:
        return {"output": None, "chart": None, "error": str(e)}
    except Exception as e:
        return {"output": None, "chart": None, "error": f"{type(e).__name__}: {e}"}
    finally:
        if has_alarm:
            signal.alarm(0)
            if old_handler is not None:
                signal.signal(signal.SIGALRM, old_handler)
        stdout_capture.close()
