# LLM Agent

## Overview

The Copilot agent (`src/qdash/api/lib/copilot_agent.py`) uses the OpenAI SDK directly (not Pydantic AI) to interact with LLMs. It supports two API paths:

- **OpenAI Responses API** (default) -- Used for OpenAI models (e.g., gpt-4.1). Supports tool calling, structured JSON output, and multimodal input.
- **Chat Completions API** (fallback) -- Used for Ollama models that don't support the Responses API. No tool calling support.

## Tool Definitions

The agent has access to five tools defined in `AGENT_TOOLS`:

| Tool | Description | Required Parameters |
|------|-------------|-------------------|
| `get_qubit_params` | Get current calibrated parameters for a qubit (T1, T2, frequency, etc.) | `chip_id`, `qid` |
| `get_latest_task_result` | Get the latest result for a specific calibration task on a qubit | `task_name`, `chip_id`, `qid` |
| `get_task_history` | Get recent historical results for a calibration task | `task_name`, `chip_id`, `qid`, optional `last_n` |
| `get_parameter_timeseries` | Get time series data for a specific output parameter | `parameter_name`, `chip_id`, `qid`, optional `last_n` |
| `execute_python_analysis` | Execute Python code in a sandboxed environment | `code`, optional `context_data` |

Tool executors are wired in `_build_tool_executors()` in the router, mapping each tool name to a Python callable that queries MongoDB or invokes the sandbox.

## Tool Call Loop

The agent implements a multi-round tool-calling loop (max `MAX_TOOL_ROUNDS = 3` iterations):

```
Build system prompt + input
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
    4. Execute tool
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
```

Key implementation detail: when feeding tool results back, all model output items (reasoning, function_call, message) must be preserved in the input. Omitting reasoning items causes a 400 error from the OpenAI API.

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
