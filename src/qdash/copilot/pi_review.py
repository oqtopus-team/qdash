"""Run one AI review through the Pi Agent Runtime.

The runtime has no way to constrain assistant text to a schema, so the verdict
comes back as `submit_review` tool arguments. Rendering those into the stored
markdown note stays here, byte-for-byte compatible with the LiteLLM path, so the
dashboard and UI regexes keep working.
"""

from __future__ import annotations

import logging
import os
import re
from typing import TYPE_CHECKING, Literal

import httpx
from pydantic import BaseModel

from qdash.copilot.prompts.analysis import (
    build_analysis_system_prompt,
    build_language_instruction,
)
from qdash.copilot.prompts.models import AnalysisPromptOptions

if TYPE_CHECKING:
    from qdash.copilot.config import CopilotConfig, ModelConfig
    from qdash.copilot.contracts import AnalysisContextResult

logger = logging.getLogger(__name__)

RUNTIME_URL = os.environ.get("PI_AGENT_RUNTIME_URL", "http://agent-runtime:8002")
# Generous: the runtime queues reviews behind a concurrency cap, and a local VLM
# reading two figures is slow even once it starts.
REQUEST_TIMEOUT_S = float(os.environ.get("PI_AGENT_RUNTIME_REVIEW_TIMEOUT", "600"))
_REVIEW_FIELD_MARKER = re.compile(
    r"-\s*(decision|human label suggestion|accepted parameter\(s\)|needs review|"
    r"primary reason|closest knowledge case|suggested labels|recommended action|optional note)\s*:",
    re.IGNORECASE,
)


class ReviewVerdict(BaseModel):
    """The `submit_review` tool arguments, as returned by the runtime."""

    decision: Literal["PASS", "PASS_WITH_NOTE", "REVIEW", "FAIL"]
    human_label: Literal["CORRECT", "SUSPICIOUS", "MISASSIGNMENT", "NO_SIGNAL", "ANOMALY"]
    accepted_parameters: str
    needs_review: str
    primary_reason: str
    closest_knowledge_case: str
    suggested_labels: str
    recommended_action: str
    optional_note: str = ""


def _single_line(value: str, *, default: str = "none") -> str:
    """Collapse model-provided free text so it cannot inject parsed fields."""
    collapsed = " ".join(value.split())
    sanitized = _REVIEW_FIELD_MARKER.sub(lambda match: f"— {match.group(1)}:", collapsed)
    return sanitized or default


def render_review_markdown(verdict: ReviewVerdict) -> str:
    """Render a verdict as the markdown block QDash stores and parses.

    The shape must match ``AI_REVIEW_FORMAT_REMINDER`` exactly: the dashboard and
    the task-result service both read these lines back with a regex.
    """
    return "\n".join(
        [
            "**AI review**",
            f"- Decision: `{verdict.decision}`",
            f"- Human label suggestion: `{verdict.human_label}`",
            f"- Accepted parameter(s): {_single_line(verdict.accepted_parameters)}",
            f"- Needs review: {_single_line(verdict.needs_review)}",
            f"- Primary reason: {_single_line(verdict.primary_reason)}",
            f"- Closest knowledge case: {_single_line(verdict.closest_knowledge_case)}",
            f"- Suggested labels: {_single_line(verdict.suggested_labels)}",
            f"- Recommended action: {_single_line(verdict.recommended_action)}",
            f"- Optional note: {_single_line(verdict.optional_note)}",
        ]
    )


def collect_images(bundle: AnalysisContextResult) -> list[dict[str, str]]:
    """Flatten the context bundle's figures into Pi image attachments.

    Expected reference images come first, then the measured ones. Pi's
    ``ImageContent`` carries no alt text, so the prompt states the counts and the
    order instead.
    """
    experiment = bundle.experiment_images or (
        [(bundle.image_base64, "result figure")] if bundle.image_base64 else []
    )
    return [
        {"data": data, "mimeType": "image/png"}
        for data, _alt in [*bundle.expected_images, *experiment]
        if data
    ]


def build_review_prompt(
    *,
    bundle: AnalysisContextResult,
    config: CopilotConfig,
    user_message: str,
) -> str:
    """Build the single message that carries the whole review context.

    Pi review sessions have no tools for looking things up, so everything the
    model needs has to be in here.
    """
    expected_count = len(bundle.expected_images)
    experiment_count = len(collect_images(bundle)) - expected_count

    body = build_analysis_system_prompt(
        AnalysisPromptOptions(
            context=bundle.context,
            language_instruction=build_language_instruction(config),
            scoring=config.scoring,
            has_expected_images=expected_count > 0,
            has_experiment_image=experiment_count > 0,
            # The verdict is collected as tool arguments; the markdown skeleton
            # would only compete with it.
            include_ai_review_instruction=False,
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


def run_review(
    *,
    bundle: AnalysisContextResult,
    config: CopilotConfig,
    model: ModelConfig,
    user_message: str,
) -> ReviewVerdict:
    """Ask the Pi Agent Runtime for one verdict.

    Raises on any failure. The caller already records failures on the task
    result; falling back to LiteLLM here would make the recorded model a lie.
    """
    payload = {
        "prompt": build_review_prompt(bundle=bundle, config=config, user_message=user_message),
        "images": collect_images(bundle),
        "model": {"provider": model.provider, "name": model.name},
    }

    # trust_env=False: the runtime is an internal service, so an ambient
    # HTTP(S)_PROXY must not be applied to it.
    with httpx.Client(timeout=REQUEST_TIMEOUT_S, trust_env=False) as client:
        response = client.post(
            f"{RUNTIME_URL}/review",
            headers=_runtime_headers(),
            json=payload,
        )
    if response.status_code != httpx.codes.OK:
        raise RuntimeError(f"Agent runtime returned HTTP {response.status_code}")

    body = response.json()
    if "review" not in body:
        detail = body.get("error", "agent runtime returned no verdict")
        logger.warning("Pi review produced no verdict: %s", body.get("text", "")[:500])
        raise RuntimeError(detail)
    return ReviewVerdict.model_validate(body["review"])


def _runtime_headers() -> dict[str, str]:
    """Return the internal runtime credential, failing closed when it is absent."""
    token = os.environ.get("AGENT_RUNTIME_TOKEN")
    if not token:
        msg = "AGENT_RUNTIME_TOKEN is required for the Pi Agent Runtime"
        raise RuntimeError(msg)
    return {"Authorization": f"Bearer {token}"}
