"""Execution helpers for Copilot LLM calls and tool orchestration."""

from __future__ import annotations

import json
import logging
import math
from typing import TYPE_CHECKING, Any, cast

from qdash.copilot.agent_runtime.client import litellm_completion, litellm_responses
from qdash.copilot.agent_runtime.rendering import build_llm_summary
from qdash.copilot.agent_runtime.schemas import ANALYSIS_RESPONSE_SCHEMA
from qdash.copilot.tooling.schemas import AGENT_TOOLS

if TYPE_CHECKING:
    from qdash.copilot.agent_runtime.types import (
        OnStatusHook,
        OnToolCallHook,
        StoredToolKey,
        ToolExecutor,
        ToolExecutors,
    )
    from qdash.copilot.config import CopilotConfig
    from qdash.copilot.tooling.sandbox import SandboxChartSpec, SandboxResult

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 10
OLLAMA_MAX_TOOL_ROUNDS = 16
MAX_IDENTICAL_TOOL_CALLS = 3
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
        from qdash.copilot.tooling.sandbox import execute_python_analysis

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


def build_tool_call_signature(name: str, args: dict[str, Any]) -> str:
    """Build a stable signature for repeated tool-call detection."""
    try:
        normalized_args = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
    except TypeError:
        normalized_args = str(args)
    return f"{name}:{normalized_args}"


def build_tool_loop_finalization_prompt(reason: str) -> str:
    """Instruct the model to stop calling tools and answer with current evidence."""
    return (
        "Tool execution was stopped before completion. "
        f"Reason: {reason} "
        "Do not call any more tools. "
        "Using only the tool results and conversation context already available, "
        "produce the best possible final answer in the required JSON format. "
        "If evidence is incomplete, say that briefly and avoid inventing missing data."
    )


def build_responses_finalization_item(reason: str) -> dict[str, Any]:
    """Create a Responses API input item that forces finalization without tools."""
    return {
        "role": "user",
        "content": [{"type": "input_text", "text": build_tool_loop_finalization_prompt(reason)}],
    }


def build_chat_finalization_message(reason: str) -> dict[str, Any]:
    """Create a Chat Completions message that forces finalization without tools."""
    return {"role": "user", "content": build_tool_loop_finalization_prompt(reason)}


def get_max_tool_rounds(config: CopilotConfig) -> int:
    """Return the provider-specific tool-call budget."""
    if config.model.provider == "ollama":
        return OLLAMA_MAX_TOOL_ROUNDS
    return MAX_TOOL_ROUNDS


def should_send_reasoning_effort(config: CopilotConfig) -> bool:
    """Return whether reasoning_effort should be forwarded to LiteLLM."""
    reasoning_effort = config.model.reasoning_effort
    if not reasoning_effort:
        return False
    return config.model.provider == "ollama" or reasoning_effort.lower() != "none"


def build_provider_response_schema(schema: dict[str, Any], config: CopilotConfig) -> dict[str, Any]:
    """Return a provider-compatible copy of a structured-output JSON schema."""
    if config.model.provider.lower() == "bedrock":
        return cast("dict[str, Any]", _bedrock_compatible_schema(schema))
    return schema


def _bedrock_compatible_schema(value: Any) -> Any:
    if isinstance(value, list):
        return [_bedrock_compatible_schema(item) for item in value]
    if not isinstance(value, dict):
        return value

    converted = {key: _bedrock_compatible_schema(item) for key, item in value.items()}
    schema_type = converted.get("type")
    if isinstance(schema_type, list) and "null" in schema_type:
        non_null_types = [item for item in schema_type if item != "null"]
        if len(non_null_types) == 1:
            converted["type"] = non_null_types[0]
            enum_values = converted.get("enum")
            if isinstance(enum_values, list):
                converted["enum"] = [item for item in enum_values if item is not None]
    properties = converted.get("properties", {})
    if "blocks" in properties:
        properties["blocks"]["items"]["properties"].update(
            {
                "type": {"type": "string", "enum": ["text"]},
                "content": {"type": "string"},
                "chart": {"type": "null"},
            }
        )
    return converted


def _is_unsupported_param(exc: Exception, name: str) -> bool:
    message = str(exc).lower()
    return name.lower() in message and (
        "unsupported" in message or "not support" in message or "not supported" in message
    )


def _item_get(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _item_type(item: Any) -> str | None:
    value = _item_get(item, "type")
    return value if isinstance(value, str) else None


def _item_dump(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    if hasattr(item, "model_dump"):
        return item.model_dump()
    return {}


def _response_output(response: Any) -> list[Any]:
    value = _item_get(response, "output")
    return value if isinstance(value, list) else []


def _response_output_text(response: Any) -> str | None:
    value = _item_get(response, "output_text")
    return value if isinstance(value, str) else None


def _completion_choices(response: Any) -> list[Any]:
    value = _item_get(response, "choices")
    return value if isinstance(value, list) else []


def _completion_message(response: Any) -> Any:
    choices = _completion_choices(response)
    if not choices:
        return None
    return _item_get(choices[0], "message")


def _message_content(message: Any) -> str:
    value = _item_get(message, "content") if message is not None else None
    return value if isinstance(value, str) else ""


def _message_tool_calls(message: Any) -> list[Any]:
    value = _item_get(message, "tool_calls") if message is not None else None
    return value if isinstance(value, list) else []


def _tool_call_function(tool_call: Any) -> Any:
    return _item_get(tool_call, "function", {})


def _message_reasoning_text(message: Any) -> str:
    for field in ("reasoning", "reasoning_content", "thinking"):
        value = _item_get(message, field) if message is not None else None
        if isinstance(value, str) and value.strip():
            return value
    return ""


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


async def run_litellm_responses(
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
    """Call LiteLLM Responses API and return the output text."""
    schema = build_provider_response_schema(response_schema or ANALYSIS_RESPONSE_SCHEMA, config)
    text_format: dict[str, Any] = {
        "format": {
            "type": "json_schema",
            "name": "analysis_response",
            "strict": strict_schema,
            "schema": schema,
        }
    }
    kwargs: dict[str, Any] = {
        "instructions": system_prompt,
        "input": input_items,
        "max_output_tokens": config.model.max_output_tokens,
    }
    if tool_executors:
        kwargs["tools"] = AGENT_TOOLS
    else:
        kwargs["text"] = text_format
    if config.model.temperature is not None:
        kwargs["temperature"] = config.model.temperature

    # Bedrock keeps tool definitions during finalization; the prompt prevents more calls.
    keep_tools_for_finalization = config.model.provider.lower() == "bedrock"

    async def _create(**kw: Any) -> Any:
        try:
            return await litellm_responses(config, **kw)
        except Exception as exc:
            if _is_unsupported_param(exc, "temperature") and "temperature" in kw:
                logger.info("Model does not support temperature, retrying without it")
                kw.pop("temperature")
                return await _create(**kw)
            raise

    if on_status:
        await on_status("thinking")
    response = await _create(**kwargs)

    if tool_executors:
        max_tool_rounds = get_max_tool_rounds(config)
        tool_call_counts: dict[str, int] = {}
        stop_reason: str | None = None
        for round_index in range(max_tool_rounds):
            function_calls = [
                item for item in _response_output(response) if _item_type(item) == "function_call"
            ]
            if not function_calls:
                if tool_call_counts:
                    final_input = list(kwargs["input"])
                    for item in _response_output(response):
                        dumped = _item_dump(item)
                        if dumped:
                            final_input.append(dumped)
                    if keep_tools_for_finalization:
                        final_input.append(build_responses_finalization_item("Tool calls completed."))
                    # Keep tools only for Bedrock; other providers finalize without tools.
                    final_kwargs = (
                        dict(kwargs)
                        if keep_tools_for_finalization
                        else {k: v for k, v in kwargs.items() if k != "tools"}
                    )
                    final_kwargs["input"] = final_input
                    final_kwargs["text"] = text_format
                    if on_status:
                        await on_status("thinking")
                    response = await _create(**final_kwargs)
                break

            parsed_calls: list[tuple[Any, dict[str, Any]]] = []
            repeated_signature: str | None = None
            for fc in function_calls:
                try:
                    args = json.loads(_item_get(fc, "arguments") or "{}")
                except (json.JSONDecodeError, TypeError):
                    args = {}
                name = str(_item_get(fc, "name") or "")
                signature = build_tool_call_signature(name, args)
                tool_call_counts[signature] = tool_call_counts.get(signature, 0) + 1
                if (
                    tool_call_counts[signature] > MAX_IDENTICAL_TOOL_CALLS
                    and repeated_signature is None
                ):
                    repeated_signature = signature
                parsed_calls.append((fc, args))

            if repeated_signature is not None:
                stop_reason = (
                    "Detected repeated identical tool calls "
                    f"more than {MAX_IDENTICAL_TOOL_CALLS} times: {repeated_signature}"
                )
                logger.warning(stop_reason)
                break

            logger.info(
                "Tool round %d/%d: %d call(s) — %s",
                round_index + 1,
                max_tool_rounds,
                len(function_calls),
                ", ".join(str(_item_get(fc, "name") or "") for fc in function_calls),
            )
            new_input = list(kwargs["input"])
            for item in _response_output(response):
                dumped = _item_dump(item)
                if dumped:
                    new_input.append(dumped)

            for fc, args in parsed_calls:
                name = str(_item_get(fc, "name") or "")
                logger.info("Tool call: %s(%s)", name, json.dumps(args, ensure_ascii=False))
                if on_tool_call:
                    await on_tool_call(name, args)

                executor = tool_executors.get(name)
                if executor is None:
                    tool_result = {"error": f"Unknown tool: {name}"}
                else:
                    try:
                        tool_result = executor(args)
                    except KeyError as e:
                        logger.warning("Tool %s missing required argument: %s", name, e)
                        tool_result = {
                            "error": f"Missing required argument: {e}. Please provide all required parameters."
                        }
                    except Exception as e:
                        logger.warning("Tool %s execution failed: %s", name, e)
                        tool_result = {"error": str(e)}

                output_str = json.dumps(sanitize_nan(tool_result), default=str, ensure_ascii=False)
                if len(output_str) > MAX_TOOL_RESULT_CHARS:
                    logger.warning(
                        "Tool %s result truncated: %d -> %d chars",
                        name,
                        len(output_str),
                        MAX_TOOL_RESULT_CHARS,
                    )
                    output_str = (
                        output_str[:MAX_TOOL_RESULT_CHARS] + '... [TRUNCATED - result too large]"}'
                    )

                new_input.append(
                    {
                        "type": "function_call_output",
                        "call_id": _item_get(fc, "call_id") or _item_get(fc, "id"),
                        "output": output_str,
                    }
                )

            kwargs["input"] = new_input
            if on_status:
                await on_status("thinking")
            response = await _create(**kwargs)
        else:
            stop_reason = f"Reached the maximum number of tool rounds ({max_tool_rounds})."

        if stop_reason is not None:
            logger.warning("Finalizing tool loop without further tool calls: %s", stop_reason)
            final_input = list(kwargs["input"])
            for item in _response_output(response):
                dumped = _item_dump(item)
                if dumped.get("type") == "function_call":
                    continue
                if dumped:
                    final_input.append(dumped)
            final_input.append(build_responses_finalization_item(stop_reason))
            # Keep tools only for Bedrock; other providers finalize without tools.
            final_kwargs = (
                dict(kwargs)
                if keep_tools_for_finalization
                else {k: v for k, v in kwargs.items() if k != "tools"}
            )
            final_kwargs["input"] = final_input
            final_kwargs["text"] = text_format
            if on_status:
                await on_status("thinking")
            response = await _create(**final_kwargs)

    output = _response_output_text(response)
    if output is None:
        final_input = list(kwargs["input"])
        for item in _response_output(response):
            dumped = _item_dump(item)
            if dumped.get("type") == "function_call":
                continue
            if dumped:
                final_input.append(dumped)
        if keep_tools_for_finalization:
            final_input.append(build_responses_finalization_item("Finalize the response."))
        # Keep tools only for Bedrock; other providers finalize without tools.
        final_kwargs = (
            dict(kwargs)
            if keep_tools_for_finalization
            else {k: v for k, v in kwargs.items() if k != "tools"}
        )
        final_kwargs["input"] = final_input
        final_kwargs["text"] = text_format
        if on_status:
            await on_status("thinking")
        response = await _create(**final_kwargs)
        output = _response_output_text(response)
        if output is None:
            text_items = [
                _item_get(item, "text")
                for item in _response_output(response)
                if _item_type(item) == "message"
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


async def run_litellm_completion_with_tools(
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
    """Tool-calling loop using LiteLLM Chat Completions."""
    chat_tools = agent_tools_for_chat_completions()
    extra_body: dict[str, Any] = {}
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
        "max_tokens": config.model.max_output_tokens,
        "tools": chat_tools,
        "tool_choice": "auto",
    }
    response_format: dict[str, Any] | None = None
    if response_schema is not None:
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": strict_schema,
                "schema": build_provider_response_schema(response_schema, config),
            },
        }
    if extra_body:
        base_kwargs["extra_body"] = extra_body
    if config.model.temperature is not None:
        base_kwargs["temperature"] = config.model.temperature
    if config.model.top_p is not None:
        base_kwargs["top_p"] = config.model.top_p
    if should_send_reasoning_effort(config):
        base_kwargs["reasoning_effort"] = config.model.reasoning_effort

    msgs: list[dict[str, Any]] = list(messages)

    async def _create(**kw: Any) -> Any:
        try:
            return await litellm_completion(config, **kw)
        except Exception as exc:
            if _is_unsupported_param(exc, "temperature") and "temperature" in kw:
                kw.pop("temperature")
                return await _create(**kw)
            if _is_unsupported_param(exc, "top_p") and "top_p" in kw:
                kw.pop("top_p")
                return await _create(**kw)
            if _is_unsupported_param(exc, "reasoning_effort") and "reasoning_effort" in kw:
                kw.pop("reasoning_effort")
                return await _create(**kw)
            if (
                _is_unsupported_param(exc, "response_format")
                or _is_unsupported_param(exc, "json_schema")
                or _is_unsupported_param(exc, "strict")
            ) and "response_format" in kw:
                kw["response_format"] = {"type": "json_object"}
                try:
                    return await _create(**kw)
                except Exception:
                    kw.pop("response_format", None)
                    return await _create(**kw)
            raise

    if on_status:
        await on_status("thinking")

    last_message: Any = None
    max_tool_rounds = get_max_tool_rounds(config)
    tool_call_counts: dict[str, int] = {}
    stop_reason: str | None = None
    for round_index in range(max_tool_rounds):
        response = await _create(messages=msgs, **base_kwargs)
        msg = _completion_message(response)
        last_message = msg
        tool_calls = _message_tool_calls(msg)
        if not tool_calls:
            break

        parsed_calls: list[tuple[Any, dict[str, Any]]] = []
        repeated_signature: str | None = None
        for tc in tool_calls:
            fn = _tool_call_function(tc)
            try:
                args = json.loads(_item_get(fn, "arguments") or "{}")
            except (json.JSONDecodeError, TypeError):
                args = {}
            name = str(_item_get(fn, "name") or "")
            signature = build_tool_call_signature(name, args)
            tool_call_counts[signature] = tool_call_counts.get(signature, 0) + 1
            if (
                tool_call_counts[signature] > MAX_IDENTICAL_TOOL_CALLS
                and repeated_signature is None
            ):
                repeated_signature = signature
            parsed_calls.append((tc, args))

        if repeated_signature is not None:
            stop_reason = (
                "Detected repeated identical tool calls "
                f"more than {MAX_IDENTICAL_TOOL_CALLS} times: {repeated_signature}"
            )
            logger.warning(stop_reason)
            break

        logger.info(
            "Tool round %d/%d: %d call(s) — %s",
            round_index + 1,
            max_tool_rounds,
            len(tool_calls),
            ", ".join(str(_item_get(_tool_call_function(tc), "name") or "") for tc in tool_calls),
        )
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": _message_content(msg) or None,
            "tool_calls": [
                {
                    "id": _item_get(tc, "id"),
                    "type": "function",
                    "function": {
                        "name": _item_get(_tool_call_function(tc), "name"),
                        "arguments": _item_get(_tool_call_function(tc), "arguments"),
                    },
                }
                for tc in tool_calls
            ],
        }
        reasoning_content = _item_get(msg, "reasoning_content") if msg is not None else None
        if isinstance(reasoning_content, str) and reasoning_content:
            assistant_msg["reasoning_content"] = reasoning_content
        msgs.append(assistant_msg)

        for tc, args in parsed_calls:
            fn = _tool_call_function(tc)
            name = str(_item_get(fn, "name") or "")
            if on_tool_call:
                await on_tool_call(name, args)

            executor = tool_executors.get(name)
            if executor is None:
                tool_result: Any = {"error": f"Unknown tool: {name}"}
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
            msgs.append({"role": "tool", "tool_call_id": _item_get(tc, "id"), "content": output_str})

        if on_status:
            await on_status("thinking")
    else:
        stop_reason = f"Reached the maximum number of tool rounds ({max_tool_rounds})."

    # Bedrock keeps tool definitions during finalization; the prompt prevents more calls.
    keep_tools_for_finalization = config.model.provider.lower() == "bedrock"

    if stop_reason is not None:
        logger.warning("Finalizing tool loop without further tool calls: %s", stop_reason)
        # Keep tools only for Bedrock; other providers finalize without tools.
        final_kwargs = (
            dict(base_kwargs)
            if keep_tools_for_finalization
            else {k: v for k, v in base_kwargs.items() if k not in ("tools", "tool_choice")}
        )
        if response_format is not None:
            final_kwargs["response_format"] = response_format
        final_messages = list(msgs)
        final_messages.append(build_chat_finalization_message(stop_reason))
        response = await _create(messages=final_messages, **final_kwargs)
        last_message = _completion_message(response)

    if stop_reason is None and tool_call_counts and last_message is not None:
        # Keep tools only for Bedrock; other providers finalize without tools.
        final_kwargs = (
            dict(base_kwargs)
            if keep_tools_for_finalization
            else {k: v for k, v in base_kwargs.items() if k not in ("tools", "tool_choice")}
        )
        if response_format is not None:
            final_kwargs["response_format"] = response_format
        final_messages = list(msgs)
        final_messages.append(
            {
                "role": "user",
                "content": (
                    "Do not call any more tools. Using the tool results above, "
                    "produce the final answer in the required JSON format."
                ),
            }
        )
        response = await _create(messages=final_messages, **final_kwargs)
        last_message = _completion_message(response)

    content = _message_content(last_message)
    if content:
        return content
    return _message_reasoning_text(last_message)


async def run_litellm_completion(
    messages: list[dict[str, Any]],
    config: CopilotConfig,
) -> str:
    """Call LiteLLM Chat Completions and return the content."""
    extra_body: dict[str, Any] = {}
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
    if should_send_reasoning_effort(config):
        kwargs["reasoning_effort"] = config.model.reasoning_effort
    try:
        response = await litellm_completion(config, **kwargs)
    except Exception as exc:
        if _is_unsupported_param(exc, "temperature") and "temperature" in kwargs:
            kwargs.pop("temperature")
            response = await litellm_completion(config, **kwargs)
        elif _is_unsupported_param(exc, "top_p") and "top_p" in kwargs:
            kwargs.pop("top_p")
            response = await litellm_completion(config, **kwargs)
        elif _is_unsupported_param(exc, "reasoning_effort") and "reasoning_effort" in kwargs:
            kwargs.pop("reasoning_effort")
            response = await litellm_completion(config, **kwargs)
        else:
            raise
    message = _completion_message(response)
    content = _message_content(message)
    if content:
        return content
    return _message_reasoning_text(message)
