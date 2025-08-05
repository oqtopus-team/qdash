import asyncio
import logging

from agent import Agent
from openai import AsyncOpenAI
from qdash.config import get_settings
from qdash.slack_agent.models import SlackEvent
from qdash.slack_agent.tools import DEFAULT_TOOLS
from slack_bolt.adapter.socket_mode.aiohttp import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp
from slack_tools import SlackTools

settings = get_settings()
# Logging setup
logging.basicConfig(level=getattr(logging, settings.log_level))
logger = logging.getLogger(__name__)

# Slack App initialization
app = AsyncApp(token=settings.slack_bot_token)

# OpenAI client initialization
openai_client = AsyncOpenAI(api_key=settings.openai_api_key)


@app.event("app_mention")
async def handle_mention(event, say, client) -> None:
    """Handle bot mention events."""
    try:
        # Parse event into Pydantic model
        slack_event = SlackEvent(**event)

        # Get clean message
        clean_message = slack_event.clean_text

        logger.info(f"Received message: {clean_message}")

        # Agent initialization
        agent_instructions = f"""You are an advanced AI assistant for QDash quantum calibration system operating on Slack.
You MUST use the provided tools to access actual quantum chip data from the QDash system.

Context:
- Current channel: {slack_event.channel}
- Thread timestamp: {slack_event.thread_ts or slack_event.ts}
- You have ACCESS to QDash quantum chip database through tools
- You can access conversation history using get_thread_history tool

CRITICAL: You are connected to a QDash system with real quantum chip data. Always use tools to get actual data.

IMPORTANT Username Extraction Examples:
- "orangekame3の最新のchip idを教えて" → Use get_current_chip(username="orangekame3")
- "adminのキャリブレーション結果" → Use investigate_calibration(username="admin")
- "user123のexecution履歴" → Use investigate_calibration(username="user123")

IMPORTANT Tool Usage Examples:
- "orangekame3のchip 64Qv1の1qubit のfidelityの情報" → Use get_chip_parameters_formatted(chip_id="64Qv1", username="orangekame3") for statistics
- "x90 gate fidelityが測定できている量子ビットの詳細" → Use get_qubit_details(parameter_type="x90_gate_fidelity") for individual qubit info
- "1qubitのfidelityの統計を教えて" → Use get_chip_parameters_formatted() for statistics
- "qubit 5のパラメータ詳細" → Use get_qubit_details() to get specific qubit information
- "readout fidelityを持つ量子ビット一覧" → Use get_qubit_details(parameter_type="average_readout_fidelity")

Available Tools for QDash System:
- get_chip_parameters_formatted: ⭐ PRIMARY TOOL for fidelity statistics and chip parameter summaries (chip_id, username, calculate_stats)
- get_qubit_details: ⭐ Get detailed info about individual qubits and their parameters (chip_id, username, parameter_type)
- get_current_chip: Retrieves current chip ID for a user (pass username parameter, e.g. username='orangekame3')
- get_current_time: Gets current date/time
- calculate: Performs mathematical calculations
- get_string_length: Measures text length
- get_thread_history: Retrieves Slack conversation history
- web_search: ⚠️ DO NOT USE for quantum/chip related queries - only for general web information

Follow these guidelines:
1. Accurately understand user intent
2. When user mentions a specific username (e.g., "orangekame3の", "user123の"), ALWAYS pass that as the username parameter to tools
3. CRITICAL: For ANY query about fidelity, chip parameters, or statistics, ALWAYS use get_chip_parameters_formatted tool first
4. For queries about calibration execution history, use investigate_calibration tool
5. When asked about "最新のchip id" or "current chip", use get_current_chip tool with the appropriate username
6. Use multiple tools in combination as needed
7. Think and act step by step
8. Be honest about what you don't know and tool limitations
9. Provide helpful and polite responses
10. If user asks about previous messages or conversation history, use get_thread_history tool
11. For general web searches (NOT calibration/experiment related), use web_search tool
12. IMPORTANT: Always extract username from user query and pass it to tools that accept username parameter

MANDATORY Tool Selection Guidelines:
- "fidelity statistics" (フィデリティ統計) → MUST use get_chip_parameters_formatted
- "individual qubit details" (個別量子ビット詳細) → MUST use get_qubit_details
- "which qubits have X parameter" → MUST use get_qubit_details(parameter_type="X")
- "qubit X詳細", "量子ビットの情報" → MUST use get_qubit_details
- "x90 gate fidelityが測定できている量子ビット" → MUST use get_qubit_details(parameter_type="x90_gate_fidelity")
- "statistics" (統計) → get_chip_parameters_formatted
- "current chip", "chip id" → get_current_chip

ABSOLUTE RULES:
1. NEVER use web_search for quantum chip, fidelity, or calibration related queries
2. NEVER provide general explanations when specific chip data is requested
3. ALWAYS use get_chip_parameters_formatted for fidelity questions - it returns pre-formatted text ready for Slack
4. When get_chip_parameters_formatted returns formatted text, output it DIRECTLY without additional interpretation
5. You have direct access to QDash database - use it!

CRITICAL: The get_chip_parameters_formatted tool returns beautifully formatted text with emojis and proper structure. Simply return this text directly to the user without modification.
"""

        # Create Slack tools with client access
        slack_tools = SlackTools(client)
        all_tools = DEFAULT_TOOLS + slack_tools.get_tools()

        agent = Agent(
            name="Slack AI Assistant",
            instructions=agent_instructions,
            tools=all_tools,
            model=settings.openai_model,
            max_steps=settings.agent_max_steps,
            openai_client=openai_client,
        )

        # Progress callback to report to Slack
        async def progress_callback(step) -> None:
            progress_text = f"🔄 Step {step.step_number}: Executing {step.action}..."
            await say(text=progress_text, thread_ts=slack_event.thread_ts or slack_event.ts)

        # Execute agent
        thread_ts = slack_event.thread_ts or slack_event.ts

        await say(text="🤔 Thinking...", thread_ts=thread_ts)

        result = await agent.think(clean_message, progress_callback)

        # Send final result
        await say(text=result, thread_ts=thread_ts)

    except Exception as e:
        logger.error(f"Error: {e!s}")
        # Fallback for unparseable events
        thread_ts = event.get("thread_ts", event.get("ts")) if isinstance(event, dict) else None
        await say(text=f"Sorry, an error occurred: {e!s}", thread_ts=thread_ts)


@app.event("message")
async def handle_message_events(body, logger) -> None:
    """Message event handler (acknowledgment only)."""
    logger.debug(body)


async def main() -> None:
    """Start the Slack bot."""
    try:
        # Start Socket Mode handler
        handler = AsyncSocketModeHandler(app, settings.slack_app_token)
        logger.info("Slack bot is running...")
        await handler.start_async()
    except Exception as e:
        logger.error(f"Failed to start bot: {e!s}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
