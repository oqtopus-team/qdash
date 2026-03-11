# LLM Integration Patterns

Practical patterns for integrating LLM tool-calling into web applications with sandboxed code execution.

## Sandbox Patterns

### Hidden Import Dependencies

Some Python modules trigger internal imports at runtime that bypass the initial `import` statement. A sandbox's import whitelist must account for these transitive imports.

```python
# datetime.strptime() internally imports _strptime on first call
from datetime import datetime
dt = datetime.strptime("2024-01-15", "%Y-%m-%d")  # Fails without _strptime in whitelist
```

Libraries with deep module trees (e.g., Plotly) internally resolve between aliased module paths. A prefix-matching strategy handles this:

```python
def _safe_import(name, *args, **kwargs):
    if name not in ALLOWED_MODULES and not any(name.startswith(m + ".") for m in ALLOWED_MODULES):
        raise ImportError(f"Import of '{name}' is not allowed")
    return original_import(name, *args, **kwargs)
```

The prefix check lets `plotly.graph_objs.scatter` pass when `plotly.graph_objects` is whitelisted, because Plotly internally resolves between these paths.

### Object Serialization

LLMs writing Plotly code produce `go.Scatter()` / `go.Figure()` objects that are not JSON-serializable. Apply a recursive converter before returning results:

```python
def _ensure_serializable(obj):
    if hasattr(obj, "to_plotly_json") and callable(obj.to_plotly_json):
        return obj.to_plotly_json()
    if isinstance(obj, dict):
        return {k: _ensure_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_ensure_serializable(item) for item in obj]
    return obj
```

This handles both single objects and nested structures without requiring the LLM to know about serialization.

### Resource Limits in Shared Processes

`resource.setrlimit(RLIMIT_AS)` limits the virtual address space of the **entire process**, not just the sandboxed code. In a web server using in-process `exec()`, setting a memory cap can crash the server itself when legitimate requests allocate memory concurrently.

Defense-in-depth without memory limits:

| Layer | Mechanism | What it catches |
|-------|-----------|-----------------|
| AST validation | Static analysis | Malicious imports, forbidden builtins |
| Module whitelist | Runtime import hook | Any import not in the allowed set |
| Timeout | `signal.SIGALRM` | Infinite loops, excessive computation |
| Output cap | String truncation | Memory exhaustion via string building |

## Tool Design Patterns

### The N+1 Tool Call Problem

When an LLM has a per-item tool like `get_item_data(id)`, it calls it once per item. For a collection of 18 items, this means 18 sequential tool calls, each requiring a full LLM round-trip.

Provide batch tools alongside per-item tools:

| Tool | Scope | Use case |
|------|-------|----------|
| `get_item_data` | Single item | "Show details for item X" |
| `get_collection_data` | All items | "Compare items across the collection" |

A clear naming convention (e.g., `collection_` prefix) communicates scope to the LLM. Batch tools should return pre-computed statistics (mean, std, min, max) alongside raw data to reduce follow-up analysis calls.

### Prompt Engineering vs Code Enforcement

Prompt instructions like "NEVER call X in a loop" are insufficient. LLMs violate such instructions roughly 20% of the time, especially in longer conversations.

Use a code-level rate limiter as a safety net:

```python
CALL_LIMIT = 3

async def rate_limited(args):
    call_count[tool_name] += 1
    if call_count[tool_name] > CALL_LIMIT:
        return {"error": f"Rate limit reached. Use {batch_tool_name} instead."}
    return await original(args)
```

The error message tells the LLM *which* tool to use instead. Both the prompt instruction and the code-level limit are needed: the prompt handles the common case, the limiter handles the edge cases.

## Data Patterns

### Tool Result JSON Compression

LLM context windows are finite and tool results can be large. Simple character truncation breaks JSON mid-structure, producing unparseable results.

Apply semantic compression before truncation becomes necessary:

**Reduce numeric precision**

```python
# Before: 45.23456789012 (14 chars per number)
# After:  45.23 (5 chars per number)
def compact_float(v, sig_figs=4):
    return float(f"{v:.{sig_figs}g}")
```

**Shorten timestamps**

```python
# Before: "2024-01-15T10:30:00.000000+00:00" (32 chars)
# After:  "2024-01-15T10:30" (16 chars)
def compact_timestamp(ts):
    return ts.strftime("%Y-%m-%dT%H:%M")
```

**Use columnar format instead of row-based**

```json
// Row-based: repeated keys for every item
[{"qid": "Q00", "t1": 45.2, "t2": 12.1}, {"qid": "Q01", "t1": 43.8, "t2": 11.5}]

// Columnar: keys appear once
{"qids": ["Q00", "Q01"], "t1": [45.2, 43.8], "t2": [12.1, 11.5]}
```

**Graceful degradation**: when the result exceeds a size threshold, drop detail arrays and keep only summary statistics. The LLM can still produce a useful answer from stats alone.

### Server-Side Data Store

For very large tool results (e.g., 600+ timeseries rows), even compressed data can consume excessive tokens. A more effective pattern is to **not send the data to the LLM at all**:

1. Tool executes and returns full data
2. A wrapper stores the result server-side in a `data_store` dict
3. The LLM receives only a compact summary (schema info, row counts, scalar statistics)
4. When the LLM invokes a sandbox tool, the `data_store` is injected as a variable
5. LLM-generated code accesses full data locally — no token cost for the data itself

```python
# Summary sent to LLM (~200 chars instead of ~30K)
{
    "parameter_name": "t1",
    "num_qubits": 64,
    "statistics": {"mean": 45.2, "stdev": 3.1},
    "qubits": {"_schema": ["qid", "latest", "trend"], "_rows": 64},
    "timeseries": {"_schema": ["qid", "t", "v"], "_rows": 640},
    "data_key": "t1",
    "_note": "Full data available as data['t1'] in execute_python_analysis."
}
```

This eliminates both the original token cost and the echo-back cost when the LLM passes data to a sandbox tool.

### Chart Injection

When a tool produces a chart (e.g., a heatmap or analysis result), the chart JSON is typically 5-10K tokens. If returned as a tool result, the LLM often reproduces the entire chart spec in its response, wasting tokens and context.

Intercept chart-producing tools:

1. Tool executes normally and returns `{"chart": {...}, "output": "..."}`
2. A wrapper extracts the chart into a separate collection
3. The tool result sent to the LLM replaces the chart with a short message: `"[Chart collected and will be displayed directly]"`
4. After the LLM finishes, collected charts are injected into the response

```python
def heatmap_wrapper(args, _orig=original_heatmap):
    result = _orig(args)
    if isinstance(result, dict) and "chart" in result:
        collected_charts.append(result["chart"])
        return {"status": "success", "message": "Chart generated.", "statistics": result.get("statistics", {})}
    return result
```

This eliminates redundant chart JSON from the LLM's output while preserving the chart for the frontend. In QDash, `_wrap_tool_executors` combines data store, chart collection, and sandbox injection into a single wrapper layer.

### Null Safety in Tool Results

Tool results often use `{"error": None}` to indicate success. This pattern causes subtle bugs across layers:

```python
# Bad: truthy check passes for None
if result.get("error"):  # False for None -- happens to work, but fragile

# Bad: key-existence check is True even when value is None
if "error" in result:
    handle_error(result["error"])  # result["error"] is None

# Good: explicit None check
if result.get("error") is not None:
    handle_error(result["error"])
```

In LLM integrations tool results flow through multiple layers (executor -> wrapper -> agent -> serializer), and each layer may check for errors differently. Use `is not None` consistently.
