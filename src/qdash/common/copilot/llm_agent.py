"""OpenAI-based agent for calibration task analysis.

Uses the openai SDK directly to avoid pydantic-ai dependency conflicts.
Supports OpenAI Responses API (default) with Chat Completions API fallback for Ollama.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, cast

from openai import AsyncOpenAI, BadRequestError

from qdash.common.copilot.analysis_models import AnalysisResponse, TaskAnalysisContext

if TYPE_CHECKING:
    from qdash.common.copilot.python_sandbox import SandboxChartSpec, SandboxResult
    from qdash.common.copilot.settings import CopilotConfig, ModelConfig
else:
    from qdash.common.copilot.settings import CopilotConfig, ModelConfig

logger = logging.getLogger(__name__)

TRIAGE_DECISIONS = ("PASS_WITH_NOTE", "PASS", "REVIEW", "FAIL")
TRIAGE_ASSESSMENT = {
    "PASS": "good",
    "PASS_WITH_NOTE": "warning",
    "REVIEW": "warning",
    "FAIL": "bad",
}
TRIAGE_BLOCK_PREFIXES = (
    "**review triage**",
    "review triage",
    "**レビューのトリアージ**",
    "レビューのトリアージ",
)

SYSTEM_PROMPT_BASE = """\
You are an expert in superconducting qubit calibration.
You analyze calibration results for fixed-frequency transmon qubits
on a square-lattice chip with fixed couplers.

Your role:
- Interpret experimental results (graphs, parameters, metrics)
- Diagnose potential issues based on the data
- Cross-reference with past cases provided in the "Past cases" section to identify similar patterns or recurring issues
- Provide actionable recommendations
- Explain findings clearly to experimentalists

Always ground your analysis in the provided experimental context.
When discussing results, reference specific parameter values and thresholds.
IMPORTANT: If a "Past cases" section is provided, you MUST discuss those cases in your
analysis. Compare the current result with each past case, noting similarities and
differences. Even if no case exactly matches, explain which case is most relevant and why.

You have access to tools that can fetch data from the calibration database.
When the user asks about parameters or results from other experiments,
use the available tools to retrieve the data rather than saying it's unavailable.
The current qubit context (chip_id, qid) is provided in the system prompt below.

Tool results are returned in JSON format.
Some tools (get_chip_parameter_timeseries, get_chip_summary) store full data
server-side and return only a summary with a `data_key` field.
In execute_python_analysis, access stored data via data["<data_key>"]
(e.g., data["t1"]). Do NOT pass context_data manually.
"""

REVIEW_TRIAGE_INSTRUCTION = """\
## Review triage output

When answering about a calibration task result, begin your first text block with
a short review triage summary before the detailed explanation. Keep it concise
and use the following markdown shape:

**Review triage**
- Decision: `PASS` | `PASS_WITH_NOTE` | `REVIEW` | `FAIL`
- Human label suggestion: `CORRECT` | `SUSPICIOUS` | `MISASSIGNMENT` | `NO_SIGNAL` | `ANOMALY`
- Accepted parameter(s): parameter names and values that are well supported, or `none`
- Needs review: parameter names and values that are weak, ambiguous, or risky, or `none`
- Primary reason: one short sentence grounded in the plot/data
- Closest knowledge case: case title or `none`
- Suggested labels: comma-separated labels such as `weak_signal`, `boundary_case`, `model_overconservative`, `model_missed_issue`, or `none`
- Recommended action: one short operator action
- Optional note: one short caveat only when useful, otherwise `none`

For reliable parsing, the JSON `explanation` string MUST start exactly with
`**Review triage**`. Every triage field line MUST begin with hyphen-space
(`- `). Do not omit the hyphens, do not bold the field names, and do not put
ordinary prose before the triage block. Use this exact skeleton before any
detailed explanation:

**Review triage**
- Decision: `PASS` | `PASS_WITH_NOTE` | `REVIEW` | `FAIL`
- Human label suggestion: `CORRECT` | `SUSPICIOUS` | `MISASSIGNMENT` | `NO_SIGNAL` | `ANOMALY`
- Accepted parameter(s): ...
- Needs review: ...
- Primary reason: ...
- Closest knowledge case: ...
- Suggested labels: ...
- Recommended action: ...
- Optional note: ...

Keep the triage fields internally consistent:
- Use `PASS` only when all important output parameters are visually and physically supported.
  For `PASS`, set `Needs review: none`, `Suggested labels: none`, and make the recommended
  action an accept/use action rather than a remeasurement action.
- Use `PASS_WITH_NOTE` only when all output parameters that would be updated are
  acceptable without human intervention, but there is a minor caveat or optional
  follow-up. Put non-blocking caveats in `Optional note`, not in `Needs review`.
- Use `REVIEW` when any important output parameter should not be auto-accepted without a
  human check. If you use labels such as `weak_signal`, `boundary_case`, `ambiguous_doublet`,
  or `frequency_offset` for a parameter that affects acceptance, prefer `REVIEW`.
- If the detailed explanation says a parameter should be treated cautiously, maintained
  from history, not overwritten, rechecked before update, or used only as a reference value,
  then that parameter MUST appear in `Needs review` and the decision MUST be `REVIEW`.
- Do not set `Needs review: none` if the recommended action includes rechecking,
  maintaining, withholding, or not overwriting any output parameter.
- In `Accepted parameter(s)`, list only parameters you would allow the workflow to update
  automatically from this result. If a parameter is plausible but not update-safe, put it
  in `Needs review`, not in `Accepted parameter(s)`.
- Use `FAIL` for no visible signal, clear misassignment, measurement failure, or anomaly.
- Assessment consistency: set the top-level assessment to `good` for `PASS`,
  `warning` for `PASS_WITH_NOTE` or `REVIEW`, and `bad` for `FAIL`.

Then continue with the detailed explanation. In the detailed explanation:
- Separate visual support for each key parameter instead of giving one blended confidence.
- If f01/f12, resonator/Purcell, or similar paired features are involved, evaluate each feature independently.
- Use past cases as operational knowledge: state which case is closest, which lessons apply, and which lessons do not apply.
- Avoid overclaiming from visual plausibility alone; distinguish "visually supported", "plausible from history/physics", and "needs review".
- End with action-oriented recommendations that an operator can execute.
"""

MAX_TOOL_ROUNDS = 10
MAX_TOOL_RESULT_CHARS = 30000

ToolExecutor = Callable[[dict[str, Any]], Any]
ToolExecutors = dict[str, ToolExecutor]
StoredToolKey = str | Callable[[dict[str, Any]], str]
OnToolCallHook = Callable[[str, dict[str, Any]], Awaitable[None]] | None
OnStatusHook = Callable[[str], Awaitable[None]] | None

AGENT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "get_qubit_params",
        "description": "Get current calibrated parameters for a qubit (T1, T2, frequency, fidelity, etc.)",
        "parameters": {
            "type": "object",
            "properties": {
                "chip_id": {"type": "string", "description": "Chip ID"},
                "qid": {"type": "string", "description": "Qubit ID"},
            },
            "required": ["chip_id", "qid"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_latest_task_result",
        "description": "Get the latest result for a specific calibration task on a qubit. Use this to look up results from other tasks (e.g., CheckT1, CheckT2Echo, CheckRabi).",
        "parameters": {
            "type": "object",
            "properties": {
                "task_name": {
                    "type": "string",
                    "description": "Task class name (e.g. CheckT1, CheckT2Echo, CheckRabi, CheckQubitFrequency)",
                },
                "chip_id": {"type": "string", "description": "Chip ID"},
                "qid": {"type": "string", "description": "Qubit ID"},
            },
            "required": ["task_name", "chip_id", "qid"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_task_history",
        "description": "Get recent historical results for a calibration task on a qubit.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_name": {"type": "string", "description": "Task class name"},
                "chip_id": {"type": "string", "description": "Chip ID"},
                "qid": {"type": "string", "description": "Qubit ID"},
                "last_n": {
                    "type": "integer",
                    "description": "Number of recent results (default 5)",
                },
            },
            "required": ["task_name", "chip_id", "qid"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_parameter_timeseries",
        "description": (
            "Get time series data for a specific output parameter for a SINGLE qubit. "
            "Only use this for ONE specific qubit. "
            "NEVER call this in a loop for multiple qubits — use get_chip_parameter_timeseries instead. "
            "If the user asks about a parameter across the chip or multiple qubits, "
            "call get_chip_parameter_timeseries (one call for all qubits). "
            "Any output parameter name stored in the calibration database can be queried "
            "(e.g. 'qubit_frequency', 't1', 't2_echo', 'x90_gate_fidelity', "
            "'resonator_frequency', 'pi_amplitude', etc.). "
            "If unsure which parameter names are available, call list_available_parameters first. "
            "Returns a list of {value, unit, calibrated_at, execution_id, task_id} entries "
            "ordered by time."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "parameter_name": {
                    "type": "string",
                    "description": (
                        "The output parameter name to query. "
                        "Use list_available_parameters to discover valid names."
                    ),
                },
                "chip_id": {"type": "string", "description": "Chip ID"},
                "qid": {"type": "string", "description": "Qubit ID"},
                "last_n": {
                    "type": "integer",
                    "description": "Number of recent results to return (default 10)",
                },
            },
            "required": ["parameter_name", "chip_id", "qid"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "execute_python_analysis",
        "description": (
            "Execute Python code in a sandboxed environment for data analysis. "
            "Use this when you need to perform calculations, statistical analysis, "
            "or generate Plotly charts from data retrieved by other tools. "
            "Available libraries: numpy, pandas, scipy, scipy.stats, plotly, math, statistics, "
            "json, datetime, collections, io. "
            "Stored tool results are automatically available as data['<data_key>'] "
            "(e.g., data['t1'], data['chip_summary']). Do NOT pass data manually. "
            "Set a 'result' variable as a dict with 'output' (text) and optionally "
            "'chart' (single Plotly spec or a list of Plotly specs, each with 'data' and 'layout' keys). "
            "You can use plotly.graph_objects, plotly.express, or plotly.subplots."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": (
                        "Python code to execute. Use data['<key>'] to access stored tool results "
                        "(e.g., data['t1']['timeseries'] for timeseries data). "
                        "Set result = {'output': '...', 'chart': {'data': [...], 'layout': {...}}} "
                        "for single chart, or 'chart': [chart1, chart2, ...] for multiple charts."
                    ),
                },
            },
            "required": ["code"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_chip_summary",
        "description": (
            "Get a summary of all qubits on a chip. Returns: "
            "(1) statistics: per-parameter mean/median/std/min/max across all qubits, "
            "(2) qubits: dict mapping qid to {param: value} for each qubit. "
            "Use this for chip-wide analysis or when the user asks about overall chip quality."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "chip_id": {"type": "string", "description": "Chip ID"},
                "param_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional list of parameter names to include "
                        "(e.g. ['qubit_frequency', 't1']). If omitted, all parameters are returned."
                    ),
                },
            },
            "required": ["chip_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_coupling_params",
        "description": (
            "Get calibrated parameters for coupling resonators. "
            "Specify either a coupling_id (e.g. '0-1') or a qubit_id to get all couplings "
            "involving that qubit. Optional param_names filter."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "chip_id": {"type": "string", "description": "Chip ID"},
                "coupling_id": {
                    "type": "string",
                    "description": "Coupling ID (e.g. '0-1'). If provided, returns this coupling only.",
                },
                "qubit_id": {
                    "type": "string",
                    "description": "Qubit ID. If provided, returns all couplings involving this qubit.",
                },
                "param_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of parameter names to filter.",
                },
            },
            "required": ["chip_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_execution_history",
        "description": (
            "Get recent execution history for a chip. "
            "Returns execution runs with status, timing, and metadata. "
            "Optional filters by status and tags."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "chip_id": {"type": "string", "description": "Chip ID"},
                "status": {
                    "type": "string",
                    "description": "Filter by status (e.g. 'completed', 'failed', 'running')",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by tags",
                },
                "last_n": {
                    "type": "integer",
                    "description": "Number of recent executions to return (default 10)",
                },
            },
            "required": ["chip_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "compare_qubits",
        "description": (
            "Compare parameters across multiple qubits side by side. "
            "Provide a list of qubit IDs to compare their current calibrated parameters."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "chip_id": {"type": "string", "description": "Chip ID"},
                "qids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of qubit IDs to compare (e.g. ['0', '1', '2'])",
                },
                "param_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of parameter names to compare.",
                },
            },
            "required": ["chip_id", "qids"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_chip_topology",
        "description": (
            "Get the chip topology information including grid size, qubit positions, "
            "and coupling connections. Useful for understanding the physical layout."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "chip_id": {"type": "string", "description": "Chip ID"},
            },
            "required": ["chip_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "search_task_results",
        "description": (
            "Search task result history with flexible filters. "
            "Use this to find specific task results by task name, qubit, status, or execution."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "chip_id": {"type": "string", "description": "Chip ID"},
                "task_name": {"type": "string", "description": "Filter by task name"},
                "qid": {"type": "string", "description": "Filter by qubit ID"},
                "status": {
                    "type": "string",
                    "description": "Filter by status (e.g. 'completed', 'failed')",
                },
                "execution_id": {"type": "string", "description": "Filter by execution ID"},
                "last_n": {
                    "type": "integer",
                    "description": "Number of results to return (default 10)",
                },
            },
            "required": ["chip_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_calibration_notes",
        "description": (
            "Get calibration notes for a chip. "
            "Notes contain observations, issues, and annotations recorded during calibration."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "chip_id": {"type": "string", "description": "Chip ID"},
                "execution_id": {"type": "string", "description": "Filter by execution ID"},
                "task_id": {"type": "string", "description": "Filter by task ID"},
                "last_n": {
                    "type": "integer",
                    "description": "Number of notes to return (default 10)",
                },
            },
            "required": ["chip_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_parameter_lineage",
        "description": (
            "Get the version history (lineage) of a specific calibration parameter. "
            "Shows how the parameter value evolved over time across executions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "parameter_name": {
                    "type": "string",
                    "description": "Parameter name (e.g. 'qubit_frequency', 't1')",
                },
                "qid": {"type": "string", "description": "Qubit or coupling ID"},
                "chip_id": {"type": "string", "description": "Chip ID"},
                "last_n": {
                    "type": "integer",
                    "description": "Number of versions to return (default 10)",
                },
            },
            "required": ["parameter_name", "qid", "chip_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_provenance_lineage_graph",
        "description": (
            "Get the provenance lineage graph for a parameter version entity. "
            "Returns a DAG of ancestor entities (input parameters) and activities (tasks) "
            "that contributed to the specified entity. Use this to trace how a parameter "
            "value was derived — which task produced it and which input parameters were used. "
            "The entity_id format is 'parameter_name:qid:execution_id:task_id' "
            "(e.g. 'qubit_frequency:0:exec-123:task-456'). "
            "You can obtain entity_id values from get_parameter_lineage results."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": (
                        "Entity identifier in format 'parameter_name:qid:execution_id:task_id'. "
                        "Obtain from get_parameter_lineage results."
                    ),
                },
                "chip_id": {
                    "type": "string",
                    "description": "Chip ID (used to resolve the project context)",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum traversal depth (default 5, max 20)",
                },
            },
            "required": ["entity_id", "chip_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "generate_chip_heatmap",
        "description": (
            "Generate a chip-wide heatmap for a qubit metric. "
            "Returns a Plotly chart showing per-qubit values arranged on the chip grid layout. "
            "Use this when the user wants to visualise a metric across the entire chip "
            "(e.g. 'Show me a T1 heatmap', 'Visualise qubit frequencies on the chip')."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "chip_id": {"type": "string", "description": "Chip ID"},
                "metric_name": {
                    "type": "string",
                    "description": (
                        "Qubit metric key as defined in the metrics configuration "
                        "(e.g. 't1', 't2_echo', 'qubit_frequency', 'x90_gate_fidelity')"
                    ),
                },
                "selection_mode": {
                    "type": "string",
                    "enum": ["latest", "best", "average"],
                    "description": "Value selection strategy (default: 'latest')",
                },
                "within_hours": {
                    "type": "integer",
                    "description": "Optional time range filter in hours",
                },
            },
            "required": ["chip_id", "metric_name"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_chip_parameter_timeseries",
        "description": (
            "Batch version of get_parameter_timeseries — fetches timeseries for multiple "
            "qubits in one call. Returns per-qubit data including: timeseries array "
            "(value + start_at in chronological order, suitable for plotting), latest value, "
            "trend, min/max/mean stats, plus chip-wide statistics. "
            "Use this instead of calling get_parameter_timeseries for each qubit individually. "
            "Omit qids to fetch ALL qubits on the chip."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "chip_id": {"type": "string", "description": "Chip ID"},
                "parameter_name": {
                    "type": "string",
                    "description": "Parameter name (e.g. 't1', 'qubit_frequency')",
                },
                "qids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional list of qubit IDs to fetch (e.g. ['0', '1', '5']). "
                        "If omitted, fetches ALL qubits on the chip."
                    ),
                },
                "last_n": {
                    "type": "integer",
                    "description": "Recent values per qubit (default 10)",
                },
            },
            "required": ["chip_id", "parameter_name"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "list_available_parameters",
        "description": (
            "List all output parameter names that have been recorded in the calibration database. "
            "Use this to discover valid parameter names for get_parameter_timeseries. "
            "Optionally filter by a specific qubit."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "chip_id": {"type": "string", "description": "Chip ID"},
                "qid": {
                    "type": "string",
                    "description": "Optional qubit ID to filter parameters for a specific qubit",
                },
            },
            "required": ["chip_id"],
            "additionalProperties": False,
        },
    },
]

ANALYSIS_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "assessment": {"type": "string", "enum": ["good", "warning", "bad"]},
        "explanation": {"type": "string"},
        "potential_issues": {"type": "array", "items": {"type": "string"}},
        "recommendations": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "summary",
        "assessment",
        "explanation",
        "potential_issues",
        "recommendations",
    ],
    "additionalProperties": False,
}

BLOCKS_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["text", "chart"]},
                    "content": {"type": ["string", "null"]},
                    "chart": {"type": ["object", "null"]},
                },
                "required": ["type", "content", "chart"],
                "additionalProperties": False,
            },
        },
        "assessment": {
            "type": ["string", "null"],
            "enum": ["good", "warning", "bad", None],
        },
    },
    # `assessment` is listed alongside `blocks` so the schema is strict-mode
    # compliant (all declared properties must appear in `required`). It may
    # still be null when the answer is informational rather than evaluative.
    "required": ["blocks", "assessment"],
    "additionalProperties": False,
}

CHAT_COMPLETIONS_STRICT_EMULATION = """\

## STRICT OUTPUT CONTRACT (provider does not enforce response_format)

The HTTP client parses your reply with JSON.parse() directly. Any non-JSON byte
will cause a parse error and the user will see a fallback rendering instead of
the structured response.

Hard rules — no exceptions:

- After every tool call resolves and you are ready to answer, your reply must
  be a SINGLE JSON object matching the `blocks` schema above. Nothing else.
- Do not include conversational filler such as "Sure, here is", "Let me",
  "Here is the answer", "I hope this helps", or any sign-off line.
- Do not wrap the JSON in markdown code fences (no triple backticks).
- Do not emit text before the opening `{` or after the closing `}`.
- Newlines inside JSON strings must be escaped as `\\n`.
- If you need to think, do it in the JSON's text block content, never as
  pre-text outside the JSON. (Native thinking-mode reasoning is stripped server
  side and does not need to be in the JSON.)

Self-check: the very first character of your final reply must be `{` and the
very last character must be `}`.
"""

CHART_SYSTEM_PROMPT = """\

## Response format

You MUST respond with a JSON object containing a "blocks" array.
Each block has "type" ("text" or "chart"), "content" (string or null), and "chart" (object or null).

For text blocks: {"type": "text", "content": "your text here (markdown supported)", "chart": null}
For chart blocks: {"type": "chart", "content": null, "chart": {"data": [...], "layout": {...}}}

Chart specifications use Plotly.js format:
- "data" is an array of trace objects (e.g. {"x": [...], "y": [...], "type": "scatter", "mode": "lines+markers", "name": "T1"})
- "layout" is a Plotly layout object (e.g. {"title": "T1 Trend", "xaxis": {"title": "Date"}, "yaxis": {"title": "T1 (μs)"}})
- Keep layouts compact: no excessive margins, use autosize
- Supported trace types: scatter, bar, histogram, heatmap

Always include at least one text block explaining the chart or analysis.
When you call `generate_chip_heatmap`, the chart is automatically generated and injected into the response.
Do NOT reproduce the chart JSON data in your response. Only include text blocks analyzing the statistics.
Similarly, charts from `execute_python_analysis` are automatically included — do not copy chart data into your response.
When showing data trends, prefer scatter plots with mode "lines+markers".
Set "assessment" to "good", "warning", or "bad" when analyzing results. Set to null for informational responses.

Example response:
{
  "blocks": [
    {"type": "text", "content": "Here are the T1 results:", "chart": null},
    {"type": "chart", "content": null, "chart": {
      "data": [{"x": ["01/01", "01/02"], "y": [45.2, 43.1], "type": "scatter", "mode": "lines+markers", "name": "T1"}],
      "layout": {"title": "T1 Trend", "xaxis": {"title": "Date"}, "yaxis": {"title": "T1 (μs)"}}
    }},
    {"type": "text", "content": "T1 is stable around 44 μs.", "chart": null}
  ],
  "assessment": "good"
}
"""

RESPONSE_FORMAT_INSTRUCTION = """\

You MUST respond with a valid JSON object (no prose, no code fences) matching this schema:
{
  "summary": "One-line result summary",
  "assessment": "good" | "warning" | "bad",
  "explanation": "Detailed analysis and interpretation",
  "potential_issues": ["issue1", "issue2"],
  "recommendations": ["action1", "action2"]
}

Rules:
- `potential_issues` and `recommendations` MUST be JSON arrays of strings. Use an empty array `[]` when nothing applies — never a single string or null.
- `assessment` MUST be exactly one of `good`, `warning`, `bad` (lowercase).
- Write the user-facing text fields (`summary`, `explanation`, items in `potential_issues` and `recommendations`) in the user's response language as instructed above. Keep technical terms like T1, T2, fidelity in English.
- The `explanation` field MUST begin with the exact review triage markdown described above, starting with `**Review triage**`.
- Put the triage fields inside `explanation`; do not add extra JSON keys for them.
- Keep `assessment` consistent with the triage decision: `good` for `PASS`, `warning` for `PASS_WITH_NOTE` or `REVIEW`, and `bad` for `FAIL`.
- Keep the response concise for interactive use: after the triage, write at most 6 short bullets or 3 short paragraphs in `explanation`, at most 3 potential issues, and at most 3 recommendations.
- Do not add keys outside this schema.
"""


def _build_client(config: CopilotConfig) -> AsyncOpenAI:
    """Build an AsyncOpenAI client based on provider configuration.

    The ``provider`` field selects which SDK invocation style to use, not the
    upstream vendor. ``openai`` covers both the official OpenAI API and any
    OpenAI-compatible gateway (DeepSeek, vLLM, custom hosts) via ``base_url``.
    ``ollama`` adds Ollama-specific defaults (localhost fallback, ``/v1``
    suffix, dummy api_key). To pick which endpoint on that client is called
    (``/v1/responses`` vs ``/v1/chat/completions``), see ``ModelConfig.api_style``.
    """
    provider = config.model.provider
    base_url = _resolve_model_config_value(config.model.base_url, field_name="base_url")
    api_key_env = config.model.api_key_env

    if provider == "ollama":
        default_endpoint = os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434"
        endpoint = (base_url or default_endpoint).rstrip("/")
        if not endpoint.endswith("/v1"):
            endpoint = f"{endpoint}/v1"
        key_env = api_key_env or "OLLAMA_API_KEY"
        return AsyncOpenAI(base_url=endpoint, api_key=os.environ.get(key_env, "ollama"))
    elif provider == "openai":
        if base_url:
            base_url = _normalize_openai_compatible_base_url(base_url)
            key = os.environ.get(api_key_env or "OPENAI_API_KEY", "local")
            return AsyncOpenAI(base_url=base_url, api_key=key)
        return AsyncOpenAI(api_key=os.environ.get(api_key_env or "OPENAI_API_KEY"))
    elif provider == "anthropic":
        raise ValueError(
            "Anthropic provider is not supported with openai SDK. Use openai or ollama."
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


def _normalize_openai_compatible_base_url(base_url: str) -> str:
    """Normalize local OpenAI-compatible endpoints to the SDK's expected base URL."""
    endpoint = base_url.rstrip("/")
    if not endpoint.endswith("/v1"):
        endpoint = f"{endpoint}/v1"
    return endpoint


def _resolve_model_config_value(value: str | None, *, field_name: str) -> str | None:
    """Resolve model config strings that reference environment variables.

    Supports ``env:VAR_NAME`` and ``${VAR_NAME}`` forms. Resolution happens when
    the model is selected, so optional local model entries do not require their
    environment variables to exist at startup.
    """
    if not value:
        return value
    if value.startswith("env:"):
        env_name = value.removeprefix("env:").strip()
        resolved = os.environ.get(env_name)
        if not resolved:
            raise ValueError(f"{field_name} environment variable is not set: {env_name}")
        return resolved
    if value.startswith("${") and value.endswith("}"):
        env_name = value[2:-1].strip()
        resolved = os.environ.get(env_name)
        if not resolved:
            raise ValueError(f"{field_name} environment variable is not set: {env_name}")
        return resolved
    return value


def _build_language_instruction(config: CopilotConfig | None) -> str:
    """Build language instruction based on copilot config.

    Parameters
    ----------
    config : CopilotConfig | None
        Copilot configuration. Falls back to default behavior if None.

    """
    if config is None:
        return "Respond in the same language as the user's message."

    response_lang = config.response_language
    thinking_lang = config.thinking_language

    parts: list[str] = []

    if thinking_lang != response_lang and not config.model.disable_thinking_instruction:
        parts.append(f"Think and reason internally in {thinking_lang} for technical precision.")

    if response_lang == "ja":
        parts.append(
            "Always respond in Japanese (日本語). "
            "Use technical terms in English where appropriate (e.g., T1, T2, fidelity)."
        )
    elif response_lang == "en":
        parts.append("Always respond in English.")
    else:
        parts.append(f"Always respond in {response_lang}.")

    return " ".join(parts)


def _build_system_prompt(
    context: TaskAnalysisContext,
    *,
    config: CopilotConfig | None = None,
    include_response_format: bool = False,
    has_expected_images: bool = False,
    has_experiment_image: bool = False,
) -> str:
    """Build the full system prompt from base prompt and context.

    Parameters
    ----------
    context : TaskAnalysisContext
        Structured context for the analysis.
    config : CopilotConfig | None
        Copilot configuration for language settings.
    include_response_format : bool
        If True, append RESPONSE_FORMAT_INSTRUCTION for providers that
        do not support structured output natively (e.g. Ollama).
    has_expected_images : bool
        If True, expected reference images are included in the input.
    has_experiment_image : bool
        If True, the actual experiment result image is included in the input.

    """
    parts = [SYSTEM_PROMPT_BASE, _build_language_instruction(config)]

    # Image analysis instructions
    if has_expected_images or has_experiment_image:
        img_instructions = ["\n## Image analysis"]
        if has_expected_images and has_experiment_image:
            img_instructions.append(
                "Reference images showing expected results are provided along with "
                "the actual experimental result image. Compare the actual result with "
                "these references to identify deviations, anomalies, or quality issues."
            )
        elif has_expected_images:
            img_instructions.append(
                "Reference images showing expected results are provided. "
                "Use them to understand what a good result looks like for this task."
            )
        elif has_experiment_image:
            img_instructions.append(
                "The actual experimental result image is provided. "
                "Analyze the graph/figure for quality, fit accuracy, and anomalies."
            )
        parts.append("\n".join(img_instructions))

    # Task knowledge
    parts.append(context.task_knowledge_prompt)
    parts.append(REVIEW_TRIAGE_INSTRUCTION)

    # Scoring thresholds from deployment config
    if config and config.scoring:
        threshold_lines = ["\n## Scoring thresholds (deployment-specific)"]
        for metric, thresh in config.scoring.items():
            range_parts = []
            if thresh.bad is not None:
                range_parts.append(f"bad < {thresh.bad} {thresh.unit}")
            range_parts.append(f"good > {thresh.good} {thresh.unit}")
            range_parts.append(f"excellent > {thresh.excellent} {thresh.unit}")
            if not thresh.higher_is_better:
                range_parts.append("(lower is better)")
            threshold_lines.append(f"- {metric}: {', '.join(range_parts)}")
        parts.append("\n".join(threshold_lines))

    # Qubit context
    lines = [f"\n## Target: Qubit {context.qid} (Chip: {context.chip_id})"]
    if context.qubit_params:
        lines.append("\n### Current qubit parameters")
        for key, val in context.qubit_params.items():
            if isinstance(val, dict) and "value" in val:
                lines.append(f"- {key}: {val['value']} {val.get('unit', '')}")
            else:
                lines.append(f"- {key}: {val}")
    parts.append("\n".join(lines))

    # Experiment results
    exp_lines = ["\n## Experiment results"]
    if context.metric_value is not None:
        exp_lines.append(f"**Metric value**: {context.metric_value} {context.metric_unit}")
    if context.r2_value is not None:
        exp_lines.append(f"**Fit R²**: {context.r2_value}")
    if context.recent_values:
        exp_lines.append(f"**Recent values**: {context.recent_values}")
    if context.output_parameters:
        exp_lines.append("\n### Output parameters")
        for key, val in context.output_parameters.items():
            if isinstance(val, dict) and "value" in val:
                exp_lines.append(f"- {key}: {val['value']} {val.get('unit', '')}")
            else:
                exp_lines.append(f"- {key}: {val}")
    if context.run_parameters:
        exp_lines.append("\n### Run parameters")
        for key, val in context.run_parameters.items():
            if isinstance(val, dict) and "value" in val:
                exp_lines.append(f"- {key}: {val['value']} {val.get('unit', '')}")
            else:
                exp_lines.append(f"- {key}: {val}")
    parts.append("\n".join(exp_lines))

    # Dynamic context: historical results
    if context.history_results:
        hist_lines = ["\n## Historical results (recent runs)"]
        for i, run in enumerate(context.history_results, 1):
            hist_lines.append(f"\n### Run {i}")
            if run.get("start_at"):
                hist_lines.append(f"- start_at: {run['start_at']}")
            if run.get("execution_id"):
                hist_lines.append(f"- execution_id: {run['execution_id']}")
            for key, val in run.get("output_parameters", {}).items():
                if isinstance(val, dict) and "value" in val:
                    hist_lines.append(f"- {key}: {val['value']} {val.get('unit', '')}")
                else:
                    hist_lines.append(f"- {key}: {val}")
        parts.append("\n".join(hist_lines))

    # Dynamic context: neighbor qubit parameters
    if context.neighbor_qubit_params:
        nb_lines = ["\n## Neighbor qubit parameters"]
        for nb_qid, params in context.neighbor_qubit_params.items():
            nb_lines.append(f"\n### Qubit {nb_qid}")
            for key, val in params.items():
                if isinstance(val, dict) and "value" in val:
                    nb_lines.append(f"- {key}: {val['value']} {val.get('unit', '')}")
                else:
                    nb_lines.append(f"- {key}: {val}")
        parts.append("\n".join(nb_lines))

    # Dynamic context: coupling parameters
    if context.coupling_params:
        cp_lines = ["\n## Coupling parameters"]
        for coupling_id, params in context.coupling_params.items():
            cp_lines.append(f"\n### Coupling {coupling_id}")
            for key, val in params.items():
                if isinstance(val, dict) and "value" in val:
                    cp_lines.append(f"- {key}: {val['value']} {val.get('unit', '')}")
                else:
                    cp_lines.append(f"- {key}: {val}")
        parts.append("\n".join(cp_lines))

    if include_response_format:
        parts.append(RESPONSE_FORMAT_INSTRUCTION)

    return "\n\n".join(parts)


def _build_input(
    user_message: str,
    image_base64: str | None,
    conversation_history: list[dict[str, str]] | None,
    expected_images: list[tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Build the input items list for the OpenAI Responses API.

    Unlike Chat Completions, system messages are passed via the
    ``instructions`` parameter, so only user/assistant messages
    are included here.

    Parameters
    ----------
    user_message : str
        The user's question.
    image_base64 : str | None
        Base64-encoded experiment result image.
    conversation_history : list[dict[str, str]] | None
        Previous conversation messages.
    expected_images : list[tuple[str, str]] | None
        List of (base64_data, alt_text) for expected reference images.

    """
    items: list[dict[str, Any]] = []

    # Add conversation history
    if conversation_history:
        for m in conversation_history:
            role = m.get("role", "user")
            content = m.get("content", "")
            # Responses API requires "output_text" for assistant messages
            text_type = "output_text" if role == "assistant" else "input_text"
            items.append(
                {
                    "role": role,
                    "content": [{"type": text_type, "text": content}],
                }
            )

    # Build the current user message content parts
    content_parts: list[dict[str, Any]] = []

    # Add expected reference images first (with labels)
    if expected_images:
        content_parts.append({"type": "input_text", "text": "Expected result reference images:"})
        for b64_data, alt_text in expected_images:
            content_parts.append({"type": "input_text", "text": f"[Reference: {alt_text}]"})
            content_parts.append(
                {
                    "type": "input_image",
                    "image_url": f"data:image/png;base64,{b64_data}",
                }
            )

    # Add experiment result image (with label)
    if image_base64:
        content_parts.append({"type": "input_text", "text": "Actual experimental result:"})
        content_parts.append(
            {
                "type": "input_image",
                "image_url": f"data:image/png;base64,{image_base64}",
            }
        )

    # Add the user message text
    content_parts.append({"type": "input_text", "text": user_message})

    items.append({"role": "user", "content": content_parts})

    return items


def _build_messages(
    system_prompt: str,
    user_message: str,
    image_base64: str | None,
    conversation_history: list[dict[str, str]] | None,
    expected_images: list[tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Build the messages list for the Chat Completions API (Ollama fallback)."""
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    # Add conversation history
    if conversation_history:
        for m in conversation_history:
            messages.append(
                {
                    "role": m.get("role", "user"),
                    "content": m.get("content", ""),
                }
            )

    # Build the current user message
    has_images = image_base64 or expected_images
    if has_images:
        content_parts: list[dict[str, Any]] = []

        # Add expected reference images first
        if expected_images:
            content_parts.append({"type": "text", "text": "Expected result reference images:"})
            for b64_data, alt_text in expected_images:
                content_parts.append({"type": "text", "text": f"[Reference: {alt_text}]"})
                content_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64_data}"},
                    }
                )

        # Add experiment result image
        if image_base64:
            content_parts.append({"type": "text", "text": "Actual experimental result:"})
            content_parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                }
            )

        content_parts.append({"type": "text", "text": user_message})
        messages.append({"role": "user", "content": content_parts})
    else:
        messages.append({"role": "user", "content": user_message})

    return messages


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences from text."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # skip first ```json line
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text


def _extract_triage_fallback(content: str) -> AnalysisResponse | None:
    """Build a legacy response from a free-form review triage block."""
    fields = {
        "Decision": "",
        "Human label suggestion": "",
        "Accepted parameter(s)": "",
        "Needs review": "",
        "Primary reason": "",
        "Closest knowledge case": "",
        "Suggested labels": "",
        "Recommended action": "",
        "Optional note": "",
    }
    for field in fields:
        match = re.search(rf"^\s*[-*]\s+{re.escape(field)}:\s*(.*)$", content, re.M)
        if not match:
            continue
        value = match.group(1).strip().strip("`")
        if field == "Decision":
            for decision in TRIAGE_DECISIONS:
                if re.search(rf"\b{decision}\b", value):
                    value = decision
                    break
        fields[field] = value

    decision = fields["Decision"]
    if not decision:
        return None

    triage = "\n".join(
        [
            "**Review triage**",
            *(f"- {field}: {value or 'none'}" for field, value in fields.items()),
        ]
    )
    return AnalysisResponse(
        summary=fields["Primary reason"] or "Analysis complete",
        assessment=TRIAGE_ASSESSMENT.get(decision, "warning"),
        explanation=triage,
        potential_issues=(
            [] if decision in {"PASS", "PASS_WITH_NOTE"} else [fields["Primary reason"]]
        ),
        recommendations=[fields["Recommended action"]] if fields["Recommended action"] else [],
    )


def _has_triage_block(text: str) -> bool:
    """Return True when text starts with the required review-triage block."""
    return text.lower().lstrip().startswith(TRIAGE_BLOCK_PREFIXES)


def _missing_triage_response(content: str) -> AnalysisResponse:
    """Return a safe review note when a local model omits required triage fields."""
    summary = "AI triage response did not include the required review block."
    triage = "\n".join(
        [
            "**Review triage**",
            "- Decision: `REVIEW`",
            "- Human label suggestion: `SUSPICIOUS`",
            "- Accepted parameter(s): `none`",
            "- Needs review: `all output parameters`",
            f"- Primary reason: {summary}",
            "- Closest knowledge case: `none`",
            "- Suggested labels: `model_format_error`",
            "- Recommended action: Open the task result and review the plot manually.",
            "- Optional note: The raw local-model response was missing the triage block.",
        ]
    )
    return AnalysisResponse(
        summary=summary,
        assessment="warning",
        explanation=triage,
        potential_issues=[summary],
        recommendations=["Open the task result and review the plot manually."],
    )


def _parse_response(content: str) -> AnalysisResponse:
    """Parse LLM response into AnalysisResponse, handling JSON and plain text."""
    text = _strip_code_fences(content)

    try:
        data = json.loads(text)
        response = AnalysisResponse(**data)
        if response.explanation and _has_triage_block(response.explanation):
            return response
        fallback_response = _extract_triage_fallback(response.explanation or content)
        if fallback_response is not None:
            return fallback_response
        logger.warning("Local model response omitted required review triage block: %s", content)
        return _missing_triage_response(content)
    except (json.JSONDecodeError, ValueError):
        fallback_response = _extract_triage_fallback(content)
        if fallback_response is not None:
            return fallback_response
        logger.warning("Local model response omitted required review triage block: %s", content)
        return _missing_triage_response(content)


_ASSESSMENT_LABELS_JA = {
    "good": ("✅", "良好"),
    "warning": ("⚠️", "要注意"),
    "warn": ("⚠️", "要注意"),
    "bad": ("❌", "不良"),
    "poor": ("❌", "不良"),
}
_ASSESSMENT_LABELS_EN = {
    "good": ("✅", "Good"),
    "warning": ("⚠️", "Warning"),
    "warn": ("⚠️", "Warning"),
    "bad": ("❌", "Bad"),
    "poor": ("❌", "Bad"),
}

_SECTION_LABELS = {
    "ja": {
        "summary": "概要",
        "explanation": "詳細",
        "issues": "潜在的な問題",
        "recommendations": "推奨アクション",
        "assessment": "評価",
    },
    "en": {
        "summary": "Summary",
        "explanation": "Details",
        "issues": "Potential Issues",
        "recommendations": "Recommendations",
        "assessment": "Assessment",
    },
}


def _format_assessment_badge(assessment: str | None, lang: str) -> str:
    if not assessment:
        return ""
    key = assessment.strip().lower()
    table = _ASSESSMENT_LABELS_JA if lang == "ja" else _ASSESSMENT_LABELS_EN
    emoji, label = table.get(key, ("", assessment))
    return f"{emoji} **{label}**".strip()


_LANG_FULLNAME = {"ja": "Japanese (日本語)", "en": "English"}


def _looks_like_target_language(text: str, lang: str) -> bool:
    """Cheap heuristic: does `text` already look like it's in `lang`?"""
    if not text:
        return True
    if lang == "ja":
        # Any CJK character → assume already Japanese enough.
        return any("\u3040" <= ch <= "\u30ff" or "\u4e00" <= ch <= "\u9fff" for ch in text)
    if lang == "en":
        return all(ord(ch) < 0x3000 for ch in text)
    return True


async def _translate_analysis_response(
    response: AnalysisResponse,
    target_lang: str,
    general_model: ModelConfig,
) -> AnalysisResponse:
    """Translate an AnalysisResponse via the general (non-specialized) model.

    Used when a calibration-specialized analysis model replies in English but
    the user expects a different language (e.g. Japanese). Only free-form
    text fields are translated; `assessment` is left untouched.
    """
    lang_key = "ja" if target_lang.startswith("ja") else "en"
    fields_needing = []
    if response.summary and not _looks_like_target_language(response.summary, lang_key):
        fields_needing.append("summary")
    if response.explanation and not _looks_like_target_language(response.explanation, lang_key):
        fields_needing.append("explanation")
    if any(i and not _looks_like_target_language(i, lang_key) for i in response.potential_issues):
        fields_needing.append("potential_issues")
    if any(r and not _looks_like_target_language(r, lang_key) for r in response.recommendations):
        fields_needing.append("recommendations")

    if not fields_needing:
        return response

    lang_name = _LANG_FULLNAME.get(lang_key, target_lang)
    payload = {
        "summary": response.summary or "",
        "explanation": response.explanation or "",
        "potential_issues": list(response.potential_issues),
        "recommendations": list(response.recommendations),
    }
    system = (
        f"You translate technical quantum-calibration analysis into natural, fluent {lang_name}. "
        "Preserve all numeric values, units, and technical terms like T1, T2, fidelity, Rabi, "
        "R², π-pulse, I/Q in their original form. Keep the same JSON shape. "
        "Do not add, remove, or reinterpret content — only translate."
    )
    user = (
        "Translate the string values in this JSON into "
        f"{lang_name}. Return a JSON object with the SAME keys and array lengths.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )

    try:
        translator_config = CopilotConfig(model=general_model)
        client = _build_client(translator_config)
        kwargs: dict[str, Any] = {
            "model": general_model.name,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        if general_model.temperature is not None:
            kwargs["temperature"] = 0.2
        try:
            completion = await client.chat.completions.create(**kwargs)
        except BadRequestError as exc:
            if "temperature" in str(exc):
                kwargs.pop("temperature", None)
                completion = await client.chat.completions.create(**kwargs)
            else:
                raise
        content = completion.choices[0].message.content or "{}"
        data = json.loads(_strip_code_fences(content))
    except Exception as exc:
        logger.warning("Translation to %s failed, using original text: %s", lang_key, exc)
        return response

    def _coerce_list(val: Any, fallback: list[str]) -> list[str]:
        if isinstance(val, list):
            return [str(x) for x in val if x]
        if isinstance(val, str) and val:
            return [val]
        return fallback

    return response.model_copy(
        update={
            "summary": str(data.get("summary") or response.summary),
            "explanation": str(data.get("explanation") or response.explanation),
            "potential_issues": _coerce_list(
                data.get("potential_issues"), list(response.potential_issues)
            ),
            "recommendations": _coerce_list(
                data.get("recommendations"), list(response.recommendations)
            ),
        }
    )


def _legacy_to_blocks(
    response: AnalysisResponse, config: CopilotConfig | None = None
) -> dict[str, Any]:
    """Convert a legacy AnalysisResponse to a multi-block human-friendly response.

    Emits one block per semantic section (assessment badge, summary, explanation,
    issues, recommendations) so that the frontend can render them separately — e.g.
    as dedicated cards once richer block types land.
    """
    lang_raw = (config.response_language if config else "ja") or "ja"
    lang = "ja" if lang_raw.startswith("ja") else "en"
    labels = _SECTION_LABELS[lang]

    blocks: list[dict[str, Any]] = []

    def _text_block(content: str) -> None:
        if content and content.strip():
            blocks.append({"type": "text", "content": content, "chart": None})

    summary = (response.summary or "").strip()
    explanation = (response.explanation or "").strip()

    # Local/Ollama analysis uses the legacy JSON schema. If the model followed
    # the review-triage instruction, preserve that operational triage as the
    # first visible block instead of burying it under the generic assessment
    # badge.
    normalized_explanation = explanation.lower().lstrip()
    explanation_starts_with_triage = normalized_explanation.startswith(
        ("**review triage**", "review triage", "**レビューのトリアージ**", "レビューのトリアージ")
    )
    if explanation and explanation != summary and explanation_starts_with_triage:
        _text_block(explanation)

    badge = _format_assessment_badge(response.assessment, lang)
    if badge or summary:
        header = f"### {labels['assessment']}: {badge}" if badge else ""
        body = summary
        _text_block("\n\n".join(p for p in (header, body) if p))

    if explanation and explanation != summary and not explanation_starts_with_triage:
        _text_block(f"**{labels['explanation']}**\n\n{explanation}")

    issues = [i for i in response.potential_issues if i and str(i).strip()]
    if issues:
        issue_lines = "\n".join(f"- {issue}" for issue in issues)
        _text_block(f"**{labels['issues']}**\n\n{issue_lines}")

    recs = [r for r in response.recommendations if r and str(r).strip()]
    if recs:
        rec_lines = "\n".join(f"- {rec}" for rec in recs)
        _text_block(f"**{labels['recommendations']}**\n\n{rec_lines}")

    if not blocks:
        fallback = explanation or summary or ""
        blocks.append({"type": "text", "content": fallback, "chart": None})

    return {
        "blocks": blocks,
        "assessment": response.assessment,
    }


def _extract_first_json_object(text: str) -> dict[str, Any] | None:
    """Scan ``text`` for the first balanced ``{...}`` block and json.loads it.

    Used when a model can't be forced via ``response_format`` and wraps the
    structured payload in conversational filler (DeepSeek's ds4-server today
    behaves like this). Brace counting is string-aware so braces inside strings
    don't break the match.
    """
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
                    if isinstance(parsed, dict):
                        return parsed
                    break
        start = text.find("{", start + 1)
    return None


def _has_real_blocks(parsed: dict[str, Any]) -> bool:
    """Return True when the parsed BLOCKS payload came from real JSON output.

    A single text block with assessment=None matches the plain-text fallback
    branch of ``_parse_blocks_response``. Multi-block payloads or any explicit
    assessment value imply the model actually emitted JSON.
    """
    blocks = parsed.get("blocks") if isinstance(parsed, dict) else None
    if not isinstance(blocks, list):
        return False
    if len(blocks) != 1:
        return True
    return parsed.get("assessment") is not None


def _parse_blocks_response(content: str, config: CopilotConfig | None = None) -> dict[str, Any]:
    """Parse LLM response into blocks format dict, with fallback to legacy."""
    text = _strip_code_fences(content)

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        data = _extract_first_json_object(text)

    if isinstance(data, dict):
        if "blocks" in data and isinstance(data["blocks"], list):
            return dict(data)
        # Legacy format returned — convert
        try:
            response = AnalysisResponse(**data)
            return _legacy_to_blocks(response, config)
        except ValueError:
            pass

    # Plain text fallback
    return {
        "blocks": [{"type": "text", "content": content, "chart": None}],
        "assessment": None,
    }


_STORED_TOOLS: dict[str, StoredToolKey] = {
    "get_chip_parameter_timeseries": lambda args: args["parameter_name"],
    "get_chip_summary": lambda _args: "chip_summary",
}


def _build_llm_summary(full_result: dict[str, Any], data_key: str) -> dict[str, Any]:
    """Replace list items with schema info and attach data_key.

    The LLM receives only a compact summary (schema + row count) instead of
    the full dataset, which is stored server-side in ``data_store``.
    """
    summary: dict[str, Any] = {}
    for key, value in full_result.items():
        if isinstance(value, list):
            if value and isinstance(value[0], dict):
                summary[key] = {"_schema": list(value[0].keys()), "_rows": len(value)}
            else:
                summary[key] = {"_rows": len(value)}
        else:
            summary[key] = value
    summary["data_key"] = data_key
    summary["_note"] = (
        f"Full data available as data['{data_key}'] in execute_python_analysis. "
        f"Do NOT pass data manually."
    )
    return summary


def _wrap_tool_executors(
    tool_executors: ToolExecutors,
    data_store: dict[str, Any],
) -> tuple[ToolExecutors, list[SandboxChartSpec | dict[str, Any]]]:
    """Wrap tool executors to handle data store and chart collection.

    - **Stored tools** (``get_chip_parameter_timeseries``, ``get_chip_summary``):
      full results go to *data_store*; the LLM receives only a summary.
    - **Heatmap**: chart is collected for direct injection into the response.
    - **execute_python_analysis**: *data_store* is auto-injected as ``data``;
      charts are collected.
    """
    collected_charts: list[SandboxChartSpec | dict[str, Any]] = []
    wrapped = dict(tool_executors)

    # Stored tools: full data → data_store, summary → LLM
    for tool_name, key_fn in _STORED_TOOLS.items():
        original = wrapped.get(tool_name)
        if original:
            original_executor = cast("ToolExecutor", original)

            def stored_wrapper(
                args: dict[str, Any],
                _orig: ToolExecutor = original_executor,
                _kfn: StoredToolKey = key_fn,
            ) -> Any:
                result = _orig(args)
                if isinstance(result, dict) and "error" not in result:
                    key = _kfn(args) if callable(_kfn) else _kfn
                    data_store[key] = result
                    return _build_llm_summary(result, key)
                return result

            wrapped[tool_name] = stored_wrapper

    # Heatmap: chart collection
    original_heatmap = wrapped.get("generate_chip_heatmap")
    if original_heatmap:
        original_heatmap_executor = cast("ToolExecutor", original_heatmap)

        def heatmap_wrapper(
            args: dict[str, Any], _orig: ToolExecutor = original_heatmap_executor
        ) -> Any:
            result = _orig(args)
            if isinstance(result, dict) and "chart" in result:
                collected_charts.append(result["chart"])
                return {
                    "status": "success",
                    "message": (
                        "Heatmap chart generated. It will be automatically appended "
                        "to your response. Do NOT reproduce the chart data."
                    ),
                    "statistics": result.get("statistics", {}),
                }
            return result

        wrapped["generate_chip_heatmap"] = heatmap_wrapper

    # execute_python_analysis: data_store auto-injected + chart collection
    def python_wrapper(args: dict[str, Any]) -> SandboxResult | dict[str, Any]:
        from qdash.common.copilot.python_sandbox import execute_python_analysis

        result = execute_python_analysis(args["code"], data_store)
        if isinstance(result, dict) and result.get("chart"):
            chart = result["chart"]
            if isinstance(chart, list):
                collected_charts.extend(chart)
            elif chart is not None:
                collected_charts.append(chart)
            return {
                "output": result.get("output", ""),
                "chart": None,
                "chart_note": "Chart(s) generated. They will be automatically appended to your response.",
            }
        return result

    wrapped["execute_python_analysis"] = python_wrapper

    return wrapped, collected_charts


# Maximum number of get_parameter_timeseries calls allowed per conversation turn.
# Beyond this limit the executor returns an error nudging the LLM to use
# get_chip_parameter_timeseries instead.
_TIMESERIES_CALL_LIMIT = 3


def _wrap_rate_limited_executors(tool_executors: ToolExecutors) -> ToolExecutors:
    """Wrap per-qubit tools with a call-count limiter.

    If the LLM calls ``get_parameter_timeseries`` more than
    ``_TIMESERIES_CALL_LIMIT`` times in a single turn, subsequent calls
    return an error directing it to ``get_chip_parameter_timeseries``.
    """
    wrapped = dict(tool_executors)

    original_ts = wrapped.get("get_parameter_timeseries")
    if original_ts is None:
        return wrapped

    original_ts_executor = cast("ToolExecutor", original_ts)
    call_count = 0

    def timeseries_limiter(args: dict[str, Any], _orig: ToolExecutor = original_ts_executor) -> Any:
        nonlocal call_count
        call_count += 1
        if call_count > _TIMESERIES_CALL_LIMIT:
            logger.warning(
                "get_parameter_timeseries called %d times (limit %d), blocking",
                call_count,
                _TIMESERIES_CALL_LIMIT,
            )
            return {
                "error": (
                    f"Too many get_parameter_timeseries calls ({call_count}). "
                    "Use get_chip_parameter_timeseries instead — it returns per-qubit "
                    "timeseries arrays (value + timestamp, suitable for plotting), "
                    "stats, and trends for ALL qubits in one call."
                )
            }
        return _orig(args)

    wrapped["get_parameter_timeseries"] = timeseries_limiter
    return wrapped


def _sanitize_nan(obj: Any) -> Any:
    """Recursively replace NaN/Inf float values with None for valid JSON.

    Preserves non-primitive types (e.g. numpy arrays) so that Plotly
    chart specs remain valid.
    """
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_nan(v) for v in obj]
    return obj


def _inject_collected_charts(
    result: dict[str, Any],
    collected_charts: list[SandboxChartSpec | dict[str, Any]],
) -> dict[str, Any]:
    """Append tool-generated charts to the blocks response."""
    if not collected_charts:
        return result
    blocks = result.get("blocks", [])
    for chart in collected_charts:
        blocks.append({"type": "chart", "content": None, "chart": _sanitize_nan(chart)})
    result["blocks"] = blocks
    return result


async def _run_responses_api(
    client: AsyncOpenAI,
    system_prompt: str,
    input_items: list[dict[str, Any]],
    config: CopilotConfig,
    tool_executors: ToolExecutors | None = None,
    *,
    response_schema: dict[str, Any] | None = None,
    strict_schema: bool = True,
    on_tool_call: OnToolCallHook = None,
    on_status: OnStatusHook = None,
) -> str:
    """Call OpenAI Responses API and return the output text.

    When *tool_executors* is provided, the request includes ``AGENT_TOOLS``
    and the function implements a tool-call loop: if the model emits
    ``function_call`` items, each call is dispatched to the corresponding
    executor, the result is fed back, and the model is called again.
    The loop runs for at most ``MAX_TOOL_ROUNDS`` iterations.
    """
    schema = response_schema or ANALYSIS_RESPONSE_SCHEMA
    kwargs: dict[str, Any] = {
        "model": config.model.name,
        "instructions": system_prompt,
        "input": input_items,
        "max_output_tokens": config.model.max_output_tokens,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "analysis_response",
                "strict": strict_schema,
                "schema": schema,
            }
        },
    }
    if tool_executors:
        kwargs["tools"] = AGENT_TOOLS
    if config.model.temperature is not None:
        kwargs["temperature"] = config.model.temperature

    async def _create(**kw: Any) -> Any:
        try:
            return await client.responses.create(**kw)
        except BadRequestError as exc:
            if "temperature" in str(exc) and "temperature" in kw:
                logger.info("Model does not support temperature, retrying without it")
                kw.pop("temperature")
                return await client.responses.create(**kw)
            raise

    if on_status:
        await on_status("thinking")
    response = await _create(**kwargs)

    # Tool call loop
    if tool_executors:
        for _round in range(MAX_TOOL_ROUNDS):
            function_calls = [item for item in response.output if item.type == "function_call"]
            if not function_calls:
                break

            logger.info(
                "Tool round %d/%d: %d call(s) — %s",
                _round + 1,
                MAX_TOOL_ROUNDS,
                len(function_calls),
                ", ".join(fc.name for fc in function_calls),
            )

            # Build new input: previous input + ALL model output items.
            # All items (reasoning, function_call, message, etc.) must be
            # preserved — omitting reasoning items causes a 400 error.
            new_input = list(kwargs["input"])
            for item in response.output:
                new_input.append(item.model_dump())

            for fc in function_calls:
                try:
                    args = json.loads(fc.arguments)
                except (json.JSONDecodeError, TypeError):
                    args = {}

                logger.info("Tool call: %s(%s)", fc.name, json.dumps(args, ensure_ascii=False))

                if on_tool_call:
                    await on_tool_call(fc.name, args)

                executor = tool_executors.get(fc.name)
                if executor is None:
                    tool_result = {"error": f"Unknown tool: {fc.name}"}
                else:
                    try:
                        tool_result = executor(args)
                    except KeyError as e:
                        logger.warning("Tool %s missing required argument: %s", fc.name, e)
                        tool_result = {
                            "error": f"Missing required argument: {e}. "
                            f"Please provide all required parameters."
                        }
                    except Exception as e:
                        logger.warning("Tool %s execution failed: %s", fc.name, e)
                        tool_result = {"error": str(e)}

                output_str = json.dumps(_sanitize_nan(tool_result), default=str, ensure_ascii=False)
                if len(output_str) > MAX_TOOL_RESULT_CHARS:
                    logger.warning(
                        "Tool %s result truncated: %d -> %d chars",
                        fc.name,
                        len(output_str),
                        MAX_TOOL_RESULT_CHARS,
                    )
                    output_str = (
                        output_str[:MAX_TOOL_RESULT_CHARS] + '... [TRUNCATED - result too large]"}'
                    )

                # Log result summary
                result_summary = ""
                if isinstance(tool_result, dict):
                    if tool_result.get("error"):
                        result_summary = f" error={str(tool_result['error'])[:100]}"
                    elif "num_qubits" in tool_result:
                        result_summary = f" num_qubits={tool_result['num_qubits']}"
                elif isinstance(tool_result, list):
                    result_summary = f" items={len(tool_result)}"
                logger.info(
                    "Tool result: %s -> %d chars%s",
                    fc.name,
                    len(output_str),
                    result_summary,
                )
                new_input.append(
                    {
                        "type": "function_call_output",
                        "call_id": fc.call_id,
                        "output": output_str,
                    }
                )

            kwargs["input"] = new_input
            if on_status:
                await on_status("thinking")
            response = await _create(**kwargs)

    output = response.output_text
    logger.info(
        "Responses API output_text length=%s, output items=%d, types=%s",
        len(output) if output else "None",
        len(response.output),
        [getattr(item, "type", "?") for item in response.output],
    )
    if output is None:
        # Model exhausted tool rounds without producing text.
        # Re-call the model WITHOUT tools to force a text response
        # based on the information gathered so far.
        logger.warning(
            "Tool rounds exhausted (%d). Retrying without tools to force text output.",
            MAX_TOOL_ROUNDS,
        )

        # Build final input with all gathered context
        final_input = list(kwargs["input"])
        for item in response.output:
            dumped = item.model_dump()
            # Skip function_call items — they can't be included without tools
            if dumped.get("type") == "function_call":
                continue
            final_input.append(dumped)

        final_kwargs = {k: v for k, v in kwargs.items() if k != "tools"}
        final_kwargs["input"] = final_input
        if on_status:
            await on_status("thinking")
        response = await _create(**final_kwargs)
        output = response.output_text

        if output is None:
            text_items = [
                getattr(item, "text", None)
                for item in response.output
                if getattr(item, "type", None) == "message"
            ]
            if text_items:
                output = " ".join(t for t in text_items if t)
            else:
                logger.warning(
                    "Responses API returned no output_text even without tools. output types: %s",
                    [getattr(item, "type", "?") for item in response.output],
                )
                output = ""
    return str(output)


def _agent_tools_for_chat_completions() -> list[dict[str, Any]]:
    """Convert AGENT_TOOLS (Responses API shape) into Chat Completions tool format.

    Responses API uses a flat ``{type, name, description, parameters}`` per tool,
    while Chat Completions wraps the function spec under a ``function`` key.
    """
    converted: list[dict[str, Any]] = []
    for tool in AGENT_TOOLS:
        if tool.get("type") != "function":
            continue
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {}),
                },
            }
        )
    return converted


async def _run_chat_completions_with_tools(
    client: AsyncOpenAI,
    messages: list[dict[str, Any]],
    config: CopilotConfig,
    tool_executors: ToolExecutors,
    *,
    response_schema: dict[str, Any] | None = None,
    strict_schema: bool = True,
    schema_name: str = "analysis_response",
    on_tool_call: OnToolCallHook = None,
    on_status: OnStatusHook = None,
) -> str:
    """Tool-calling loop using the Chat Completions API.

    Used for providers that expose ``/v1/chat/completions`` but not
    ``/v1/responses`` (e.g. DeepSeek). Mirrors ``_run_responses_api``: sends
    ``tools``, dispatches each ``tool_call`` to the matching executor, feeds
    results back as ``role: "tool"`` messages, and re-asks the model until it
    stops calling tools (or ``MAX_TOOL_ROUNDS`` is hit). Returns the final
    assistant text content.

    When ``response_schema`` is provided, the request includes
    ``response_format: json_schema`` so the final assistant text is structured.
    Providers that don't accept that field (or that don't support ``strict``)
    fall back gracefully.
    """
    chat_tools = _agent_tools_for_chat_completions()

    extra_body: dict[str, Any] = {}
    if config.model.provider == "ollama":
        options: dict[str, Any] = {}
        if config.model.keep_alive:
            extra_body["keep_alive"] = config.model.keep_alive
        if config.model.num_ctx is not None:
            options["num_ctx"] = config.model.num_ctx
        if config.model.top_k is not None:
            options["top_k"] = config.model.top_k
        if options:
            extra_body["options"] = options

    base_kwargs: dict[str, Any] = {
        "model": config.model.name,
        "max_tokens": config.model.max_output_tokens,
        "tools": chat_tools,
        "tool_choice": "auto",
    }
    if response_schema is not None:
        base_kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": strict_schema,
                "schema": response_schema,
            },
        }
    if extra_body:
        base_kwargs["extra_body"] = extra_body
    if config.model.temperature is not None:
        base_kwargs["temperature"] = config.model.temperature
    if config.model.top_p is not None:
        base_kwargs["top_p"] = config.model.top_p
    if config.model.reasoning_effort:
        base_kwargs["reasoning_effort"] = config.model.reasoning_effort

    msgs: list[dict[str, Any]] = list(messages)

    async def _create(**kw: Any) -> Any:
        try:
            return await client.chat.completions.create(**kw)
        except BadRequestError as exc:
            msg = str(exc)
            if "temperature" in msg and "temperature" in kw:
                logger.info("Model does not support temperature, retrying without it")
                kw.pop("temperature")
                return await client.chat.completions.create(**kw)
            if "top_p" in msg and "top_p" in kw:
                logger.info("Model does not support top_p, retrying without it")
                kw.pop("top_p")
                return await client.chat.completions.create(**kw)
            if "reasoning_effort" in msg and "reasoning_effort" in kw:
                logger.info("Model does not support reasoning_effort, retrying without it")
                kw.pop("reasoning_effort")
                return await client.chat.completions.create(**kw)
            if (
                "response_format" in msg or "json_schema" in msg or "strict" in msg
            ) and "response_format" in kw:
                logger.info(
                    "Model does not support response_format json_schema (or strict), "
                    "retrying with type=json_object"
                )
                kw["response_format"] = {"type": "json_object"}
                try:
                    return await client.chat.completions.create(**kw)
                except BadRequestError:
                    logger.info("Model also rejects json_object, dropping response_format")
                    kw.pop("response_format", None)
                    return await client.chat.completions.create(**kw)
            raise

    if on_status:
        await on_status("thinking")

    last_message: Any = None
    for _round in range(MAX_TOOL_ROUNDS):
        response = await _create(messages=msgs, **base_kwargs)
        choice = response.choices[0]
        msg = choice.message
        last_message = msg
        tool_calls = getattr(msg, "tool_calls", None) or []

        if not tool_calls:
            break

        logger.info(
            "Chat-completions tool round %d/%d: %d call(s) — %s",
            _round + 1,
            MAX_TOOL_ROUNDS,
            len(tool_calls),
            ", ".join(tc.function.name for tc in tool_calls),
        )

        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": msg.content or None,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ],
        }
        # DeepSeek thinking mode: when an assistant turn contained tool_calls,
        # the model's reasoning_content from that turn MUST be sent back on the
        # next request — otherwise the server rejects the conversation.
        reasoning_content = getattr(msg, "reasoning_content", None)
        if isinstance(reasoning_content, str) and reasoning_content:
            assistant_msg["reasoning_content"] = reasoning_content
        msgs.append(assistant_msg)

        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                args = {}

            logger.info("Tool call: %s(%s)", tc.function.name, json.dumps(args, ensure_ascii=False))
            if on_tool_call:
                await on_tool_call(tc.function.name, args)

            executor = tool_executors.get(tc.function.name)
            if executor is None:
                tool_result: Any = {"error": f"Unknown tool: {tc.function.name}"}
            else:
                try:
                    tool_result = executor(args)
                except KeyError as e:
                    logger.warning("Tool %s missing required argument: %s", tc.function.name, e)
                    tool_result = {
                        "error": (
                            f"Missing required argument: {e}. "
                            "Please provide all required parameters."
                        )
                    }
                except Exception as e:
                    logger.warning("Tool %s execution failed: %s", tc.function.name, e)
                    tool_result = {"error": str(e)}

            output_str = json.dumps(_sanitize_nan(tool_result), default=str, ensure_ascii=False)
            if len(output_str) > MAX_TOOL_RESULT_CHARS:
                logger.warning(
                    "Tool %s result truncated: %d -> %d chars",
                    tc.function.name,
                    len(output_str),
                    MAX_TOOL_RESULT_CHARS,
                )
                output_str = (
                    output_str[:MAX_TOOL_RESULT_CHARS] + "... [TRUNCATED - result too large]"
                )

            msgs.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": output_str,
                }
            )

        if on_status:
            await on_status("thinking")
    else:
        # MAX_TOOL_ROUNDS exhausted. Force a final non-tool response.
        logger.warning(
            "Chat-completions tool rounds exhausted (%d). Retrying without tools.",
            MAX_TOOL_ROUNDS,
        )
        final_kwargs = {k: v for k, v in base_kwargs.items() if k not in ("tools", "tool_choice")}
        response = await _create(messages=msgs, **final_kwargs)
        last_message = response.choices[0].message

    content = (getattr(last_message, "content", None) or "") if last_message is not None else ""
    if content:
        return content
    for field in ("reasoning", "reasoning_content", "thinking"):
        value = getattr(last_message, field, None) if last_message is not None else None
        if isinstance(value, str) and value.strip():
            logger.warning(
                "Chat-completions with tools returned empty content; using message.%s fallback",
                field,
            )
            return value
    return ""


async def _run_chat_completions(
    client: AsyncOpenAI,
    messages: list[dict[str, Any]],
    config: CopilotConfig,
) -> str:
    """Call Chat Completions API (Ollama fallback) and return the content."""
    extra_body: dict[str, Any] = {}
    if config.model.provider == "ollama":
        options: dict[str, Any] = {}
        if config.model.keep_alive:
            extra_body["keep_alive"] = config.model.keep_alive
        if config.model.num_ctx is not None:
            options["num_ctx"] = config.model.num_ctx
        if config.model.top_k is not None:
            options["top_k"] = config.model.top_k
        if options:
            extra_body["options"] = options

    kwargs: dict[str, Any] = {
        "model": config.model.name,
        "messages": messages,
        "max_tokens": config.model.max_output_tokens,
        "response_format": {"type": "json_object"},
    }
    if extra_body:
        kwargs["extra_body"] = extra_body
    if config.model.temperature is not None:
        kwargs["temperature"] = config.model.temperature
    if config.model.top_p is not None:
        kwargs["top_p"] = config.model.top_p
    if config.model.reasoning_effort:
        kwargs["reasoning_effort"] = config.model.reasoning_effort
    try:
        response = await client.chat.completions.create(**kwargs)
    except BadRequestError as exc:
        if "temperature" in str(exc) and "temperature" in kwargs:
            logger.info("Model does not support temperature, retrying without it")
            kwargs.pop("temperature")
            response = await client.chat.completions.create(**kwargs)
        elif "top_p" in str(exc) and "top_p" in kwargs:
            logger.info("Model does not support top_p, retrying without it")
            kwargs.pop("top_p")
            response = await client.chat.completions.create(**kwargs)
        elif "reasoning_effort" in str(exc) and "reasoning_effort" in kwargs:
            logger.info("Model does not support reasoning_effort, retrying without it")
            kwargs.pop("reasoning_effort")
            response = await client.chat.completions.create(**kwargs)
        else:
            raise
    choice = response.choices[0]
    message = choice.message
    content = message.content or ""
    reasoning_chars = 0
    for field in ("reasoning", "reasoning_content", "thinking"):
        value = getattr(message, field, None)
        if isinstance(value, str):
            reasoning_chars += len(value)
    usage = getattr(response, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
    completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
    total_tokens = getattr(usage, "total_tokens", None) if usage else None
    finish_reason = getattr(choice, "finish_reason", None)
    logger.info(
        "Chat completion finished: provider=%s model=%s finish_reason=%s "
        "content_chars=%d reasoning_chars=%d prompt_tokens=%s completion_tokens=%s total_tokens=%s",
        config.model.provider,
        config.model.name,
        finish_reason,
        len(content),
        reasoning_chars,
        prompt_tokens,
        completion_tokens,
        total_tokens,
    )
    if finish_reason == "length":
        logger.warning(
            "Chat completion hit token limit before stop: provider=%s model=%s "
            "content_chars=%d reasoning_chars=%d completion_tokens=%s max_tokens=%s",
            config.model.provider,
            config.model.name,
            len(content),
            reasoning_chars,
            completion_tokens,
            config.model.max_output_tokens,
        )
    if content:
        return content

    # Some local thinking models served through Ollama's OpenAI-compatible
    # endpoint place generated text in non-standard reasoning fields while
    # leaving content empty. Treat that as raw model output so the triage parser
    # can extract a compact review block or mark it as a format error.
    for field in ("reasoning", "reasoning_content", "thinking"):
        value = getattr(message, field, None)
        if isinstance(value, str) and value.strip():
            logger.warning(
                "Chat completion returned empty content; using message.%s fallback", field
            )
            return value
    logger.warning(
        "Chat completion returned no usable text: provider=%s model=%s finish_reason=%s",
        config.model.provider,
        config.model.name,
        finish_reason,
    )
    return ""


async def run_analysis(
    context: TaskAnalysisContext,
    user_message: str,
    config: CopilotConfig,
    image_base64: str | None = None,
    expected_images: list[tuple[str, str]] | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    tool_executors: ToolExecutors | None = None,
    on_tool_call: OnToolCallHook = None,
    on_status: OnStatusHook = None,
) -> dict[str, Any]:
    """Run the analysis using OpenAI-compatible API.

    For OpenAI, uses the Responses API with structured JSON Schema output
    and the blocks response format (mixed text/chart content).
    For Ollama, falls back to Chat Completions API since Ollama does not
    support the Responses API.

    Parameters
    ----------
    context : TaskAnalysisContext
        Structured context including task knowledge, qubit params, and results.
    user_message : str
        The user's question about the calibration result.
    config : CopilotConfig
        Copilot configuration (model provider, temperature, etc.).
    image_base64 : str | None
        Optional base64-encoded result figure.
    expected_images : list[tuple[str, str]] | None
        Optional list of (base64_data, alt_text) for expected reference images.
    conversation_history : list[dict[str, str]] | None
        Previous conversation messages.
    tool_executors : ToolExecutors | None
        Optional dict mapping tool names to executor callables.
        Only used for OpenAI Responses API path; ignored for Ollama.

    Returns
    -------
    dict[str, Any]
        Blocks-format response: {"blocks": [...], "assessment": ...}

    """
    # Allow a dedicated analysis model (e.g. calibration-specialized LLM) to
    # override the general chat model for task result analysis. Keep a
    # reference to the original general model so we can use it for post-
    # processing (e.g. translation to the user's response language).
    general_model = config.model
    analysis_model = config.analysis_model
    if analysis_model is None and config.analysis_models:
        analysis_model = config.analysis_models[0]
    if analysis_model is not None:
        config = config.model_copy(update={"model": analysis_model})
    client = _build_client(config)
    provider = config.model.provider

    has_expected = bool(expected_images)
    has_experiment = bool(image_base64)

    if provider == "ollama":
        # Ollama only supports Chat Completions API (no tool support)
        system_prompt = _build_system_prompt(
            context,
            config=config,
            include_response_format=True,
            has_expected_images=has_expected,
            has_experiment_image=has_experiment,
        )
        messages = _build_messages(
            system_prompt, user_message, image_base64, conversation_history, expected_images
        )
        content = await _run_chat_completions(client, messages, config)
        # Ollama still uses legacy schema; convert to blocks
        response = _parse_response(content)
        # Calibration-specialized models often ignore language instructions and
        # reply in English. If the user expects a different language, translate
        # the free-form fields via the general (frontier) model.
        target_lang = (config.response_language or "en").lower()
        should_translate = (
            target_lang != "en"
            and general_model.provider != "ollama"
            and general_model is not config.model
        )
        if should_translate:
            response = await _translate_analysis_response(response, target_lang, general_model)
        return _legacy_to_blocks(response, config)
    else:
        # OpenAI: use Responses API with blocks schema (strict: False for flexible chart objects)
        system_prompt = (
            _build_system_prompt(
                context,
                config=config,
                has_expected_images=has_expected,
                has_experiment_image=has_experiment,
            )
            + CHART_SYSTEM_PROMPT
        )
        input_items = _build_input(
            user_message, image_base64, conversation_history, expected_images
        )

        # Wrap tools: data store + chart collection + rate limiting
        if tool_executors:
            wrapped_executors: ToolExecutors | None = None
            data_store: dict[str, Any] = {}
            rate_limited = _wrap_rate_limited_executors(tool_executors)
            wrapped_executors, collected_charts = _wrap_tool_executors(rate_limited, data_store)
        else:
            wrapped_executors, collected_charts = None, []

        content = await _run_responses_api(
            client,
            system_prompt,
            input_items,
            config,
            wrapped_executors,
            response_schema=BLOCKS_RESPONSE_SCHEMA,
            strict_schema=False,
            on_tool_call=on_tool_call,
            on_status=on_status,
        )
        return _inject_collected_charts(_parse_blocks_response(content, config), collected_charts)


def blocks_to_markdown(result: dict[str, Any]) -> str:
    """Convert a blocks-format AI response to markdown for issue replies."""
    blocks = result.get("blocks", [])
    if not blocks:
        logger.warning("blocks_to_markdown: no blocks in result keys=%s", list(result.keys()))

    parts: list[str] = []
    for block in blocks:
        block_type = block.get("type")
        content = block.get("content")
        # Use `is not None` — empty string "" is falsy but still valid content
        if block_type == "text" and content is not None and content != "":
            parts.append(str(content))
        elif block_type == "chart" and block.get("chart"):
            chart = block["chart"]
            title = chart.get("layout", {}).get("title", "Chart")
            parts.append(
                f"**{title}**\n```json\n{json.dumps(chart, indent=2, ensure_ascii=False)}\n```"
            )

    if not parts:
        logger.warning("blocks_to_markdown: all blocks produced empty output, result=%s", result)

    return "\n\n".join(parts)


CHAT_SYSTEM_PROMPT = """\
You are an expert in superconducting qubit calibration.
You analyze calibration results for fixed-frequency transmon qubits
on a square-lattice chip with fixed couplers.

Tool results are returned in JSON format.
Some tools (get_chip_parameter_timeseries, get_chip_summary) store full data
server-side and return only a summary with a `data_key` field.
In execute_python_analysis, access stored data via data["<data_key>"]
(e.g., data["t1"]). Do NOT pass context_data manually.

Your role:
- Answer questions about qubit calibration data and parameters
- Retrieve and visualize data using available tools
- Perform statistical analysis and computations on calibration data
- Provide actionable insights and recommendations
- Explain findings clearly to experimentalists

You have access to tools that can fetch data from the calibration database.

⚠️ CRITICAL RULE: When analysing a parameter across multiple qubits or the whole chip (e.g. "T1の時系列", "show me T1 trends", "analyse qubit_frequency for all qubits"), you MUST call get_chip_parameter_timeseries ONCE. NEVER call get_parameter_timeseries in a loop for each qubit — that is slow and wasteful. get_parameter_timeseries is ONLY for deep-diving into a single specific qubit the user explicitly asked about.

### Single-qubit tools (use only for ONE specific qubit)
- get_qubit_params: Get current calibrated parameters for a qubit (chip_id, qid required)
- get_latest_task_result: Get the latest result for a specific calibration task
- get_task_history: Get recent historical results for a task
- get_parameter_timeseries: Get time series for a parameter on a SINGLE qubit only. For multiple/all qubits, use get_chip_parameter_timeseries instead.
- list_available_parameters: List all output parameter names recorded in the database. Optionally filter by qid.

### Chip-wide & cross-qubit tools
- get_chip_summary: Get all qubits on a chip with statistics (mean/median/std/min/max)
- compare_qubits: Compare parameters across multiple qubits side by side
- get_chip_topology: Get chip topology (grid size, qubit positions, coupling connections)
- get_chip_parameter_timeseries: Get per-qubit timeseries + summary for a parameter across ALL qubits in one call. Returns timeseries arrays (for charts), latest values, trends, and chip-wide stats. Use this instead of calling get_parameter_timeseries for each qubit.
- generate_chip_heatmap: Generate a chip-wide heatmap for a qubit metric (e.g. T1, frequency). Returns a Plotly chart.

### Coupling & execution tools
- get_coupling_params: Get coupling resonator parameters by coupling_id or qubit_id
- get_execution_history: Get recent execution runs with status and timing
- search_task_results: Search task results with flexible filters (task_name, qid, status, execution_id)

### Provenance & notes
- get_calibration_notes: Get calibration notes/annotations for a chip
- get_parameter_lineage: Get version history of a parameter across executions
- get_provenance_lineage_graph: Get the provenance DAG showing how a parameter was derived (ancestor entities and activities). Use for root cause diagnosis.

### Analysis
- execute_python_analysis: Execute Python code for data analysis and visualization (numpy, pandas, scipy available)

IMPORTANT: When calling tools, you need chip_id and often qid.
- The default chip_id is provided in the context below. Always use it unless the user specifies a different chip.
- For qid: users may refer to qubits as "Q16", "qubit 16", or just "16". Normalize to the plain number format (e.g. "16") when calling tools.
- For parameter names in get_parameter_timeseries, use snake_case names (e.g. qubit_frequency, t1, t2_echo, x90_gate_fidelity). If unsure, call list_available_parameters first to discover valid names.
- For chip-wide queries (get_chip_summary, get_execution_history, get_chip_topology), only chip_id is required.
- For get_provenance_lineage_graph, entity_id format is "parameter_name:qid:execution_id:task_id". First call get_parameter_lineage to obtain entity_id values, then use them with get_provenance_lineage_graph.

When the user asks about parameters or trends, ALWAYS use the tools to retrieve real data.
When showing data trends, create charts using the blocks response format.

## Using execute_python_analysis

For complex analysis (correlations, statistics, distributions, fitting), use execute_python_analysis:
1. First, retrieve data using get_chip_parameter_timeseries, get_chip_summary, etc.
   These "stored" tools save full data server-side and return a summary with a `data_key`.
2. Then call execute_python_analysis with only "code" — NO context_data needed.
   Stored data is automatically available as `data["<data_key>"]`.
   For example, after calling get_chip_parameter_timeseries for "t1":
   - `data["t1"]["timeseries"]` contains the full timeseries list
   - `data["t1"]["qubits"]` contains per-qubit stats
3. Available libraries: numpy, pandas, scipy, scipy.stats, plotly (graph_objects, express, subplots), math, statistics, json, datetime, collections, io.
4. In the code, set a 'result' variable:
   ```python
   result = {
       "output": "Text description of analysis results",
       "chart": {  # optional Plotly chart
           "data": [{"x": [...], "y": [...], "type": "scatter", ...}],
           "layout": {"title": "...", "xaxis": {"title": "..."}, ...}
       }
   }
   ```
5. Include the execution result in your blocks response: text from output, chart from chart field.

## Root cause diagnosis with provenance

When the user asks why a calibration result is bad, or wants to find the cause of a poor parameter value,
use the provenance lineage graph to trace upstream dependencies:

1. Identify the problematic parameter and get its version history with get_parameter_lineage (parameter_name, qid, chip_id).
2. From the results, pick the entity_id of the bad version (or the latest version).
3. Call get_provenance_lineage_graph with that entity_id and chip_id to get the ancestor graph.
4. In the returned graph, look at ancestor entity nodes (depth > 0, node_type=entity):
   - Check if any upstream parameter has degraded (compare value to typical/expected ranges).
   - Check the task (activity node) that produced the bad result and its input parameters.
   - If an upstream parameter's version has a latest_version field, that means a newer version exists and the input may have been stale.
5. Report which upstream parameter and calibration task may be the root cause, and recommend re-running the relevant upstream calibration.

Example workflow:
- User: "Why is X90 gate fidelity bad for Q0?"
- Step 1: get_parameter_lineage("x90_gate_fidelity", "0", chip_id) → find entity_id of the latest version
- Step 2: get_provenance_lineage_graph(entity_id, chip_id) → get ancestor graph
- Step 3: Inspect ancestor entities (e.g., qubit_frequency, pi_amplitude) for degradation
- Step 4: Conclude "The qubit_frequency input to CreateX90 was degraded (v3, 4.85 GHz → expected ~5.0 GHz). Re-run CheckQubitFrequency first."

## Presenting analysis results

When you analyse data, ALWAYS provide evidence with your conclusions:

1. **Summary table**: After calling get_chip_parameter_timeseries or get_chip_summary, present a markdown table of per-qubit values so the user can verify your conclusions. Example:
   | Qubit | Latest | Trend | Min | Max |
   |-------|--------|-------|-----|-----|
   | 0     | 45.2   | stable | 43.1 | 46.0 |
   | 1     | 38.7   | decreasing | 37.5 | 42.3 |

2. **Charts**: Use execute_python_analysis to create Plotly charts for visual evidence — bar charts comparing qubits, scatter plots for trends, histograms for distributions, etc. Stored tool data is automatically available as data["<data_key>"].

3. **Statistics**: Always report chip-wide statistics (mean, median, stdev, min, max) returned by tools. Highlight outliers (values > 2 stdev from mean).

Provide tables first for quick reference, then charts for visual insight, then your interpretation.
"""


def _build_chat_system_prompt(
    *,
    config: CopilotConfig | None = None,
    chip_id: str | None = None,
    qid: str | None = None,
    qubit_params: dict[str, Any] | None = None,
) -> str:
    """Build system prompt for the generic chat endpoint."""
    parts = [CHAT_SYSTEM_PROMPT, _build_language_instruction(config)]

    if config and config.scoring:
        threshold_lines = ["\n## Scoring thresholds (deployment-specific)"]
        for metric, thresh in config.scoring.items():
            range_parts = []
            if thresh.bad is not None:
                range_parts.append(f"bad < {thresh.bad} {thresh.unit}")
            range_parts.append(f"good > {thresh.good} {thresh.unit}")
            range_parts.append(f"excellent > {thresh.excellent} {thresh.unit}")
            if not thresh.higher_is_better:
                range_parts.append("(lower is better)")
            threshold_lines.append(f"- {metric}: {', '.join(range_parts)}")
        parts.append("\n".join(threshold_lines))

    if chip_id:
        if qid:
            lines = [f"\n## Current context: Qubit {qid} (Chip: {chip_id})"]
        else:
            lines = [f"\n## Current context: Chip {chip_id}"]
            lines.append(
                "No specific qubit selected. Use this chip_id as default when calling tools."
            )
        if qubit_params:
            lines.append("\n### Current qubit parameters")
            for key, val in qubit_params.items():
                if isinstance(val, dict) and "value" in val:
                    lines.append(f"- {key}: {val['value']} {val.get('unit', '')}")
                else:
                    lines.append(f"- {key}: {val}")
        parts.append("\n".join(lines))

    parts.append(CHART_SYSTEM_PROMPT)
    return "\n\n".join(parts)


async def run_chat(
    user_message: str,
    config: CopilotConfig,
    chip_id: str | None = None,
    qid: str | None = None,
    qubit_params: dict[str, Any] | None = None,
    image_base64: str | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    tool_executors: ToolExecutors | None = None,
    on_tool_call: OnToolCallHook = None,
    on_status: OnStatusHook = None,
) -> dict[str, Any]:
    """Run a generic chat using OpenAI-compatible API.

    Lightweight version of run_analysis that does not require TaskAnalysisContext.
    Optionally includes chip_id/qid context if provided.

    Returns
    -------
    dict[str, Any]
        Blocks-format response: {"blocks": [...], "assessment": ...}

    """
    client = _build_client(config)

    system_prompt = _build_chat_system_prompt(
        config=config,
        chip_id=chip_id,
        qid=qid,
        qubit_params=qubit_params,
    )

    if tool_executors:
        data_store: dict[str, Any] = {}
        rate_limited = _wrap_rate_limited_executors(tool_executors)
        wrapped_executors, collected_charts = _wrap_tool_executors(rate_limited, data_store)
    else:
        wrapped_executors, collected_charts = None, []

    # OpenAI and Ollama 0.13.3+ expose /v1/responses (tool-call, json_schema,
    # reasoning-item preservation). Providers that only ship /v1/chat/completions
    # (e.g. DeepSeek) opt in via `api_style: chat_completions` in copilot.yaml.
    if config.model.api_style == "chat_completions":
        # ds4-server and similar providers expose tools and chat completions
        # but reject `response_format: json_schema` / strict mode. Reinforce
        # the BLOCKS contract in the system prompt so the model still emits a
        # parseable JSON object on its own.
        chat_system_prompt = system_prompt + CHAT_COMPLETIONS_STRICT_EMULATION
        messages = _build_messages(
            chat_system_prompt,
            user_message,
            image_base64,
            conversation_history,
        )
        if wrapped_executors:
            content = await _run_chat_completions_with_tools(
                client,
                messages,
                config,
                wrapped_executors,
                response_schema=BLOCKS_RESPONSE_SCHEMA,
                strict_schema=True,
                schema_name="blocks_response",
                on_tool_call=on_tool_call,
                on_status=on_status,
            )
        else:
            content = await _run_chat_completions(client, messages, config)
        parsed = _parse_blocks_response(content, config)
        if not _has_real_blocks(parsed):
            logger.warning(
                "chat_completions: BLOCKS parse fell back to single text block "
                "(model emitted free text). content_chars=%d",
                len(content or ""),
            )
        return _inject_collected_charts(parsed, collected_charts)

    input_items = _build_input(user_message, image_base64, conversation_history)
    content = await _run_responses_api(
        client,
        system_prompt,
        input_items,
        config,
        wrapped_executors,
        response_schema=BLOCKS_RESPONSE_SCHEMA,
        strict_schema=False,
        on_tool_call=on_tool_call,
        on_status=on_status,
    )
    return _inject_collected_charts(_parse_blocks_response(content, config), collected_charts)
