# LLM Agent

## Overview

The Copilot agent (`src/qdash/api/lib/copilot_agent.py`) uses the OpenAI SDK directly (not Pydantic AI) to interact with LLMs. It supports two API paths:

- **OpenAI Responses API** (default) -- Used for OpenAI models (e.g., gpt-4.1). Supports tool calling, structured JSON output, and multimodal input.
- **Chat Completions API** (fallback) -- Used for Ollama models that don't support the Responses API. No tool calling support.

## Tool Definitions

The agent has access to 17 tools defined in `AGENT_TOOLS`:

| Tool | Description |
|------|-------------|
| `get_qubit_params` | Get current calibrated parameters for a qubit |
| `get_latest_task_result` | Get the latest result for a specific calibration task |
| `get_task_history` | Get recent historical results for a calibration task |
| `get_parameter_timeseries` | Get time series data for a single qubit |
| `execute_python_analysis` | Execute Python code in a sandboxed environment (data store auto-injected) |
| `get_chip_summary` | Get summary of all qubits on a chip with statistics (stored tool) |
| `get_coupling_params` | Get calibrated parameters for coupling resonators |
| `get_execution_history` | Get recent execution history for a chip |
| `compare_qubits` | Compare parameters across multiple qubits |
| `get_chip_topology` | Get chip topology information |
| `search_task_results` | Search task result history with flexible filters |
| `get_calibration_notes` | Get calibration notes for a chip |
| `get_parameter_lineage` | Get version history of a calibration parameter |
| `get_provenance_lineage_graph` | Get provenance lineage graph for a parameter |
| `generate_chip_heatmap` | Generate chip-wide heatmap for a qubit metric |
| `get_chip_parameter_timeseries` | Batch timeseries for all qubits on a chip (stored tool) |
| `list_available_parameters` | List available output parameter names |

Tool executors are built by `CopilotDataService.build_tool_executors()`, mapping each tool name to a Python callable that queries MongoDB or invokes the sandbox. UI display labels are defined in `ai_labels.py`.

## Tool Call Loop

The agent implements a multi-round tool-calling loop (max `MAX_TOOL_ROUNDS = 10` iterations):

```
Build system prompt + input
        │
        ▼
  Apply tool executor wrappers:
    _wrap_rate_limited_executors  (throttle per-qubit timeseries)
    _wrap_tool_executors          (data store + chart interception)
        │
        ▼
  Call OpenAI Responses API
  (with tools if tool_executors provided)
        │
        ▼
  ┌─────────────────────┐
  │ Response has         │
  │ function_call items? │──No──▶ Extract output_text ──▶ Return
  └────────┬────────────┘
           │ Yes
           ▼
  For each function_call:
    1. Fire on_tool_call callback (for SSE progress)
    2. Look up executor by name
    3. Parse arguments from JSON
    4. Execute tool (through wrappers)
    5. Append function_call_output to input
           │
           ▼
  Rebuild input (preserve ALL output items
  including reasoning items to avoid 400 errors)
           │
           ▼
  Fire on_status("thinking") callback
           │
           ▼
  Call Responses API again ──▶ Loop back to check
  (up to MAX_TOOL_ROUNDS)
        │
        ▼
  Inject collected charts as blocks in response
```

Key implementation detail: when feeding tool results back, all model output items (reasoning, function_call, message) must be preserved in the input. Omitting reasoning items causes a 400 error from the OpenAI API.

## Data Store Pattern

Large-data tools (`get_chip_parameter_timeseries`, `get_chip_summary`) use a **data store** to avoid sending full datasets to the LLM:

1. Tool executes and returns full data
2. `_wrap_tool_executors` stores the result in `data_store[key]`
3. LLM receives only a compact summary (`_build_llm_summary`) with schema info and a `data_key`
4. When the LLM calls `execute_python_analysis`, the sandbox receives `data_store` as the `data` variable
5. LLM-generated code accesses full data via `data["t1"]`, `data["chip_summary"]`, etc.

This eliminates token double-consumption (LLM no longer echoes back large datasets as `context_data`) while preserving full data precision for sandbox analysis. See [Tool Result Compression](./tool-result-compression.md) for details.

## Response Format

The agent uses two response schemas:

### Blocks Schema (primary, used for OpenAI)

```json
{
  "blocks": [
    {"type": "text", "content": "Markdown text here", "chart": null},
    {"type": "chart", "content": null, "chart": {"data": [...], "layout": {...}}}
  ],
  "assessment": "good" | "warning" | "bad" | null
}
```

- `blocks` is an ordered array of content blocks, each either `text` or `chart`
- `chart` blocks contain Plotly.js specs with `data` (traces) and `layout`
- `assessment` provides an overall quality judgment (nullable for informational responses)
- Schema is passed with `strict: False` to allow flexible chart objects

### Legacy Schema (used for Ollama fallback)

```json
{
  "summary": "One-line summary",
  "assessment": "good" | "warning" | "bad",
  "explanation": "Detailed analysis",
  "potential_issues": ["issue1", "issue2"],
  "recommendations": ["action1", "action2"]
}
```

Legacy responses are automatically converted to blocks format via `_legacy_to_blocks()`.

## System Prompt Construction

The system prompt is assembled from multiple parts depending on the mode:

### Analysis Mode (`_build_system_prompt`)

```
SYSTEM_PROMPT_BASE          # Role definition + capabilities
  + Language instruction    # Response/thinking language from config
  + Task knowledge prompt   # From TaskKnowledge.to_prompt()
  + Scoring thresholds      # Per-metric good/excellent/bad ranges
  + Qubit context           # Current parameters for target qubit
  + Experiment results      # Metric values, R², output/run parameters
  + Historical results      # Recent runs for trend context
  + Neighbor qubit params   # Adjacent qubit data (if configured)
  + Coupling params         # Coupling data (if configured)
  + CHART_SYSTEM_PROMPT     # Response format instructions with examples
```

### Chat Mode (`_build_chat_system_prompt`)

```
CHAT_SYSTEM_PROMPT          # Role + tool usage instructions
  + Language instruction    # Response/thinking language
  + Scoring thresholds      # Per-metric ranges
  + Chip/qubit context      # Current chip_id, optional qid + params
  + CHART_SYSTEM_PROMPT     # Response format instructions
```

The chat system prompt includes detailed instructions for tool usage, including how to normalize qubit IDs and which parameter names to use for `get_parameter_timeseries`.

## Callbacks

The agent supports two async callback hooks for real-time progress reporting:

### `on_tool_call(name: str, args: dict) -> None`

Fired when the model emits a function call, before execution. Used by the SSE streaming layer to send tool progress events to the frontend.

### `on_status(status: str) -> None`

Fired when the agent enters a new processing phase (e.g., `"thinking"` when calling the LLM). Used to update the status indicator in the UI.

Both callbacks are optional (`None` by default) and are only used by the streaming endpoints.
