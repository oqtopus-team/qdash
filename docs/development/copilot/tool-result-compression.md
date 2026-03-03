# Tool Result Compression

Copilot tool results are truncated at `MAX_TOOL_RESULT_CHARS = 30000`. Raw MongoDB documents easily exceed this, so tools apply semantic compression. Additionally, large-data tools use a **data store** pattern to avoid sending full datasets to the LLM at all.

## Two categories of tools

### Stored tools (data store pattern)

Tools that return large datasets store full results server-side in `data_store` and return only a compact summary to the LLM. The sandbox (`execute_python_analysis`) receives the full data automatically via the `data` variable.

| Tool | data_key | Description |
|------|----------|-------------|
| `get_chip_parameter_timeseries` | `args["parameter_name"]` (e.g., `"t1"`) | Per-qubit timeseries + stats |
| `get_chip_summary` | `"chip_summary"` | All qubits with statistics |

**Data flow:**

```
Tool → full data → data_store["t1"] (server-side)
     → summary (schema + stats) → json.dumps → LLM (~1K chars)
LLM → execute_python_analysis(code)  ← no context_data needed
→ sandbox: data["t1"] provides full dataset
```

**Summary format (`_build_llm_summary`):**

Lists of dicts are replaced with schema info:

```python
# Full result (stored in data_store)
{"qubits": [{"qid": "0", "latest": 5.05}, {"qid": "1", "latest": 4.98}]}

# Summary (sent to LLM)
{"qubits": {"_schema": ["qid", "latest"], "_rows": 2},
 "data_key": "t1",
 "_note": "Full data available as data['t1'] in execute_python_analysis. Do NOT pass data manually."}
```

Scalar values (chip_id, unit, num_qubits, statistics) pass through unchanged, giving the LLM enough context to decide what analysis to run.

### Direct tools (JSON to LLM)

Smaller-data tools return results directly to the LLM as JSON. These apply value-level compression to reduce token usage.

| Tool | Compression |
|------|-------------|
| `search_task_results` | `_compact_output_parameters`, `_compact_timestamp`, `_compact_number` |
| `get_task_history` | `_compact_output_parameters`, `_compact_timestamp` |
| `compare_qubits` | Value-only extraction, `_compact_number` |
| `get_provenance_lineage_graph` | Uniform `nodes` list, `edges` list, `_compact_number`, `_compact_timestamp` |
| `get_parameter_lineage` | `_compact_number`, `_compact_timestamp` |
| `get_execution_history` | `_compact_timestamp`, `_compact_number` |

## Value-level helpers

Three module-level functions in `copilot_data_service.py` handle common compression tasks for **direct tools**.

### `_compact_number(value)`

Rounds floats to 4 significant figures. Returns `int` when the fractional part is zero.

```python
_compact_number(45.23456789012)  # -> 45.23
_compact_number(0.000123456)     # -> 0.0001235
_compact_number(1200.0)          # -> 1200 (int)
```

Non-float inputs and non-finite values (`NaN`, `inf`) pass through unchanged.

### `_compact_timestamp(iso_str)`

Strips year, seconds, and microseconds from ISO timestamps.

```python
_compact_timestamp("2026-02-24T02:22:04.211000")  # -> "02-24 02:22"
_compact_timestamp(None)                            # -> ""
```

**Note:** Stored tools (timeseries) keep full ISO timestamps because the sandbox needs them for Plotly datetime parsing.

### `_compact_output_parameters(params)`

Reduces `output_parameters` from 10 fields per parameter to only what the LLM needs:

```python
# Before: 10 fields per parameter
{"qubit_frequency": {"parameter_name": "...", "value": 5.234567890, ...}}

# After: 2-3 fields
{"qubit_frequency": {"value": 5.235, "unit": "GHz", "error": 0.001234}}
```

## Stored tools: no value compression

Stored tools (`get_chip_parameter_timeseries`, `get_chip_summary`) do **not** apply `_compact_number` or `_compact_timestamp` to data that goes into `data_store`. The sandbox receives full-precision values and full ISO timestamps.

However, per-qubit **summary stats** (latest, min, max, mean, trend) and **chip-wide statistics** still use `_compact_number` because these appear in the LLM summary.

## Serialization

Tool results are serialized with:

```python
json.dumps(_sanitize_nan(tool_result), default=str, ensure_ascii=False)
```

- `_sanitize_nan`: Replaces `NaN`/`Inf` float values with `None` for valid JSON
- `default=str`: Handles non-primitive types (datetime, ObjectId, etc.)
- Charts bypass the LLM entirely and go directly to the frontend

## Adding a new tool

When adding a tool to `CopilotDataService`:

1. **Decide: stored or direct?** If the tool returns large datasets (100+ rows), make it a stored tool by adding it to `_STORED_TOOLS` in `copilot_agent.py`.
2. For **direct tools**: apply `_compact_timestamp()`, `_compact_number()`, and `_compact_output_parameters()` as appropriate.
3. For **stored tools**: keep full precision in the data (no `_compact_number` on timeseries values). Use `_compact_number` only on summary statistics that appear in the LLM summary.
4. Use list-of-dicts (not dict-of-dicts) for tabular data — move the key into a field (e.g., `{"qid": "0", ...}`).
5. Flatten nested structures into separate lists.

## References

- `src/qdash/api/services/copilot_data_service.py` — all tool implementations and helpers
- `src/qdash/api/lib/copilot_agent.py` — `_build_llm_summary`, `_wrap_tool_executors`, `_STORED_TOOLS`, `_sanitize_nan`, and `MAX_TOOL_RESULT_CHARS` truncation
