"""LLM-facing tool schema definitions for Copilot function calling."""

from __future__ import annotations

from typing import Any

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
