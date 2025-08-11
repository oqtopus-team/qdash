"""
Strands-based Slack agent implementation for QDash quantum calibration system.
This is the full migration to Strands Agents SDK.
"""

import asyncio
import logging
import os
import statistics
from datetime import datetime
from typing import Any

import pendulum
from pydantic import BaseModel
from qdash.config import get_settings
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.initialize import initialize
from qdash.slack_agent.config_manager import get_current_model_config
from qdash.slack_agent.error_handlers import (
    handle_critical_error,
    log_slack_event,
    metrics,
    setup_periodic_health_check,
    with_error_handling,
)
from qdash.slack_agent.models import SlackEvent
from slack_bolt.adapter.socket_mode.aiohttp import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp

# Import Strands Agents SDK
try:
    from strands import Agent, tool
    from strands.models.openai import OpenAIModel

    STRANDS_AVAILABLE = True
    print("✅ Strands Agents SDK imported successfully")
except ImportError as e:
    print(f"❌ Strands Agents SDK not available: {e}")
    STRANDS_AVAILABLE = False

    # Fallback tool decorator
    def tool(func):
        """Fallback tool decorator when Strands is not available."""
        func._is_tool = True
        func._tool_name = func.__name__
        return func


# Initialize database
initialize()

settings = get_settings()

# Enhanced logging configuration

log_dir = os.path.dirname(os.path.abspath(__file__))
log_file = os.path.join(log_dir, "log", "agent.log")

# Ensure log directory exists
os.makedirs(os.path.dirname(log_file), exist_ok=True)

logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(log_file, encoding="utf-8")],
)
logger = logging.getLogger(__name__)

# Slack App initialization with error handling
try:
    app = AsyncApp(token=settings.slack_bot_token)
    logger.info("✅ Slack app initialized successfully")
except Exception as e:
    logger.error(f"❌ Failed to initialize Slack app: {e}")
    raise


@tool
@with_error_handling
async def get_current_time() -> str:
    """Get current time in JST timezone."""
    from datetime import timedelta, timezone

    jst = timezone(timedelta(hours=9))
    return datetime.now(tz=jst).strftime("%Y-%m-%d %H:%M:%S JST")


@tool
@with_error_handling
async def calculate(expression: str) -> float:
    """Calculate mathematical expression safely."""
    try:
        import ast
        import operator

        # Validate expression safety
        if any(dangerous in expression for dangerous in ["import", "__", "exec", "eval"]):
            raise ValueError("Potentially dangerous expression detected")

        # Parse and evaluate safely using a controlled evaluator
        def safe_eval(node):
            if isinstance(node, ast.Expression):
                return safe_eval(node.body)
            elif isinstance(node, ast.Constant):  # Python 3.8+
                return node.value
            elif isinstance(node, ast.Num):  # For older Python versions
                return node.n
            elif isinstance(node, ast.BinOp):
                ops = {
                    ast.Add: operator.add,
                    ast.Sub: operator.sub,
                    ast.Mult: operator.mul,
                    ast.Div: operator.truediv,
                    ast.Pow: operator.pow,
                    ast.Mod: operator.mod,
                    ast.FloorDiv: operator.floordiv,
                }
                if type(node.op) not in ops:
                    raise ValueError(f"Unsupported operation: {type(node.op)}")
                return ops[type(node.op)](safe_eval(node.left), safe_eval(node.right))
            elif isinstance(node, ast.UnaryOp):
                ops = {ast.UAdd: operator.pos, ast.USub: operator.neg}
                if type(node.op) not in ops:
                    raise ValueError(f"Unsupported unary operation: {type(node.op)}")
                return ops[type(node.op)](safe_eval(node.operand))
            else:
                raise ValueError(f"Unsupported node type: {type(node)}")

        node = ast.parse(expression, mode="eval")
        result = safe_eval(node)
        return float(result)

    except Exception as e:
        raise ValueError(f"Calculation error: {e!s}")


@tool
@with_error_handling
async def get_string_length(text: str) -> int:
    """Get string length."""
    if not isinstance(text, str):
        raise ValueError("Input must be a string")
    return len(text)


@tool
@with_error_handling
async def get_current_chip(username: str = "admin") -> str:
    """Get current quantum chip ID for a user."""
    try:
        chip = ChipDocument.get_current_chip(username)
        if chip:
            logger.info(f"Retrieved current chip for user {username}: {chip.chip_id}")
            return str(chip.chip_id)
        logger.warning(f"No current chip found for user {username}")
        return f"No current chip found for user {username}"
    except Exception as e:
        logger.error(f"Database error retrieving current chip for {username}: {e}")
        raise


class ChipParameterInfo(BaseModel):
    """Chip parameter information model."""

    chip_id: str
    username: str
    qubit_count: int
    qubit_parameters: dict[str, dict[str, Any]]
    coupling_parameters: dict[str, dict[str, Any]]
    statistics: dict[str, Any]


@tool
async def get_chip_parameters(
    chip_id: str | None = None,
    username: str = "admin",
    calculate_stats: bool = True,
    within_24hrs: bool = False,
) -> dict[str, Any]:
    """Get quantum chip parameter information including fidelity statistics.

    Args:
        chip_id: Chip ID to get parameters for (if None, uses current chip)
        username: Username to filter by (default: "admin")
        calculate_stats: Whether to calculate statistics like median fidelity
        within_24hrs: Whether to only include parameters from last 24 hours

    Returns:
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
    readout_fidelities = []
    x90_gate_fidelities = []
    x180_gate_fidelities = []

    for qid, qubit_model in chip.qubits.items():
        params = {}
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

                        # Collect fidelity values for statistics
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
    zx90_gate_fidelities = []
    bell_state_fidelities = []

    for coupling_id, coupling_model in chip.couplings.items():
        params = {}
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
                        display_name = coupling_field_map.get(param_name, param_name)
                        value = param_data.get("value")

                        # Validate fidelity values
                        if "fidelity" in display_name and value is not None and value > 1.0:
                            value = None

                        params[display_name] = {
                            "value": value,
                            "unit": param_data.get("unit", ""),
                            "calibrated_at": param_data.get("calibrated_at", ""),
                        }

                        # Collect fidelity values for statistics
                        if isinstance(value, (int, float)) and 0 <= value <= 1:
                            if display_name == "zx90_gate_fidelity":
                                zx90_gate_fidelities.append(value)
                            elif display_name == "bell_state_fidelity":
                                bell_state_fidelities.append(value)
        coupling_params[coupling_id] = params

    # Calculate statistics
    stats = {}
    if calculate_stats:

        def calc_stats(values):
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

        if readout_fidelities:
            stats["readout_fidelity"] = calc_stats(readout_fidelities)
        if x90_gate_fidelities:
            stats["x90_gate_fidelity"] = calc_stats(x90_gate_fidelities)
        if x180_gate_fidelities:
            stats["x180_gate_fidelity"] = calc_stats(x180_gate_fidelities)
        if zx90_gate_fidelities:
            stats["zx90_gate_fidelity"] = calc_stats(zx90_gate_fidelities)
        if bell_state_fidelities:
            stats["bell_state_fidelity"] = calc_stats(bell_state_fidelities)

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

    lines = [
        f"**Chip Parameters for {chip_id}** (User: {username})",
        f"Total Qubits: {qubit_count}",
        "",
    ]

    # Statistics section
    stats = parameters.get("statistics", {})
    if stats:
        lines.append("**Fidelity Statistics:**")

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


@tool
@with_error_handling
async def get_chip_parameters_formatted(
    chip_id: str | None = None,
    username: str = "admin",
    calculate_stats: bool = True,
    within_24hrs: bool = False,
) -> str:
    """Get quantum chip fidelity statistics with Slack-friendly formatting."""
    try:
        logger.info(f"Fetching chip parameters: chip_id={chip_id}, username={username}")
        raw_params = await get_chip_parameters(chip_id, username, calculate_stats, within_24hrs)
        formatted_result = format_chip_parameters_for_slack(raw_params)
        logger.info(f"Successfully formatted chip parameters ({len(formatted_result)} chars)")
        return formatted_result
    except Exception as e:
        logger.error(f"Failed to get formatted chip parameters: {e}")
        raise


@tool
@with_error_handling
async def get_thread_history(channel_id: str, thread_ts: str) -> dict[str, Any]:
    """Get Slack conversation history from a thread."""
    try:
        logger.info(f"Fetching thread history: channel={channel_id}, thread={thread_ts}")
        result = await app.client.conversations_replies(channel=channel_id, ts=thread_ts, limit=50)

        messages = [
            {
                "user": msg.get("user", "unknown"),
                "text": msg.get("text", ""),
                "ts": msg.get("ts", ""),
                "type": msg.get("type", "message"),
            }
            for msg in result.get("messages", [])
        ]

        logger.info(f"Retrieved {len(messages)} messages from thread")
        return {
            "channel_id": channel_id,
            "thread_ts": thread_ts,
            "message_count": len(messages),
            "messages": messages,
        }
    except Exception as e:
        logger.error(f"Slack API error fetching thread history: {e}")
        return {"error": f"Failed to get thread history: {e!s}"}


# Create the Strands agent with QDash tools
def create_strands_agent():
    """Create a Strands agent with QDash quantum tools."""
    model_config = get_current_model_config()

    # System instructions for the agent
    system_prompt = f"""あなたはQDash量子キャリブレーションシステムのSlackアシスタントです。

基本的な対応:
- 日本語で自然に返答してください
- 簡潔で親しみやすい口調で答えてください
- 挨拶には普通に挨拶で返してください

利用可能なツール:
- get_chip_parameters_formatted: チップのフィデリティ統計とパラメータ取得
- get_current_chip: 現在のチップID取得
- get_current_time: 現在時刻取得
- calculate: 数式計算
- get_string_length: 文字列長取得

使用方針:
1. ユーザー名が言及された場合（例："orangekame3の"）、ツールに渡してください
2. フィデリティやチップに関する質問: get_chip_parameters_formatted を使用
3. "最新のchip id"に関する質問: get_current_chip を使用
4. 単純な挨拶や雑談には、ツールを使わず自然に返答してください

Model: {model_config.name}
"""

    # Prepare tools list
    tools = [
        get_current_time,
        calculate,
        get_string_length,
        get_current_chip,
        get_chip_parameters_formatted,
        get_thread_history,
    ]

    if STRANDS_AVAILABLE:
        # Configure model based on provider
        if model_config.provider == "openai":
            # Get API key from settings or environment
            settings = get_settings()
            api_key = getattr(settings, "openai_api_key", None) or model_config.api_key or os.getenv("OPENAI_API_KEY")

            # Create OpenAI model configuration with supported parameters only
            model_params = {
                "temperature": model_config.temperature,
                "max_completion_tokens": model_config.max_completion_tokens,
            }

            # Note: GPT-5 specific parameters (verbosity, reasoning) are not yet supported
            # by the current OpenAI client library. Will be enabled when available.

            model = OpenAIModel(
                client_args={
                    "api_key": api_key,
                    "timeout": 30.0,  # 30 second timeout
                    "max_retries": 3,  # More retries
                },
                model_id=model_config.name,
                params=model_params,
            )

            # Create Strands Agent with proper configuration
            agent = Agent(model=model, system_prompt=system_prompt, tools=tools)
            logger.info(f"✅ Strands Agent initialized with OpenAI model: {model_config.name}")
        else:
            # For other providers, use default Agent (will use environment settings)
            agent = Agent(system_prompt=system_prompt, tools=tools)
            logger.info("✅ Strands Agent initialized with default configuration")
    else:
        # Fallback: Create a simple async wrapper for OpenAI
        logger.warning("⚠️ Strands SDK not available, using fallback implementation")
        from openai import AsyncOpenAI

        class FallbackAgent:
            def __init__(self):
                self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                self.model = model_config.name
                self.system_prompt = system_prompt
                self.tools = {t.__name__: t for t in tools}

            async def invoke_async(self, message: str):
                """Simple async invocation without tool support."""
                try:
                    response = await self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": self.system_prompt},
                            {"role": "user", "content": message},
                        ],
                        temperature=model_config.temperature,
                        max_tokens=model_config.max_tokens,
                    )

                    # Return a simple object with message content
                    class Result:
                        def __init__(self, content):
                            self.message = type("Message", (), {"content": content})()

                    return Result(response.choices[0].message.content)
                except Exception as e:
                    logger.error(f"Fallback agent error: {e}")
                    raise

        agent = FallbackAgent()
        logger.info(f"⚠️ Fallback Agent initialized: {model_config.name}")

    return agent


@app.event("app_mention")
async def handle_mention(event, say, client) -> None:
    """Handle bot mention events using Strands agent."""
    start_time = datetime.now()

    try:
        # Parse event into Pydantic model
        slack_event = SlackEvent(**event)
        clean_message = slack_event.clean_text

        # Log Slack event
        log_slack_event("app_mention", slack_event.channel, slack_event.user, clean_message)

        # Create Strands agent
        agent = create_strands_agent()

        thread_ts = slack_event.thread_ts or slack_event.ts

        await say(text="🤔 Thinking...", thread_ts=thread_ts)

        try:
            # Execute agent with user message directly (no confusing context)
            user_message = clean_message

            # Use invoke_async for Strands Agent
            result = await agent.invoke_async(user_message)

            # Extract the message content from the result (Strands AgentResult format)
            response_text = str(result) if result else "No response generated"

            # Send final result
            await say(text=response_text, thread_ts=thread_ts)

            # Record successful interaction
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            metrics.record_user_interaction(True, duration_ms)

            logger.info(f"✅ Successfully responded to user in {duration_ms:.1f}ms")

        except Exception as e:
            # Handle agent execution errors
            error_msg = handle_critical_error(e, "agent_execution")
            await say(text=error_msg, thread_ts=thread_ts)

            # Record failed interaction
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            metrics.record_user_interaction(False, duration_ms)

    except Exception as e:
        # Handle parsing/setup errors
        logger.error(f"Critical error in handle_mention: {e}")
        thread_ts = event.get("thread_ts", event.get("ts")) if isinstance(event, dict) else None
        error_msg = handle_critical_error(e, "slack_event_handling")
        await say(text=error_msg, thread_ts=thread_ts)

        # Record failed interaction
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        metrics.record_user_interaction(False, duration_ms)


@app.event("message")
async def handle_message_events(body, logger) -> None:
    """Message event handler (acknowledgment only)."""
    logger.debug(body)


async def main() -> None:
    """Start the Strands-based Slack bot."""
    try:
        # Start periodic health check
        health_check_task = asyncio.create_task(setup_periodic_health_check())

        # Start Socket Mode handler
        handler = AsyncSocketModeHandler(app, settings.slack_app_token)

        # Simple startup logging
        model_config = get_current_model_config()
        logger.info("🚀 QDash Strands Slack Agent starting...")
        logger.info(f"  Strands SDK: {STRANDS_AVAILABLE}")
        logger.info(f"  Model: {model_config.name}")
        logger.info(f"  Log Level: {settings.log_level}")

        await handler.start_async()

    except KeyboardInterrupt:
        logger.info("👋 Shutting down...")
        health_check_task.cancel()

    except Exception as e:
        logger.critical(f"Startup failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
