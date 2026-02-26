# Sandboxed Python Execution

## Overview

The sandbox (`src/qdash/api/lib/copilot_sandbox.py`) provides a restricted Python execution environment where LLM-generated code can run safely. It is exposed to the LLM agent as the `execute_python_analysis` tool, allowing the agent to perform calculations, statistical analysis, and generate Plotly charts from calibration data.

The sandbox enforces multiple layers of security:
1. **AST validation** -- Static analysis before execution
2. **Module whitelist** -- Only numerical/statistical imports allowed
3. **Restricted builtins** -- No `eval`, `exec`, `open`, etc.
4. **Timeout** -- Execution time cap via `signal.SIGALRM`

## Security Model

### AST Validation

Before any code is executed, `_validate_ast()` parses the code into an AST and walks every node to check for violations:

| Check | What it catches |
|-------|----------------|
| `ast.Import` / `ast.ImportFrom` | Imports of non-whitelisted modules (e.g., `import os`, `from subprocess import ...`) |
| `ast.Call` with `ast.Name` | Direct calls to forbidden builtins (`eval()`, `exec()`, `compile()`, `open()`, etc.) |
| `ast.Name` | Access to forbidden dunder names (`__subclasses__`, `__globals__`, etc.) |
| `ast.Attribute` | Attribute access to forbidden dunders (e.g., `obj.__code__`, `cls.__bases__`) |
| `SyntaxError` | Malformed Python code |

If validation fails, the code is never executed and an error is returned immediately.

### Allowed Modules

Only the following modules can be imported:

| Module | Purpose |
|--------|---------|
| `numpy` | Numerical arrays and operations |
| `pandas` | DataFrames and data manipulation |
| `scipy` | Scientific computing |
| `scipy.stats` | Statistical distributions and tests |
| `scipy.optimize` | Curve fitting and optimization |
| `scipy.signal` | Signal processing |
| `scipy.interpolate` | Interpolation |
| `plotly` | Base Plotly module |
| `plotly.graph_objects` | Plotly graph objects (go.Scatter, go.Figure, etc.) |
| `plotly.express` | High-level Plotly charting |
| `plotly.subplots` | Subplot creation |
| `math` | Basic math functions |
| `statistics` | Statistical measures |
| `json` | JSON serialization |
| `datetime` | Date/time handling |
| `_strptime` | Internal module required by `datetime.strptime()` |
| `collections` | Data structures (Counter, defaultdict, etc.) |

A custom `__import__` function (`_safe_import`) enforces this whitelist at runtime, providing a second layer of defense beyond AST validation.

### Safe Builtins

The execution environment replaces `__builtins__` with a curated set:

**Included**: `print`, `len`, `range`, `dict`, `list`, `int`, `float`, `str`, `bool`, `tuple`, `set`, `frozenset`, `enumerate`, `zip`, `map`, `filter`, `sorted`, `reversed`, `min`, `max`, `sum`, `abs`, `round`, `isinstance`, `True`, `False`, `None`, and common exception types (`ValueError`, `TypeError`, `KeyError`, `IndexError`, `ZeroDivisionError`, `Exception`).

**Excluded (with reasons)**:

| Builtin | Reason for exclusion |
|---------|---------------------|
| `eval` | Arbitrary code execution bypass |
| `exec` | Arbitrary code execution bypass |
| `compile` | Code object creation |
| `open` | Filesystem access |
| `breakpoint` | Debugger invocation |
| `exit` / `quit` | Process termination |

### Forbidden Dunder Attributes

Access to these attributes is blocked to prevent sandbox escapes via Python's introspection capabilities:

`__subclasses__`, `__bases__`, `__mro__`, `__globals__`, `__code__`, `__builtins__`, `__import__`, `__loader__`, `__spec__`

### Resource Limits

| Limit | Value | Mechanism |
|-------|-------|-----------|
| Execution timeout | 5 seconds | `signal.SIGALRM` (Unix) |
| Output size | 100 KB | String truncation after execution |

The alarm handler is restored in a `finally` block after execution. No `RLIMIT_AS` memory cap is set because it limits the entire process address space, which would affect the API server itself (see [LLM Integration Patterns](./llm-integration-patterns.md#resource-limits-in-shared-processes)).

## Execution Flow

```
LLM generates Python code
        │
        ▼
  _validate_ast(code)
        │
   ┌────┴────┐
   │ Error?  │──Yes──▶ Return {"error": "..."}
   └────┬────┘
        │ No
        ▼
  Build restricted globals
  (__builtins__ = SAFE_BUILTINS + _safe_import)
  Inject context_data as 'data' variable
        │
        ▼
  Set SIGALRM timeout
        │
        ▼
  exec(code, restricted_globals)
  with redirect_stdout
        │
   ┌────┴──────────────┐
   │ result var set?    │──Yes──▶ Extract output + chart
   └────┬──────────────┘
        │ No
        ▼
  Use captured stdout as output
        │
        ▼
  _ensure_serializable(chart)
  (convert Plotly objects to plain dicts)
        │
        ▼
  Validate chart structure (must have 'data' key)
  Truncate output if > 100KB
        │
        ▼
  Return {"output": "...", "chart": {...}, "error": null}
```

## Result Format

The `execute_python_analysis` function returns a dict with three keys:

```python
{
    "output": str | None,   # Text output (stdout or result["output"])
    "chart": dict | list[dict] | None,  # Plotly chart spec(s) {"data": [...], "layout": {...}}
    "error": str | None      # Error message if execution failed
}
```

The LLM-generated code can set a `result` variable as a dict:

```python
result = {
    "output": "Mean T1 = 45.2 μs, std = 3.1 μs",
    "chart": {
        "data": [{"x": dates, "y": values, "type": "scatter", "mode": "lines+markers"}],
        "layout": {"title": "T1 Trend", "xaxis": {"title": "Date"}}
    }
}
```

If no `result` variable is set, captured `stdout` becomes the output.

## Known Limitations

- **Unix-only timeout**: `signal.SIGALRM` is not available on Windows. Timeout enforcement is skipped on non-Unix platforms.
- **No network access**: The sandbox cannot make HTTP requests or access external services.
- **No matplotlib**: Only Plotly is supported for chart generation. Plotly objects (`go.Figure`, `go.Scatter`, etc.) are auto-converted to JSON-serializable dicts via `_ensure_serializable()`.
- **Single-threaded**: Code runs synchronously in the main process. The 5-second timeout prevents blocking.
