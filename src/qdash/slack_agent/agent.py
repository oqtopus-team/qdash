import asyncio
import json
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class ToolParameter(BaseModel):
    """Tool parameter schema."""

    type: str = "object"
    properties: dict[str, dict[str, Any]]
    required: list[str] = Field(default_factory=list)


class Tool(BaseModel):
    """Tool definition."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="Tool description")
    parameters: ToolParameter | dict[str, Any] = Field(..., description="Parameter schema")
    function: Callable = Field(..., description="Function to execute")

    def get_schema(self) -> dict[str, Any]:
        """Get OpenAI-format schema."""
        params = self.parameters
        if isinstance(params, ToolParameter):
            params = params.model_dump(exclude_none=True)
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": params},
        }


class AgentStep(BaseModel):
    """Agent execution step record."""

    step_number: int = Field(..., ge=1, description="Step number")
    action: str = Field(..., description="Action executed")
    input: Any = Field(..., description="Input data")
    output: Any = Field(..., description="Output data")
    timestamp: datetime = Field(default_factory=datetime.now, description="Execution timestamp")


class Agent:
    """Autonomous AI agent that thinks and acts."""

    def __init__(
        self,
        name: str,
        instructions: str,
        tools: list[Tool],
        model: str = "gpt-4o-mini",
        max_steps: int = 10,
        openai_client: AsyncOpenAI | None = None,
    ) -> None:
        self.name = name
        self.instructions = instructions
        self.tools = {tool.name: tool for tool in tools}
        self.model = model
        self.max_steps = max_steps
        self.client = openai_client or AsyncOpenAI()
        self.conversation_history: list[dict[str, str]] = []
        self.steps: list[AgentStep] = []

    def _get_tools_schema(self) -> list[dict[str, Any]]:
        """Generate OpenAI-format tool schemas."""
        return [tool.get_schema() for tool in self.tools.values()]

    async def _execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Execute a tool."""
        if tool_name not in self.tools:
            raise ValueError(f"Unknown tool: {tool_name}")

        tool = self.tools[tool_name]
        try:
            logger.info(f"🔧 Executing tool: {tool_name} with args: {arguments}")

            # Check if tool function is async
            if asyncio.iscoroutinefunction(tool.function):
                result = await tool.function(**arguments)
            else:
                result = tool.function(**arguments)

            logger.info(f"✅ Tool {tool_name} completed successfully")
            return result
        except Exception as e:
            logger.error(f"❌ Error executing tool {tool_name}: {e}")
            return f"Error: {e!s}"

    async def think(self, user_input: str, progress_callback: Callable | None = None) -> str:
        """Think and act autonomously based on user input."""
        # Check if web search might be useful - but exclude calibration-related queries
        calibration_keywords = [
            "calibration",
            "キャリブレーション",
            "execution",
            "実行",
            "task",
            "タスク",
            "experiment",
            "実験",
            "qubit",
            "quantum",
            "量子ビット",
            "quantum bit",
            "chip",
            "チップ",
            "fidelity",
            "フィデリティ",
            "parameter",
            "パラメータ",
            "statistics",
            "統計",
            "1qubit",
        ]

        is_calibration_query = any(
            keyword.lower() in user_input.lower() for keyword in calibration_keywords
        )

        web_search_keywords = [
            "search",
            "find",
            "news",
            "today",
            "検索",
            "ニュース",
        ]
        might_need_web_search = any(
            keyword.lower() in user_input.lower() for keyword in web_search_keywords
        )

        # Remove "latest", "recent", "最新" from web search keywords since they are common in calibration queries

        # NEVER use web search for calibration-related queries
        if (
            might_need_web_search
            and not is_calibration_query
            and self.model in ["gpt-4.1", "gpt-4.1-mini", "o4-mini"]
        ):
            # Use Responses API with built-in web search for supported models
            try:
                logger.info(f"🌐 Using OpenAI built-in web search for model: {self.model}")
                response = await self.client.responses.create(
                    model=self.model,
                    tools=[{"type": "web_search_preview"}],
                    input=f"{self.instructions}\n\nUser request: {user_input}",
                )
                return response.output_text
            except Exception as e:
                logger.warning(
                    f"❌ OpenAI web search failed, falling back to function calling: {e}"
                )
                # Fall back to function calling approach

        # Original function calling approach
        self.conversation_history = [
            {"role": "system", "content": self.instructions},
            {"role": "user", "content": user_input},
        ]
        self.steps = []

        for step in range(self.max_steps):
            # Thinking process
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=self.conversation_history,
                tools=self._get_tools_schema(),
                tool_choice="auto",
            )

            message = response.choices[0].message

            # Add assistant response to history
            self.conversation_history.append(
                {"role": "assistant", "content": message.content, "tool_calls": message.tool_calls}
            )

            # If no tool calls, finish
            if not message.tool_calls:
                return message.content or "Task completed."

            # Execute tools
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)

                # Execute tool
                result = await self._execute_tool(tool_name, arguments)

                # Record step
                step_record = AgentStep(
                    step_number=step + 1, action=tool_name, input=arguments, output=result
                )
                self.steps.append(step_record)

                # Progress callback
                if progress_callback:
                    await progress_callback(step_record)

                # Add tool result to history
                self.conversation_history.append(
                    {
                        "role": "tool",
                        "content": json.dumps(result, ensure_ascii=False),
                        "tool_call_id": tool_call.id,
                    }
                )

        return "Maximum steps reached. Ending process."

    def get_execution_summary(self) -> str:
        """Get execution summary."""
        if not self.steps:
            return "No steps executed."

        summary = f"## Execution Summary ({len(self.steps)} steps)\n\n"
        for step in self.steps:
            summary += f"**Step {step.step_number}**: {step.action}\n"
            summary += f"- Input: {json.dumps(step.input, ensure_ascii=False, indent=2)}\n"
            summary += f"- Output: {json.dumps(step.output, ensure_ascii=False, indent=2)}\n\n"

        return summary
