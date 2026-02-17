"""OpenAI-based agent for calibration task analysis.

Uses the openai SDK directly to avoid pydantic-ai dependency conflicts.
Supports OpenAI Responses API (default) with Chat Completions API fallback for Ollama.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from openai import AsyncOpenAI, BadRequestError
from qdash.api.lib.copilot_analysis import AnalysisResponse, TaskAnalysisContext

if TYPE_CHECKING:
    from qdash.api.lib.copilot_config import CopilotConfig

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_BASE = """\
You are an expert in superconducting qubit calibration.
You analyze calibration results for fixed-frequency transmon qubits
on a square-lattice chip with fixed couplers.

Your role:
- Interpret experimental results (graphs, parameters, metrics)
- Diagnose potential issues based on the data
- Provide actionable recommendations
- Explain findings clearly to experimentalists

Always ground your analysis in the provided experimental context.
When discussing results, reference specific parameter values and thresholds.

You have access to tools that can fetch data from the calibration database.
When the user asks about parameters or results from other experiments,
use the available tools to retrieve the data rather than saying it's unavailable.
The current qubit context (chip_id, qid) is provided in the system prompt below.
"""

MAX_TOOL_ROUNDS = 5

ToolExecutors = dict[str, Any]
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
            "Get time series data for a specific output parameter across all task results. "
            "This queries by parameter name (e.g. 'qubit_frequency', 't1', 't2_echo', "
            "'x90_gate_fidelity', 'resonator_frequency') rather than by task name. "
            "Use this when the user asks about trends or history of a specific parameter. "
            "Returns a list of {value, unit, calibrated_at, execution_id, task_id} entries "
            "ordered by time."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "parameter_name": {
                    "type": "string",
                    "description": (
                        "The output parameter name to query "
                        "(e.g. 'qubit_frequency', 't1', 't2_echo', 'x90_gate_fidelity')"
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
            "Available libraries: numpy, pandas, scipy, scipy.stats, math, statistics, json, "
            "datetime, collections. "
            "Pass data from previous tool calls via context_data (accessible as 'data' in code). "
            "Set a 'result' variable as a dict with 'output' (text) and optionally "
            "'chart' (Plotly spec with 'data' and 'layout' keys)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": (
                        "Python code to execute. Use 'data' to access context_data. "
                        "Set result = {'output': '...', 'chart': {'data': [...], 'layout': {...}}} "
                        "for structured output."
                    ),
                },
                "context_data": {
                    "type": "object",
                    "description": "Data from previous tool calls to make available as 'data' variable in the code.",
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
            "Get a summary of all qubits on a chip with per-qubit parameters and "
            "computed statistics (mean, median, std, min, max) for numeric parameters. "
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
    "required": ["blocks"],
    "additionalProperties": False,
}

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

You MUST respond with a valid JSON object matching this schema:
{
  "summary": "One-line result summary",
  "assessment": "good or warning or bad",
  "explanation": "Detailed analysis and interpretation",
  "potential_issues": ["issue1", "issue2"],
  "recommendations": ["action1", "action2"]
}
"""


def _build_client(config: CopilotConfig) -> AsyncOpenAI:
    """Build an AsyncOpenAI client based on provider configuration."""
    provider = config.model.provider

    if provider == "ollama":
        base_url = os.environ.get("OLLAMA_URL", "http://localhost:11434") + "/v1"
        return AsyncOpenAI(base_url=base_url, api_key="ollama")
    elif provider == "openai":
        return AsyncOpenAI()  # uses OPENAI_API_KEY env var
    elif provider == "anthropic":
        raise ValueError(
            "Anthropic provider is not supported with openai SDK. Use openai or ollama."
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


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

    if thinking_lang != response_lang:
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

    """
    parts = [SYSTEM_PROMPT_BASE, _build_language_instruction(config)]

    # Task knowledge
    parts.append(context.task_knowledge_prompt)

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
) -> list[dict[str, Any]]:
    """Build the input items list for the OpenAI Responses API.

    Unlike Chat Completions, system messages are passed via the
    ``instructions`` parameter, so only user/assistant messages
    are included here.
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

    # Build the current user message
    content_parts: list[dict[str, Any]] = [
        {"type": "input_text", "text": user_message},
    ]
    if image_base64:
        content_parts.append(
            {
                "type": "input_image",
                "image_url": f"data:image/png;base64,{image_base64}",
            }
        )
    items.append({"role": "user", "content": content_parts})

    return items


def _build_messages(
    system_prompt: str,
    user_message: str,
    image_base64: str | None,
    conversation_history: list[dict[str, str]] | None,
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
    if image_base64:
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_message},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                    },
                ],
            }
        )
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


def _parse_response(content: str) -> AnalysisResponse:
    """Parse LLM response into AnalysisResponse, handling JSON and plain text."""
    text = _strip_code_fences(content)

    try:
        data = json.loads(text)
        return AnalysisResponse(**data)
    except (json.JSONDecodeError, ValueError):
        # If JSON parsing fails, treat the entire response as explanation
        return AnalysisResponse(
            summary="Analysis complete",
            assessment="warning",
            explanation=content,
            potential_issues=[],
            recommendations=[],
        )


def _legacy_to_blocks(response: AnalysisResponse) -> dict[str, Any]:
    """Convert a legacy AnalysisResponse to blocks format."""
    blocks: list[dict[str, Any]] = []

    # Summary + explanation as text block
    parts: list[str] = []
    if response.summary:
        parts.append(response.summary)
    if response.explanation:
        parts.append(response.explanation)
    if response.potential_issues:
        parts.append("\n**Potential Issues:**")
        for issue in response.potential_issues:
            parts.append(f"- {issue}")
    if response.recommendations:
        parts.append("\n**Recommendations:**")
        for rec in response.recommendations:
            parts.append(f"- {rec}")

    blocks.append({"type": "text", "content": "\n\n".join(parts), "chart": None})

    return {
        "blocks": blocks,
        "assessment": response.assessment,
    }


def _parse_blocks_response(content: str) -> dict[str, Any]:
    """Parse LLM response into blocks format dict, with fallback to legacy."""
    text = _strip_code_fences(content)

    try:
        data = json.loads(text)
        if "blocks" in data and isinstance(data["blocks"], list):
            return dict(data)
        # Legacy format returned — convert
        response = AnalysisResponse(**data)
        return _legacy_to_blocks(response)
    except (json.JSONDecodeError, ValueError):
        # Plain text fallback
        return {
            "blocks": [{"type": "text", "content": content, "chart": None}],
            "assessment": None,
        }


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

            # Build new input: previous input + ALL model output items.
            # All items (reasoning, function_call, message, etc.) must be
            # preserved — omitting reasoning items causes a 400 error.
            new_input = list(kwargs["input"])
            for item in response.output:
                new_input.append(item.model_dump())

            for fc in function_calls:
                if on_tool_call:
                    try:
                        args = json.loads(fc.arguments)
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                    await on_tool_call(fc.name, args)

                executor = tool_executors.get(fc.name)
                if executor is None:
                    tool_result = {"error": f"Unknown tool: {fc.name}"}
                else:
                    try:
                        args = json.loads(fc.arguments)
                        tool_result = executor(args)
                    except Exception as e:
                        logger.warning("Tool %s execution failed: %s", fc.name, e)
                        tool_result = {"error": str(e)}

                logger.info("Tool call: %s -> %s", fc.name, type(tool_result).__name__)
                new_input.append(
                    {
                        "type": "function_call_output",
                        "call_id": fc.call_id,
                        "output": json.dumps(tool_result, default=str, ensure_ascii=False),
                    }
                )

            kwargs["input"] = new_input
            if on_status:
                await on_status("thinking")
            response = await _create(**kwargs)

    return str(response.output_text)


async def _run_chat_completions(
    client: AsyncOpenAI,
    messages: list[dict[str, Any]],
    config: CopilotConfig,
) -> str:
    """Call Chat Completions API (Ollama fallback) and return the content."""
    kwargs: dict[str, Any] = {
        "model": config.model.name,
        "messages": messages,
        "max_tokens": config.model.max_output_tokens,
        "response_format": {"type": "json_object"},
    }
    if config.model.temperature is not None:
        kwargs["temperature"] = config.model.temperature
    try:
        response = await client.chat.completions.create(**kwargs)
    except BadRequestError as exc:
        if "temperature" in str(exc) and "temperature" in kwargs:
            logger.info("Model does not support temperature, retrying without it")
            kwargs.pop("temperature")
            response = await client.chat.completions.create(**kwargs)
        else:
            raise
    return response.choices[0].message.content or ""


async def run_analysis(
    context: TaskAnalysisContext,
    user_message: str,
    config: CopilotConfig,
    image_base64: str | None = None,
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
    client = _build_client(config)
    provider = config.model.provider

    if provider == "ollama":
        # Ollama only supports Chat Completions API (no tool support)
        system_prompt = _build_system_prompt(context, config=config, include_response_format=True)
        messages = _build_messages(system_prompt, user_message, image_base64, conversation_history)
        content = await _run_chat_completions(client, messages, config)
        # Ollama still uses legacy schema; convert to blocks
        response = _parse_response(content)
        return _legacy_to_blocks(response)
    else:
        # OpenAI: use Responses API with blocks schema (strict: False for flexible chart objects)
        system_prompt = _build_system_prompt(context, config=config) + CHART_SYSTEM_PROMPT
        input_items = _build_input(user_message, image_base64, conversation_history)
        content = await _run_responses_api(
            client,
            system_prompt,
            input_items,
            config,
            tool_executors,
            response_schema=BLOCKS_RESPONSE_SCHEMA,
            strict_schema=False,
            on_tool_call=on_tool_call,
            on_status=on_status,
        )
        return _parse_blocks_response(content)


CHAT_SYSTEM_PROMPT = """\
You are an expert in superconducting qubit calibration.
You analyze calibration results for fixed-frequency transmon qubits
on a square-lattice chip with fixed couplers.

Your role:
- Answer questions about qubit calibration data and parameters
- Retrieve and visualize data using available tools
- Perform statistical analysis and computations on calibration data
- Provide actionable insights and recommendations
- Explain findings clearly to experimentalists

You have access to tools that can fetch data from the calibration database:

### Single-qubit tools
- get_qubit_params: Get current calibrated parameters for a qubit (chip_id, qid required)
- get_latest_task_result: Get the latest result for a specific calibration task
- get_task_history: Get recent historical results for a task
- get_parameter_timeseries: Get time series data for a parameter (ideal for trend charts)

### Chip-wide & cross-qubit tools
- get_chip_summary: Get all qubits on a chip with statistics (mean/median/std/min/max)
- compare_qubits: Compare parameters across multiple qubits side by side
- get_chip_topology: Get chip topology (grid size, qubit positions, coupling connections)

### Coupling & execution tools
- get_coupling_params: Get coupling resonator parameters by coupling_id or qubit_id
- get_execution_history: Get recent execution runs with status and timing
- search_task_results: Search task results with flexible filters (task_name, qid, status, execution_id)

### Provenance & notes
- get_calibration_notes: Get calibration notes/annotations for a chip
- get_parameter_lineage: Get version history of a parameter across executions

### Analysis
- execute_python_analysis: Execute Python code for data analysis and visualization (numpy, pandas, scipy available)

IMPORTANT: When calling tools, you need chip_id and often qid.
- The default chip_id is provided in the context below. Always use it unless the user specifies a different chip.
- For qid: users may refer to qubits as "Q16", "qubit 16", or just "16". Normalize to the plain number format (e.g. "16") when calling tools.
- For parameter names in get_parameter_timeseries, use snake_case names like: qubit_frequency, t1, t2_echo, x90_gate_fidelity, resonator_frequency, etc.
- For chip-wide queries (get_chip_summary, get_execution_history, get_chip_topology), only chip_id is required.

When the user asks about parameters or trends, ALWAYS use the tools to retrieve real data.
When showing data trends, create charts using the blocks response format.

## Using execute_python_analysis

For complex analysis (correlations, statistics, distributions, fitting), use execute_python_analysis:
1. First, retrieve data using get_qubit_params, get_parameter_timeseries, etc.
2. Then call execute_python_analysis with:
   - "code": Python code that uses 'data' variable to access context_data
   - "context_data": Pass the retrieved data as a dict
3. Available libraries: numpy, pandas, scipy, scipy.stats, math, statistics, json, datetime, collections
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
    provider = config.model.provider

    system_prompt = _build_chat_system_prompt(
        config=config,
        chip_id=chip_id,
        qid=qid,
        qubit_params=qubit_params,
    )

    if provider == "ollama":
        messages = _build_messages(
            system_prompt + RESPONSE_FORMAT_INSTRUCTION,
            user_message,
            image_base64,
            conversation_history,
        )
        content = await _run_chat_completions(client, messages, config)
        response = _parse_response(content)
        return _legacy_to_blocks(response)
    else:
        input_items = _build_input(user_message, image_base64, conversation_history)
        content = await _run_responses_api(
            client,
            system_prompt,
            input_items,
            config,
            tool_executors,
            response_schema=BLOCKS_RESPONSE_SCHEMA,
            strict_schema=False,
            on_tool_call=on_tool_call,
            on_status=on_status,
        )
        return _parse_blocks_response(content)
