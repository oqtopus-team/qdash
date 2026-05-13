"""Execution helpers for Copilot LLM calls and tool orchestration."""

from __future__ import annotations

import json
import logging
import math
from typing import TYPE_CHECKING, Any, cast

from openai import AsyncOpenAI, BadRequestError

from qdash.common.copilot.agent_runtime.rendering import build_llm_summary
from qdash.common.copilot.agent_runtime.schemas import ANALYSIS_RESPONSE_SCHEMA
from qdash.common.copilot.tooling.schemas import AGENT_TOOLS

if TYPE_CHECKING:
    from qdash.common.copilot.agent_runtime.types import (
        OnStatusHook,
        OnToolCallHook,
        StoredToolKey,
        ToolExecutor,
        ToolExecutors,
    )
    from qdash.common.copilot.config import CopilotConfig
    from qdash.common.copilot.tooling.sandbox import SandboxChartSpec, SandboxResult

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 10
MAX_TOOL_RESULT_CHARS = 30000
_TIMESERIES_CALL_LIMIT = 3
_STORED_TOOLS: dict[str, StoredToolKey] = {
    "get_chip_parameter_timeseries": lambda args: args["parameter_name"],
    "get_chip_summary": lambda _args: "chip_summary",
}


def wrap_tool_executors(
    tool_executors: ToolExecutors,
    data_store: dict[str, Any],
) -> tuple[ToolExecutors, list[SandboxChartSpec | dict[str, Any]]]:
    """Wrap tool executors to handle data store and chart collection."""
    collected_charts: list[SandboxChartSpec | dict[str, Any]] = []
    wrapped = dict(tool_executors)

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
                    return build_llm_summary(result, key)
                return result

            wrapped[tool_name] = stored_wrapper

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

    def python_wrapper(args: dict[str, Any]) -> SandboxResult | dict[str, Any]:
        from qdash.common.copilot.tooling.sandbox import execute_python_analysis

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


def wrap_rate_limited_executors(tool_executors: ToolExecutors) -> ToolExecutors:
    """Wrap per-qubit tools with a call-count limiter."""
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


def sanitize_nan(obj: Any) -> Any:
    """Recursively replace NaN/Inf float values with None for valid JSON."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_nan(v) for v in obj]
    return obj


def inject_collected_charts(
    result: dict[str, Any],
    collected_charts: list[SandboxChartSpec | dict[str, Any]],
) -> dict[str, Any]:
    """Append tool-generated charts to the blocks response."""
    if not collected_charts:
        return result
    blocks = result.get("blocks", [])
    for chart in collected_charts:
        blocks.append({"type": "chart", "content": None, "chart": sanitize_nan(chart)})
    result["blocks"] = blocks
    return result


async def run_responses_api(
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
    """Call OpenAI Responses API and return the output text."""
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

    if tool_executors:
        for round_index in range(MAX_TOOL_ROUNDS):
            function_calls = [item for item in response.output if item.type == "function_call"]
            if not function_calls:
                break

            logger.info(
                "Tool round %d/%d: %d call(s) — %s",
                round_index + 1,
                MAX_TOOL_ROUNDS,
                len(function_calls),
                ", ".join(fc.name for fc in function_calls),
            )
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
                            "error": f"Missing required argument: {e}. Please provide all required parameters."
                        }
                    except Exception as e:
                        logger.warning("Tool %s execution failed: %s", fc.name, e)
                        tool_result = {"error": str(e)}

                output_str = json.dumps(sanitize_nan(tool_result), default=str, ensure_ascii=False)
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
    if output is None:
        final_input = list(kwargs["input"])
        for item in response.output:
            dumped = item.model_dump()
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
            output = " ".join(t for t in text_items if t) if text_items else ""
    return str(output)


def agent_tools_for_chat_completions() -> list[dict[str, Any]]:
    """Convert Responses API tools into Chat Completions tool format."""
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


async def run_chat_completions_with_tools(
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
    """Tool-calling loop using the Chat Completions API."""
    chat_tools = agent_tools_for_chat_completions()
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
                kw.pop("temperature")
                return await client.chat.completions.create(**kw)
            if "top_p" in msg and "top_p" in kw:
                kw.pop("top_p")
                return await client.chat.completions.create(**kw)
            if "reasoning_effort" in msg and "reasoning_effort" in kw:
                kw.pop("reasoning_effort")
                return await client.chat.completions.create(**kw)
            if (
                "response_format" in msg or "json_schema" in msg or "strict" in msg
            ) and "response_format" in kw:
                kw["response_format"] = {"type": "json_object"}
                try:
                    return await client.chat.completions.create(**kw)
                except BadRequestError:
                    kw.pop("response_format", None)
                    return await client.chat.completions.create(**kw)
            raise

    if on_status:
        await on_status("thinking")

    last_message: Any = None
    for _ in range(MAX_TOOL_ROUNDS):
        response = await _create(messages=msgs, **base_kwargs)
        choice = response.choices[0]
        msg = choice.message
        last_message = msg
        tool_calls = getattr(msg, "tool_calls", None) or []
        if not tool_calls:
            break

        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": msg.content or None,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in tool_calls
            ],
        }
        reasoning_content = getattr(msg, "reasoning_content", None)
        if isinstance(reasoning_content, str) and reasoning_content:
            assistant_msg["reasoning_content"] = reasoning_content
        msgs.append(assistant_msg)

        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                args = {}
            if on_tool_call:
                await on_tool_call(tc.function.name, args)

            executor = tool_executors.get(tc.function.name)
            if executor is None:
                tool_result: Any = {"error": f"Unknown tool: {tc.function.name}"}
            else:
                try:
                    tool_result = executor(args)
                except KeyError as e:
                    tool_result = {
                        "error": f"Missing required argument: {e}. Please provide all required parameters."
                    }
                except Exception as e:
                    tool_result = {"error": str(e)}

            output_str = json.dumps(sanitize_nan(tool_result), default=str, ensure_ascii=False)
            if len(output_str) > MAX_TOOL_RESULT_CHARS:
                output_str = (
                    output_str[:MAX_TOOL_RESULT_CHARS] + "... [TRUNCATED - result too large]"
                )
            msgs.append({"role": "tool", "tool_call_id": tc.id, "content": output_str})

        if on_status:
            await on_status("thinking")
    else:
        final_kwargs = {k: v for k, v in base_kwargs.items() if k not in ("tools", "tool_choice")}
        response = await _create(messages=msgs, **final_kwargs)
        last_message = response.choices[0].message

    content = (getattr(last_message, "content", None) or "") if last_message is not None else ""
    if content:
        return content
    for field in ("reasoning", "reasoning_content", "thinking"):
        value = getattr(last_message, field, None) if last_message is not None else None
        if isinstance(value, str) and value.strip():
            return value
    return ""


async def run_chat_completions(
    client: AsyncOpenAI,
    messages: list[dict[str, Any]],
    config: CopilotConfig,
) -> str:
    """Call Chat Completions API and return the content."""
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
            kwargs.pop("temperature")
            response = await client.chat.completions.create(**kwargs)
        elif "top_p" in str(exc) and "top_p" in kwargs:
            kwargs.pop("top_p")
            response = await client.chat.completions.create(**kwargs)
        elif "reasoning_effort" in str(exc) and "reasoning_effort" in kwargs:
            kwargs.pop("reasoning_effort")
            response = await client.chat.completions.create(**kwargs)
        else:
            raise
    choice = response.choices[0]
    message = choice.message
    content = message.content or ""
    if content:
        return content
    for field in ("reasoning", "reasoning_content", "thinking"):
        value = getattr(message, field, None)
        if isinstance(value, str) and value.strip():
            return value
    return ""
