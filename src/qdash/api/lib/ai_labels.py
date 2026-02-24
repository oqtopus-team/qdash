"""Shared AI tool and status labels for copilot and issue AI features."""

TOOL_LABELS: dict[str, str] = {
    "get_qubit_params": "Fetching qubit parameters",
    "get_latest_task_result": "Fetching latest task result",
    "get_task_history": "Fetching task history",
    "get_parameter_timeseries": "Fetching parameter timeseries",
    "execute_python_analysis": "Executing Python analysis",
    "get_chip_summary": "Fetching chip summary",
    "get_coupling_params": "Fetching coupling parameters",
    "get_execution_history": "Fetching execution history",
    "compare_qubits": "Comparing qubits",
    "get_chip_topology": "Fetching chip topology",
    "search_task_results": "Searching task results",
    "get_calibration_notes": "Fetching calibration notes",
    "get_parameter_lineage": "Fetching parameter lineage",
    "get_provenance_lineage_graph": "Fetching provenance lineage graph",
    "generate_chip_heatmap": "Generating chip heatmap",
    "list_available_parameters": "Listing available parameters",
}

STATUS_LABELS: dict[str, str] = {
    "thinking": "AI is thinking...",
}
