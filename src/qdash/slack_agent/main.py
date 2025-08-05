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
        agent_instructions = f"""You are an advanced AI assistant operating on Slack.
Please think autonomously and act appropriately using the provided tools in response to user questions and requests.

Context:
- Current channel: {slack_event.channel}
- Thread timestamp: {slack_event.thread_ts or slack_event.ts}
- You can access conversation history using get_thread_history tool

Available Tools and Limitations:
- get_current_time: Gets current date/time
- calculate: Performs mathematical calculations
- get_string_length: Measures text length
- get_thread_history: Retrieves Slack conversation history
- web_search: Uses demo mode (for real search, integrate web search API or use compatible OpenAI models)
- get_current_chip: Retrieves current chip ID (if available)

Follow these guidelines:
1. Accurately understand user intent
2. Use multiple tools in combination as needed
3. Think and act step by step
4. Be honest about what you don't know and tool limitations
5. Provide helpful and polite responses
6. If user asks about previous messages or conversation history, use get_thread_history tool
7. For web searches, use web_search tool (requires Google API configuration for real results)
8. Get current chip using get_current_chip tool
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

        # Send execution summary (for debugging)
        if agent.steps:
            summary = agent.get_execution_summary()
            await say(text=f"```\n{summary}\n```", thread_ts=thread_ts)

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
