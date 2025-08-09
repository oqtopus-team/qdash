import ast
import datetime
import statistics
from typing import Any

import pendulum
from pydantic import BaseModel
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.initialize import initialize
from qdash.slack_agent.agent import Tool, ToolParameter

initialize()  # Ensure database is initialized


# Response models for web search (demo mode)
class SearchResult(BaseModel):
    """Search result."""

    title: str
    snippet: str


class SearchResponse(BaseModel):
    """Search response."""

    query: str
    results: list[SearchResult]


# Tool functions
async def get_current_time() -> str:
    """Get current time."""
    # Use JST (Japan Standard Time) timezone-aware datetime
    jst = datetime.timezone(datetime.timedelta(hours=9))
    return datetime.datetime.now(tz=jst).strftime("%Y-%m-%d %H:%M:%S JST")


async def web_search(query: str) -> dict[str, Any]:
    """Execute web search (demo mode)."""
    import logging

    logger = logging.getLogger(__name__)
    logger.info(f"🔍 Using Demo Mode for query: '{query}'")

    response = SearchResponse(
        query=query,
        results=[
            SearchResult(
                title="[DEMO] Mock search result",
                snippet="This is demo data. Real web search is not configured in this implementation.",
            ),
            SearchResult(
                title="[DEMO] Search placeholder",
                snippet="This bot currently uses demo search results. For real search functionality, consider integrating a web search API.",
            ),
        ],
    )
    return response.model_dump()


async def calculate(expression: str) -> float:
    """Calculate mathematical expression."""
    try:
        # Use ast.literal_eval for safe evaluation of literals
        result = ast.literal_eval(expression)
        return float(result)
    except Exception as e:
        raise ValueError(f"Calculation error: {e!s}")


def get_string_length(text: str) -> int:
    """Get string length."""
    return len(text)


def get_current_chip(username: str = "admin") -> str:
    """Get current chip."""
    chip = ChipDocument.get_current_chip(username)
    if chip:
        return str(chip.chip_id)
    return f"No current chip found for user {username}"


class ChipParameterInfo(BaseModel):
    """Chip parameter information."""

    chip_id: str
    username: str
    qubit_count: int
    qubit_parameters: dict[str, dict[str, Any]]
    coupling_parameters: dict[str, dict[str, Any]]
    statistics: dict[str, Any]


async def get_chip_parameters(
    chip_id: str | None = None,
    username: str = "admin",
    calculate_stats: bool = True,
    within_24hrs: bool = False,
) -> dict[str, Any]:
    """Get chip parameter information using the same logic as chip_report flow.

    Parameters
    ----------
    chip_id : str | None
        Chip ID to get parameters for (if None, uses current chip)
    username : str
        Username to filter by (default: "admin")
    calculate_stats : bool
        Whether to calculate statistics like median fidelity
    within_24hrs : bool
        Whether to only include parameters from last 24 hours

    Returns
    -------
    dict
        Chip parameter information including fidelity data

    """
    # Get current chip if not specified
    if chip_id is None:
        current_chip = ChipDocument.get_current_chip(username)
        if current_chip:
            chip_id = current_chip.chip_id
        else:
            return {"error": f"No current chip found for user {username} and no chip_id specified"}

    # Get chip document
    chip = ChipDocument.find_one({"chip_id": chip_id, "username": username}).run()
    if not chip:
        return {"error": f"Chip {chip_id} not found for user {username}"}

    # Field mapping based on chip_report implementation
    qubit_field_map = {
        "bare_frequency": "qubit_frequency",
        "t1": "t1",
        "t2_echo": "t2_echo",
        "t2_star": "t2_star",
        "average_readout_fidelity": "average_readout_fidelity",
        "x90_gate_fidelity": "x90_gate_fidelity",
        "x180_gate_fidelity": "x180_gate_fidelity",
    }

    coupling_field_map = {
        "static_zz_interaction": "static_zz_interaction",
        "qubit_qubit_coupling_strength": "qubit_qubit_coupling_strength",
        "zx90_gate_fidelity": "zx90_gate_fidelity",
        "bell_state_fidelity": "bell_state_fidelity",
    }

    # Filter by time if requested
    cutoff_time = None
    if within_24hrs:
        cutoff_time = pendulum.now("Asia/Tokyo").subtract(hours=24)

    # Extract qubit parameters
    qubit_params = {}
    # Separate fidelity collections by parameter type
    readout_fidelities = []
    x90_gate_fidelities = []
    x180_gate_fidelities = []

    for qid, qubit_model in chip.qubits.items():
        params = {}
        # Extract key parameters from qubit model data
        if qubit_model.data and isinstance(qubit_model.data, dict):
            for param_name, param_data in qubit_model.data.items():
                if isinstance(param_data, dict) and "value" in param_data:
                    # Check time filter
                    include_param = True
                    if within_24hrs and "calibrated_at" in param_data:
                        try:
                            calibrated_at = pendulum.parse(param_data["calibrated_at"], tz="Asia/Tokyo")
                            include_param = calibrated_at >= cutoff_time
                        except Exception:
                            include_param = False

                    if include_param:
                        # Use friendly field names if available
                        display_name = qubit_field_map.get(param_name, param_name)
                        value = param_data.get("value")

                        # Convert time units (us -> ns) for t1, t2 parameters
                        if display_name.startswith("t") and value is not None:
                            value = value * 1e3  # us -> ns

                        params[display_name] = {
                            "value": value,
                            "unit": param_data.get("unit", ""),
                            "calibrated_at": param_data.get("calibrated_at", ""),
                        }

                        # Collect fidelity values for statistics by type (only valid values)
                        if isinstance(value, (int, float)) and 0 <= value <= 1:
                            if display_name == "average_readout_fidelity":
                                readout_fidelities.append(value)
                            elif display_name == "x90_gate_fidelity":
                                x90_gate_fidelities.append(value)
                            elif display_name == "x180_gate_fidelity":
                                x180_gate_fidelities.append(value)
        qubit_params[qid] = params

    # Extract coupling parameters
    coupling_params = {}
    # Separate coupling fidelity collections by parameter type
    zx90_gate_fidelities = []
    bell_state_fidelities = []

    for coupling_id, coupling_model in chip.couplings.items():
        params = {}
        # Extract key parameters from coupling model data
        if coupling_model.data and isinstance(coupling_model.data, dict):
            for param_name, param_data in coupling_model.data.items():
                if isinstance(param_data, dict) and "value" in param_data:
                    # Check time filter
                    include_param = True
                    if within_24hrs and "calibrated_at" in param_data:
                        try:
                            calibrated_at = pendulum.parse(param_data["calibrated_at"], tz="Asia/Tokyo")
                            include_param = calibrated_at >= cutoff_time
                        except Exception:
                            include_param = False

                    if include_param:
                        # Use friendly field names if available
                        display_name = coupling_field_map.get(param_name, param_name)
                        value = param_data.get("value")

                        # Validate fidelity values (should be between 0 and 1)
                        if "fidelity" in display_name and value is not None and value > 1.0:
                            value = None  # Invalid fidelity value

                        params[display_name] = {
                            "value": value,
                            "unit": param_data.get("unit", ""),
                            "calibrated_at": param_data.get("calibrated_at", ""),
                        }

                        # Collect fidelity values for statistics by type (only valid values)
                        if isinstance(value, (int, float)) and 0 <= value <= 1:
                            if display_name == "zx90_gate_fidelity":
                                zx90_gate_fidelities.append(value)
                            elif display_name == "bell_state_fidelity":
                                bell_state_fidelities.append(value)
        coupling_params[coupling_id] = params

    # Calculate statistics by parameter type
    stats = {}
    if calculate_stats:
        # Helper function for statistics calculation
        def calc_stats(values, name):
            if values:
                return {
                    "count": len(values),
                    "mean": round(statistics.mean(values), 6),
                    "median": round(statistics.median(values), 6),
                    "min": round(min(values), 6),
                    "max": round(max(values), 6),
                    "stdev": round(statistics.stdev(values), 6) if len(values) > 1 else 0,
                }
            return None

        # Qubit fidelity statistics by type
        if readout_fidelities:
            stats["readout_fidelity"] = calc_stats(readout_fidelities, "readout_fidelity")
        if x90_gate_fidelities:
            stats["x90_gate_fidelity"] = calc_stats(x90_gate_fidelities, "x90_gate_fidelity")
        if x180_gate_fidelities:
            stats["x180_gate_fidelity"] = calc_stats(x180_gate_fidelities, "x180_gate_fidelity")

        # Coupling fidelity statistics by type
        if zx90_gate_fidelities:
            stats["zx90_gate_fidelity"] = calc_stats(zx90_gate_fidelities, "zx90_gate_fidelity")
        if bell_state_fidelities:
            stats["bell_state_fidelity"] = calc_stats(bell_state_fidelities, "bell_state_fidelity")

    result = ChipParameterInfo(
        chip_id=chip_id,
        username=username,
        qubit_count=len(chip.qubits),
        qubit_parameters=qubit_params,
        coupling_parameters=coupling_params,
        statistics=stats,
    )

    return result.model_dump()


def format_chip_parameters_for_slack(parameters: dict[str, Any]) -> str:
    """Format chip parameters for readable Slack output."""
    if "error" in parameters:
        return f"Error: {parameters['error']}"

    chip_id = parameters.get("chip_id", "Unknown")
    username = parameters.get("username", "Unknown")
    qubit_count = parameters.get("qubit_count", 0)

    # Header
    lines = [
        f"**Chip Parameters for {chip_id}** (User: {username})",
        f"Total Qubits: {qubit_count}",
        "",
    ]

    # Statistics section
    stats = parameters.get("statistics", {})
    if stats:
        lines.append("**Fidelity Statistics:**")

        # Individual parameter type statistics
        if "readout_fidelity" in stats:
            rf = stats["readout_fidelity"]
            lines.extend(
                [
                    "• **Readout Fidelity:**",
                    f"  - Measurements: {rf['count']}",
                    f"  - Median: **{rf['median']:.1%}** ({rf['median']:.3f})",
                    f"  - Mean: {rf['mean']:.1%} ({rf['mean']:.3f})",
                    f"  - Range: {rf['min']:.1%} - {rf['max']:.1%}",
                    "",
                ]
            )

        if "x90_gate_fidelity" in stats:
            x90f = stats["x90_gate_fidelity"]
            lines.extend(
                [
                    "• **X90 Gate Fidelity:**",
                    f"  - Measurements: {x90f['count']}",
                    f"  - Median: **{x90f['median']:.1%}** ({x90f['median']:.3f})",
                    f"  - Mean: {x90f['mean']:.1%} ({x90f['mean']:.3f})",
                    f"  - Range: {x90f['min']:.1%} - {x90f['max']:.1%}",
                    "",
                ]
            )

        if "x180_gate_fidelity" in stats:
            x180f = stats["x180_gate_fidelity"]
            lines.extend(
                [
                    "• **X180 Gate Fidelity:**",
                    f"  - Measurements: {x180f['count']}",
                    f"  - Median: **{x180f['median']:.1%}** ({x180f['median']:.3f})",
                    f"  - Mean: {x180f['mean']:.1%} ({x180f['mean']:.3f})",
                    f"  - Range: {x180f['min']:.1%} - {x180f['max']:.1%}",
                    "",
                ]
            )

        if "zx90_gate_fidelity" in stats:
            zx90f = stats["zx90_gate_fidelity"]
            lines.extend(
                [
                    "• **ZX90 Gate Fidelity:**",
                    f"  - Measurements: {zx90f['count']}",
                    f"  - Median: **{zx90f['median']:.1%}** ({zx90f['median']:.3f})",
                    f"  - Mean: {zx90f['mean']:.1%} ({zx90f['mean']:.3f})",
                    f"  - Range: {zx90f['min']:.1%} - {zx90f['max']:.1%}",
                    "",
                ]
            )

        if "bell_state_fidelity" in stats:
            bsf = stats["bell_state_fidelity"]
            lines.extend(
                [
                    "• **Bell State Fidelity:**",
                    f"  - Measurements: {bsf['count']}",
                    f"  - Median: **{bsf['median']:.1%}** ({bsf['median']:.3f})",
                    f"  - Mean: {bsf['mean']:.1%} ({bsf['mean']:.3f})",
                    f"  - Range: {bsf['min']:.1%} - {bsf['max']:.1%}",
                    "",
                ]
            )

    else:
        lines.append("No fidelity statistics available")

    # Data availability
    qubit_params = parameters.get("qubit_parameters", {})
    coupling_params = parameters.get("coupling_parameters", {})

    qubits_with_data = sum(1 for params in qubit_params.values() if params)
    couplings_with_data = sum(1 for params in coupling_params.values() if params)

    lines.extend(
        [
            "**Data Availability:**",
            f"• Qubits with calibration data: {qubits_with_data}/{len(qubit_params)}",
            f"• Couplings with calibration data: {couplings_with_data}/{len(coupling_params)}",
        ]
    )

    return "\n".join(lines)


async def get_chip_parameters_formatted(
    chip_id: str | None = None,
    username: str = "admin",
    calculate_stats: bool = True,
    within_24hrs: bool = False,
) -> str:
    """Get chip parameters with Slack-friendly formatting."""
    raw_params = await get_chip_parameters(chip_id, username, calculate_stats, within_24hrs)
    return format_chip_parameters_for_slack(raw_params)


async def get_qubit_details(
    chip_id: str | None = None,
    username: str = "admin",
    parameter_type: str | None = None,
    within_24hrs: bool = False,
) -> str:
    """Get detailed information about individual qubits and their parameters.

    Parameters
    ----------
    chip_id : str | None
        Chip ID to get details for (if None, uses current chip)
    username : str
        Username to filter by (default: "admin")
    parameter_type : str | None
        Specific parameter type to filter by (e.g., "x90_gate_fidelity", "readout_fidelity")
    within_24hrs : bool
        Whether to only include parameters from last 24 hours

    Returns
    -------
    str
        Formatted string with individual qubit details

    """
    # Get current chip if not specified
    if chip_id is None:
        current_chip = ChipDocument.get_current_chip(username)
        if current_chip:
            chip_id = current_chip.chip_id
        else:
            return f"Error: No current chip found for user {username} and no chip_id specified"

    # Get chip document
    chip = ChipDocument.find_one({"chip_id": chip_id, "username": username}).run()
    if not chip:
        return f"Error: Chip {chip_id} not found for user {username}"

    # Field mapping
    qubit_field_map = {
        "bare_frequency": "qubit_frequency",
        "t1": "t1",
        "t2_echo": "t2_echo",
        "t2_star": "t2_star",
        "average_readout_fidelity": "average_readout_fidelity",
        "x90_gate_fidelity": "x90_gate_fidelity",
        "x180_gate_fidelity": "x180_gate_fidelity",
    }

    # Filter by time if requested
    cutoff_time = None
    if within_24hrs:
        cutoff_time = pendulum.now("Asia/Tokyo").subtract(hours=24)

    # Collect qubit details
    qubit_details = []

    for qid, qubit_model in chip.qubits.items():
        if not qubit_model.data:
            continue

        qubit_info = {"qid": qid, "parameters": {}}

        for param_name, param_data in qubit_model.data.items():
            if not isinstance(param_data, dict) or "value" not in param_data:
                continue

            # Check time filter
            include_param = True
            if within_24hrs and "calibrated_at" in param_data:
                try:
                    calibrated_at = pendulum.parse(param_data["calibrated_at"], tz="Asia/Tokyo")
                    include_param = calibrated_at >= cutoff_time
                except Exception:
                    include_param = False

            if not include_param:
                continue

            # Use friendly field names if available
            display_name = qubit_field_map.get(param_name, param_name)
            value = param_data.get("value")

            # Convert time units (us -> ns) for t1, t2 parameters
            if display_name.startswith("t") and value is not None:
                value = value * 1e3  # us -> ns

            qubit_info["parameters"][display_name] = {
                "value": value,
                "unit": param_data.get("unit", ""),
                "calibrated_at": param_data.get("calibrated_at", ""),
            }

        # Filter by parameter type if specified
        if parameter_type:
            if parameter_type in qubit_info["parameters"]:
                qubit_details.append(qubit_info)
        elif qubit_info["parameters"]:  # Include if has any parameters
            qubit_details.append(qubit_info)

    # Format output
    if not qubit_details:
        filter_msg = f" with {parameter_type}" if parameter_type else ""
        return f"No qubits found{filter_msg} for chip {chip_id}"

    # Header
    lines = [f"**Individual Qubit Details for {chip_id}** (User: {username})", ""]

    if parameter_type:
        lines.append(f"**Filtering by parameter: {parameter_type}**")
        lines.append("")

    # Sort qubits by ID for consistent output
    qubit_details.sort(key=lambda x: int(x["qid"]))

    for qubit_info in qubit_details:
        qid = qubit_info["qid"]
        params = qubit_info["parameters"]

        lines.append(f"**Qubit {qid}:**")

        # If filtering by specific parameter, show that first
        if parameter_type and parameter_type in params:
            param_data = params[parameter_type]
            value = param_data["value"]
            unit = param_data["unit"]
            calibrated_at = param_data["calibrated_at"]

            if "fidelity" in parameter_type and isinstance(value, (int, float)):
                lines.append(f"  - **{parameter_type}**: {value:.1%} ({value:.6f}) {unit}")
            else:
                lines.append(f"  - **{parameter_type}**: {value} {unit}")

            if calibrated_at:
                lines.append(f"  - Calibrated: {calibrated_at}")
        else:
            # Show all parameters
            for param_name, param_data in params.items():
                value = param_data["value"]
                unit = param_data["unit"]

                if "fidelity" in param_name and isinstance(value, (int, float)):
                    lines.append(f"  - {param_name}: {value:.1%} ({value:.6f}) {unit}")
                elif param_name in ["t1", "t2_echo", "t2_star"] and isinstance(value, (int, float)):
                    lines.append(f"  - {param_name}: {value:.1f} ns")
                elif param_name == "qubit_frequency" and isinstance(value, (int, float)):
                    lines.append(f"  - {param_name}: {value/1e9:.6f} GHz")
                else:
                    lines.append(f"  - {param_name}: {value} {unit}")

        lines.append("")

    lines.append(f"**Total qubits shown: {len(qubit_details)}**")

    return "\n".join(lines)


# Tool definitions
current_time_tool = Tool(
    name="get_current_time",
    description="Get current date and time",
    parameters=ToolParameter(properties={}, required=[]),
    function=get_current_time,
)

web_search_tool = Tool(
    name="web_search",
    description="Execute web search",
    parameters=ToolParameter(
        properties={"query": {"type": "string", "description": "Search query"}}, required=["query"]
    ),
    function=web_search,
)

calculate_tool = Tool(
    name="calculate",
    description="Calculate mathematical expression",
    parameters=ToolParameter(
        properties={
            "expression": {
                "type": "string",
                "description": "Expression to calculate (e.g. 2+2, 10*5, max(1,2,3))",
            }
        },
        required=["expression"],
    ),
    function=calculate,
)

string_length_tool = Tool(
    name="get_string_length",
    description="Get string length",
    parameters=ToolParameter(
        properties={"text": {"type": "string", "description": "Text to measure"}}, required=["text"]
    ),
    function=get_string_length,
)

curent_chip_id_tool = Tool(
    name="get_current_chip",
    description="Get current chip ID",
    parameters=ToolParameter(
        properties={
            "username": {
                "type": "string",
                "description": "Username to get chip for (default: 'admin')",
            }
        },
        required=[],
    ),
    function=get_current_chip,
)

get_chip_parameters_tool = Tool(
    name="get_chip_parameters",
    description="Get chip parameter information including fidelity statistics using chip_report logic",
    parameters=ToolParameter(
        properties={
            "chip_id": {
                "type": "string",
                "description": "Chip ID to get parameters for (optional, defaults to current chip)",
            },
            "username": {
                "type": "string",
                "description": "Username to filter by (default: 'admin')",
            },
            "calculate_stats": {
                "type": "boolean",
                "description": "Whether to calculate statistics like median fidelity (default: true)",
            },
            "within_24hrs": {
                "type": "boolean",
                "description": "Whether to only include parameters from last 24 hours (default: false)",
            },
        },
        required=[],
    ),
    function=get_chip_parameters,
)

get_chip_parameters_formatted_tool = Tool(
    name="get_chip_parameters_formatted",
    description="Get chip parameter information with Slack-friendly formatting - PRIMARY TOOL for fidelity statistics",
    parameters=ToolParameter(
        properties={
            "chip_id": {
                "type": "string",
                "description": "Chip ID to get parameters for (optional, defaults to current chip)",
            },
            "username": {
                "type": "string",
                "description": "Username to filter by (default: 'admin')",
            },
            "calculate_stats": {
                "type": "boolean",
                "description": "Whether to calculate statistics like median fidelity (default: true)",
            },
            "within_24hrs": {
                "type": "boolean",
                "description": "Whether to only include parameters from last 24 hours (default: false)",
            },
        },
        required=[],
    ),
    function=get_chip_parameters_formatted,
)

get_qubit_details_tool = Tool(
    name="get_qubit_details",
    description="Get detailed information about individual qubits and their specific parameters - Use for detailed qubit info",
    parameters=ToolParameter(
        properties={
            "chip_id": {
                "type": "string",
                "description": "Chip ID to get details for (optional, defaults to current chip)",
            },
            "username": {
                "type": "string",
                "description": "Username to filter by (default: 'admin')",
            },
            "parameter_type": {
                "type": "string",
                "description": "Specific parameter to filter by (e.g., 'x90_gate_fidelity', 'readout_fidelity', 't1', 't2_echo')",
            },
            "within_24hrs": {
                "type": "boolean",
                "description": "Whether to only include parameters from last 24 hours (default: false)",
            },
        },
        required=[],
    ),
    function=get_qubit_details,
)


# Default tool set
DEFAULT_TOOLS = [
    current_time_tool,
    web_search_tool,
    calculate_tool,
    string_length_tool,
    curent_chip_id_tool,
    get_chip_parameters_formatted_tool,
    get_qubit_details_tool,
]
