"""Public Copilot agent entrypoint.

This module exposes the callable surface used by API routes and workflows.
Implementation details live under ``agent_runtime/``:

- ``client``: LLM request construction
- ``execution``: Responses / Chat Completions loops and tool orchestration
- ``parsing``: response parsing and fallback handling
- ``rendering``: blocks rendering and compact summaries
- ``translation``: language fallback helpers
- ``schemas`` / ``types``: runtime contracts
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from qdash.copilot.agent_runtime import execution as _agent_execution
from qdash.copilot.agent_runtime.parsing import (
    has_real_blocks as _has_real_blocks,
)
from qdash.copilot.agent_runtime.parsing import (
    parse_blocks_response as _parse_blocks_response,
)
from qdash.copilot.agent_runtime.schemas import BLOCKS_RESPONSE_SCHEMA
from qdash.copilot.agent_runtime.translation import (
    translate_analysis_response as _translate_analysis_response_impl,
)
from qdash.copilot.prompts.analysis import build_analysis_system_prompt
from qdash.copilot.prompts.chat import (
    CHART_SYSTEM_PROMPT,
    CHAT_COMPLETIONS_STRICT_EMULATION,
    build_chat_system_prompt,
)
from qdash.copilot.prompts.models import AnalysisPromptOptions, ChatPromptContext

if TYPE_CHECKING:
    from qdash.copilot.agent_runtime.types import (
        OnStatusHook,
        OnToolCallHook,
        ToolExecutors,
    )
    from qdash.copilot.config import CopilotConfig, ModelConfig
    from qdash.copilot.contracts import AnalysisResponse, TaskAnalysisContext
    from qdash.copilot.tooling.sandbox import SandboxChartSpec

logger = logging.getLogger(__name__)


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

    if thinking_lang != response_lang and not config.model.disable_thinking_instruction:
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
    has_expected_images: bool = False,
    has_experiment_image: bool = False,
) -> str:
    """Build the full system prompt from prompt assets and analysis context."""
    return build_analysis_system_prompt(
        AnalysisPromptOptions(
            context=context,
            language_instruction=_build_language_instruction(config),
            scoring=config.scoring if config else {},
            include_response_format=include_response_format,
            has_expected_images=has_expected_images,
            has_experiment_image=has_experiment_image,
        )
    )


def _build_input(
    user_message: str,
    image_base64: str | None,
    conversation_history: list[dict[str, str]] | None,
    expected_images: list[tuple[str, str]] | None = None,
    experiment_images: list[tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Build the input items list for the OpenAI Responses API.

    Unlike Chat Completions, system messages are passed via the
    ``instructions`` parameter, so only user/assistant messages
    are included here.

    Parameters
    ----------
    user_message : str
        The user's question.
    image_base64 : str | None
        Base64-encoded experiment result image.
    conversation_history : list[dict[str, str]] | None
        Previous conversation messages.
    expected_images : list[tuple[str, str]] | None
        List of (base64_data, alt_text) for expected reference images.
    experiment_images : list[tuple[str, str]] | None
        List of (base64_data, alt_text) for actual experiment result images.

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

    # Build the current user message content parts
    content_parts: list[dict[str, Any]] = []

    # Add expected reference images first (with labels)
    if expected_images:
        content_parts.append({"type": "input_text", "text": "Expected result reference images:"})
        for b64_data, alt_text in expected_images:
            content_parts.append({"type": "input_text", "text": f"[Reference: {alt_text}]"})
            content_parts.append(
                {
                    "type": "input_image",
                    "image_url": f"data:image/png;base64,{b64_data}",
                }
            )

    actual_images = experiment_images or ([(image_base64, "result figure")] if image_base64 else [])
    if actual_images:
        label = (
            "Actual experimental result images:"
            if len(actual_images) > 1
            else "Actual experimental result:"
        )
        content_parts.append({"type": "input_text", "text": label})
        for b64_data, alt_text in actual_images:
            if len(actual_images) > 1:
                content_parts.append({"type": "input_text", "text": f"[Target: {alt_text}]"})
            content_parts.append(
                {
                    "type": "input_image",
                    "image_url": f"data:image/png;base64,{b64_data}",
                }
            )

    # Add the user message text
    content_parts.append({"type": "input_text", "text": user_message})

    items.append({"role": "user", "content": content_parts})

    return items


def _build_messages(
    system_prompt: str,
    user_message: str,
    image_base64: str | None,
    conversation_history: list[dict[str, str]] | None,
    expected_images: list[tuple[str, str]] | None = None,
    experiment_images: list[tuple[str, str]] | None = None,
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
    actual_images = experiment_images or ([(image_base64, "result figure")] if image_base64 else [])
    has_images = actual_images or expected_images
    if has_images:
        content_parts: list[dict[str, Any]] = []

        # Add expected reference images first
        if expected_images:
            content_parts.append({"type": "text", "text": "Expected result reference images:"})
            for b64_data, alt_text in expected_images:
                content_parts.append({"type": "text", "text": f"[Reference: {alt_text}]"})
                content_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64_data}"},
                    }
                )

        if actual_images:
            label = (
                "Actual experimental result images:"
                if len(actual_images) > 1
                else "Actual experimental result:"
            )
            content_parts.append({"type": "text", "text": label})
            for b64_data, alt_text in actual_images:
                if len(actual_images) > 1:
                    content_parts.append({"type": "text", "text": f"[Target: {alt_text}]"})
                content_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64_data}"},
                    }
                )

        content_parts.append({"type": "text", "text": user_message})
        messages.append({"role": "user", "content": content_parts})
    else:
        messages.append({"role": "user", "content": user_message})

    return messages


async def _translate_analysis_response(
    response: AnalysisResponse,
    target_lang: str,
    general_model: ModelConfig,
) -> AnalysisResponse:
    """Translate an AnalysisResponse via the general (non-specialized) model."""
    return await _translate_analysis_response_impl(response, target_lang, general_model)


def _wrap_tool_executors(
    tool_executors: ToolExecutors,
    data_store: dict[str, Any],
) -> tuple[ToolExecutors, list[SandboxChartSpec | dict[str, Any]]]:
    """Wrap tool executors to handle data store and chart collection."""
    return _agent_execution.wrap_tool_executors(tool_executors, data_store)


def _wrap_rate_limited_executors(tool_executors: ToolExecutors) -> ToolExecutors:
    """Wrap per-qubit tools with a call-count limiter."""
    return _agent_execution.wrap_rate_limited_executors(tool_executors)


def _sanitize_nan(obj: Any) -> Any:
    """Recursively replace NaN/Inf float values with None for valid JSON."""
    return _agent_execution.sanitize_nan(obj)


def _inject_collected_charts(
    result: dict[str, Any],
    collected_charts: list[SandboxChartSpec | dict[str, Any]],
) -> dict[str, Any]:
    """Append tool-generated charts to the blocks response."""
    return _agent_execution.inject_collected_charts(result, collected_charts)


async def _run_litellm_responses(
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
    return await _agent_execution.run_litellm_responses(
        system_prompt,
        input_items,
        config,
        tool_executors,
        response_schema=response_schema,
        strict_schema=strict_schema,
        on_tool_call=on_tool_call,
        on_status=on_status,
    )


def _agent_tools_for_chat_completions() -> list[dict[str, Any]]:
    """Convert Responses API tools into Chat Completions tool format."""
    return _agent_execution.agent_tools_for_chat_completions()


async def _run_litellm_completion_with_tools(
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
    return await _agent_execution.run_litellm_completion_with_tools(
        messages,
        config,
        tool_executors,
        response_schema=response_schema,
        strict_schema=strict_schema,
        schema_name=schema_name,
        on_tool_call=on_tool_call,
        on_status=on_status,
    )


async def _run_litellm_completion(
    messages: list[dict[str, Any]],
    config: CopilotConfig,
) -> str:
    """Call LiteLLM Chat Completions and return the content."""
    return await _agent_execution.run_litellm_completion(messages, config)


async def run_analysis(
    context: TaskAnalysisContext,
    user_message: str,
    config: CopilotConfig,
    image_base64: str | None = None,
    expected_images: list[tuple[str, str]] | None = None,
    experiment_images: list[tuple[str, str]] | None = None,
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
    expected_images : list[tuple[str, str]] | None
        Optional list of (base64_data, alt_text) for expected reference images.
    experiment_images : list[tuple[str, str]] | None
        Optional list of actual experiment result images. When provided, this
        supersedes image_base64 and preserves per-image target labels.
    conversation_history : list[dict[str, str]] | None
        Previous conversation messages.
    tool_executors : ToolExecutors | None
        Optional dict mapping tool names to executor callables.

    Returns
    -------
    dict[str, Any]
        Blocks-format response: {"blocks": [...], "assessment": ...}

    """
    # Allow a dedicated analysis model (e.g. calibration-specialized LLM) to
    # override the general chat model for task result analysis.
    analysis_model = config.analysis_model
    if analysis_model is None and config.analysis_models:
        analysis_model = config.analysis_models[0]
    if analysis_model is not None:
        config = config.model_copy(update={"model": analysis_model})
    api_style = config.model.api_style

    has_expected = bool(expected_images)
    has_experiment = bool(experiment_images or image_base64)

    if tool_executors:
        wrapped_executors: ToolExecutors | None = None
        data_store: dict[str, Any] = {}
        rate_limited = _wrap_rate_limited_executors(tool_executors)
        wrapped_executors, collected_charts = _wrap_tool_executors(rate_limited, data_store)
    else:
        wrapped_executors, collected_charts = None, []

    if api_style == "completion":
        system_prompt = _build_system_prompt(
            context,
            config=config,
            include_response_format=True,
            has_expected_images=has_expected,
            has_experiment_image=has_experiment,
        ) + CHART_SYSTEM_PROMPT + CHAT_COMPLETIONS_STRICT_EMULATION
        messages = _build_messages(
            system_prompt,
            user_message,
            image_base64,
            conversation_history,
            expected_images,
            experiment_images,
        )
        if wrapped_executors:
            content = await _run_litellm_completion_with_tools(
                messages,
                config,
                wrapped_executors,
                response_schema=BLOCKS_RESPONSE_SCHEMA,
                strict_schema=True,
                schema_name="blocks_response",
                on_tool_call=on_tool_call,
                on_status=on_status,
            )
        else:
            content = await _run_litellm_completion(messages, config)
        parsed = _parse_blocks_response(content, config)
        if not _has_real_blocks(parsed):
            logger.warning(
                "completion: BLOCKS parse fell back to single text block "
                "(model emitted free text). content_chars=%d",
                len(content or ""),
            )
        return _inject_collected_charts(parsed, collected_charts)
    if api_style == "responses":
        system_prompt = (
            _build_system_prompt(
                context,
                config=config,
                has_expected_images=has_expected,
                has_experiment_image=has_experiment,
            )
            + CHART_SYSTEM_PROMPT
        )
        input_items = _build_input(
            user_message,
            image_base64,
            conversation_history,
            expected_images,
            experiment_images,
        )
        content = await _run_litellm_responses(
            system_prompt,
            input_items,
            config,
            wrapped_executors,
            response_schema=BLOCKS_RESPONSE_SCHEMA,
            strict_schema=False,
            on_tool_call=on_tool_call,
            on_status=on_status,
        )
        return _inject_collected_charts(_parse_blocks_response(content, config), collected_charts)
    raise ValueError(f"Unsupported api_style: {config.model.api_style}")


def blocks_to_markdown(result: dict[str, Any]) -> str:
    """Convert a blocks-format AI response to markdown for issue replies."""
    blocks = result.get("blocks", [])
    if not blocks:
        logger.warning("blocks_to_markdown: no blocks in result keys=%s", list(result.keys()))

    parts: list[str] = []
    for block in blocks:
        block_type = block.get("type")
        content = block.get("content")
        # Use `is not None` — empty string "" is falsy but still valid content
        if block_type == "text" and content is not None and content != "":
            parts.append(str(content))
        elif block_type == "chart" and block.get("chart"):
            chart = block["chart"]
            title = chart.get("layout", {}).get("title", "Chart")
            parts.append(
                f"**{title}**\n```json\n{json.dumps(chart, indent=2, ensure_ascii=False)}\n```"
            )

    if not parts:
        logger.warning("blocks_to_markdown: all blocks produced empty output, result=%s", result)

    return "\n\n".join(parts)


def _build_chat_system_prompt(
    *,
    config: CopilotConfig | None = None,
    chip_id: str | None = None,
    qid: str | None = None,
    qubit_params: dict[str, Any] | None = None,
) -> str:
    """Build the generic chat system prompt from prompt assets."""
    return build_chat_system_prompt(
        ChatPromptContext(
            language_instruction=_build_language_instruction(config),
            scoring=config.scoring if config else {},
            chip_id=chip_id,
            qid=qid,
            qubit_params=qubit_params or {},
        )
    )


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
    """Run a generic chat using the configured LiteLLM API style.

    Lightweight version of run_analysis that does not require TaskAnalysisContext.
    Optionally includes chip_id/qid context if provided.

    Returns
    -------
    dict[str, Any]
        Blocks-format response: {"blocks": [...], "assessment": ...}

    """
    system_prompt = _build_chat_system_prompt(
        config=config,
        chip_id=chip_id,
        qid=qid,
        qubit_params=qubit_params,
    )

    if tool_executors:
        data_store: dict[str, Any] = {}
        rate_limited = _wrap_rate_limited_executors(tool_executors)
        wrapped_executors, collected_charts = _wrap_tool_executors(rate_limited, data_store)
    else:
        wrapped_executors, collected_charts = None, []

    # LiteLLM Responses is the default path. Providers that only expose Chat
    # Completions opt in via `api_style: completion`.
    api_style = config.model.api_style
    if api_style == "completion":
        # ds4-server and similar providers expose tools and chat completions
        # but reject `response_format: json_schema` / strict mode. Reinforce
        # the BLOCKS contract in the system prompt so the model still emits a
        # parseable JSON object on its own.
        chat_system_prompt = system_prompt + CHAT_COMPLETIONS_STRICT_EMULATION
        messages = _build_messages(
            chat_system_prompt,
            user_message,
            image_base64,
            conversation_history,
        )
        if wrapped_executors:
            content = await _run_litellm_completion_with_tools(
                messages,
                config,
                wrapped_executors,
                response_schema=BLOCKS_RESPONSE_SCHEMA,
                strict_schema=True,
                schema_name="blocks_response",
                on_tool_call=on_tool_call,
                on_status=on_status,
            )
        else:
            content = await _run_litellm_completion(messages, config)
        parsed = _parse_blocks_response(content, config)
        if not _has_real_blocks(parsed):
            logger.warning(
                "completion: BLOCKS parse fell back to single text block "
                "(model emitted free text). content_chars=%d",
                len(content or ""),
            )
        return _inject_collected_charts(parsed, collected_charts)

    if api_style != "responses":
        raise ValueError(f"Unsupported api_style: {config.model.api_style}")

    input_items = _build_input(user_message, image_base64, conversation_history)
    content = await _run_litellm_responses(
        system_prompt,
        input_items,
        config,
        wrapped_executors,
        response_schema=BLOCKS_RESPONSE_SCHEMA,
        strict_schema=False,
        on_tool_call=on_tool_call,
        on_status=on_status,
    )
    return _inject_collected_charts(_parse_blocks_response(content, config), collected_charts)
