"""Bridge between the Copilot analysis SSE endpoint and the Pi Agent Runtime.

Analysis sits between chat and review: it is a continuing conversation with
tools, like chat, but its first turn carries figures and a pre-built context,
like review. Only that first turn differs, so this module builds the opening
message and then hands off to the chat bridge.

See .agents/sessions/2026-09-28-analyze-sidebar-pi-agent/adr/0001-*.md and
adr/0003-*.md
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from qdash.api.lib.sse import sse_event
from qdash.api.services import pi_chat_service
from qdash.copilot.pi_review import collect_images
from qdash.copilot.prompts.analysis import build_analysis_system_prompt
from qdash.copilot.prompts.models import AnalysisPromptOptions

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from qdash.copilot.config import CopilotConfig
    from qdash.copilot.contracts import AnalysisContextResult, AnalyzeRequest

logger = logging.getLogger(__name__)


def build_analysis_prompt(
    *,
    bundle: AnalysisContextResult,
    config: CopilotConfig,
    user_message: str,
    language_instruction: str,
) -> str:
    """Build the opening message that carries the whole analysis context.

    Sibling of ``pi_review.build_review_prompt``. Unlike review this keeps the
    AI review markdown skeleton (the sidebar shows it as text and nothing
    competes for it here) and it does keep the language instruction.
    """
    expected_count = len(bundle.expected_images)
    experiment_count = len(collect_images(bundle)) - expected_count

    body = build_analysis_system_prompt(
        AnalysisPromptOptions(
            context=bundle.context,
            language_instruction=language_instruction,
            scoring=config.scoring,
            has_expected_images=expected_count > 0,
            has_experiment_image=experiment_count > 0,
            # Pi answers in free text and calls `render_chart`; the blocks are
            # reassembled from that. Asking for JSON here would land the raw
            # JSON string inside a text block.
            include_response_format=False,
        )
    )

    image_note = (
        f"\n\n## Attached figures\n\n"
        f"{expected_count} expected reference figure(s) first, "
        f"then {experiment_count} figure(s) measured in this run."
        if expected_count or experiment_count
        else ""
    )
    return f"{body}{image_note}\n\n## Your task\n\n{user_message}"


async def stream(
    request: AnalyzeRequest,
    config: CopilotConfig,
    bundle: AnalysisContextResult,
    *,
    username: str,
    language_instruction: str,
    images_sent: dict[str, Any],
) -> AsyncGenerator[str, None]:
    """Proxy one analysis turn through the Pi Agent Runtime as SSE events."""
    if not request.session_id:
        yield sse_event(
            "error",
            {"step": "init", "detail": "session_id is required by the Pi analysis backend"},
        )
        return

    agent_messages = pi_chat_service.load_agent_messages(username, request.session_id)
    first_turn = not agent_messages

    payload: dict[str, Any] = {
        "conversation_id": request.session_id,
        "message": (
            build_analysis_prompt(
                bundle=bundle,
                config=config,
                user_message=request.message,
                language_instruction=language_instruction,
            )
            if first_turn
            else request.message
        ),
        "messages": agent_messages,
        "model": {"provider": config.model.provider, "name": config.model.name},
        "thinking_level": pi_chat_service.thinking_level(config),
        # Only on the first turn: the figures stay in the stored conversation,
        # and resending them every turn would eat the context window.
        "images": collect_images(bundle) if first_turn else [],
    }

    def on_done(messages: list[dict[str, Any]]) -> None:
        pi_chat_service.save_agent_messages(username, str(request.session_id), messages)

    async for event in pi_chat_service.stream_payload(
        payload,
        on_done=on_done,
        step="run_analysis",
        extra_result={"images_sent": images_sent},
    ):
        yield event
