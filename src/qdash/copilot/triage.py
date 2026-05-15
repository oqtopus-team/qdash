"""Shared AI triage helpers used by API, workflow, and evaluation tooling."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from qdash.copilot.agent import blocks_to_markdown, run_analysis
from qdash.copilot.runtime import CopilotRuntime

if TYPE_CHECKING:
    from qdash.copilot.config import CopilotConfig, ModelConfig
    from qdash.copilot.contracts import AnalysisContextResult

AI_TRIAGE_FORMAT_REMINDER = """\

Required output format:
Return JSON, but the JSON `explanation` string must start exactly with this
markdown block. Do not put prose before it.

**Review triage**
- Decision: `PASS` | `PASS_WITH_NOTE` | `REVIEW` | `FAIL`
- Human label suggestion: `CORRECT` | `SUSPICIOUS` | `MISASSIGNMENT` | `NO_SIGNAL` | `ANOMALY`
- Accepted parameter(s): ...
- Needs review: ...
- Primary reason: ...
- Closest knowledge case: ...
- Suggested labels: ...
- Recommended action: ...
- Optional note: ...
"""


def select_analysis_model(config: CopilotConfig) -> ModelConfig:
    """Return the effective model used for task-result analysis."""
    return config.analysis_model or (
        config.analysis_models[0] if config.analysis_models else config.model
    )


def apply_ai_triage_config(config: CopilotConfig) -> CopilotConfig:
    """Apply AI-triage-only speed defaults without changing interactive chat."""
    analysis = config.analysis
    if analysis.ai_triage_max_expected_images is not None:
        analysis = analysis.model_copy(
            update={"max_expected_images": analysis.ai_triage_max_expected_images}
        )

    model = select_analysis_model(config)
    if analysis.ai_triage_max_output_tokens is not None:
        model = model.model_copy(update={"max_output_tokens": analysis.ai_triage_max_output_tokens})

    return config.model_copy(update={"analysis": analysis, "analysis_model": model})


def build_ai_triage_user_message(config: CopilotConfig) -> str:
    """Build the user message sent to the LLM for automatic AI triage."""
    return f"{config.analysis.ai_triage_message}\n\n{AI_TRIAGE_FORMAT_REMINDER}"


def build_ai_triage_context(
    *,
    task_name: str,
    chip_id: str,
    qid: str,
    task_id: str,
    config: CopilotConfig,
) -> AnalysisContextResult:
    """Build the compact context used by AI triage analysis."""
    context_bundle = CopilotRuntime().build_analysis_context(
        task_name=task_name,
        chip_id=chip_id,
        qid=qid,
        task_id=task_id,
        image_base64=None,
        config=config,
    )
    context_bundle.context = context_bundle.context.model_copy(
        update={"recent_values": [], "history_results": []}
    )
    return context_bundle


def _param_value(params: dict[str, object], *names: str) -> object:
    """Return a compact output-parameter value from possible parameter names."""
    for name in names:
        if name not in params:
            continue
        raw = params[name]
        if isinstance(raw, dict):
            return raw.get("value")
        return raw
    return None


def forced_ai_triage_markdown(task_name: str, output_params: dict[str, object]) -> str | None:
    """Apply deterministic safety guards before asking a local VLM."""
    if task_name != "CheckQubitSpectroscopy":
        return None

    f01 = _param_value(
        output_params,
        "coarse_qubit_frequency",
        "coarse_qubit_frequency_ghz",
        "f01_frequency",
        "f01_frequency_ghz",
    )
    if f01 is not None:
        return None

    return "\n".join(
        [
            "**Review triage**",
            "- Decision: `FAIL`",
            "- Human label suggestion: `NO_SIGNAL`",
            "- Accepted parameter(s): `none`",
            "- Needs review: `none`",
            "- Primary reason: No f01 output parameter was detected, so the result is not safe "
            "for automatic update.",
            "- Closest knowledge case: `none`",
            "- Suggested labels: `no_signal`",
            "- Recommended action: Rerun qubit spectroscopy with an adjusted frequency range or "
            "drive power.",
            "- Optional note: Deterministic safety guard applied before local VLM review.",
        ]
    )


def render_ai_triage_markdown(
    *,
    task_name: str,
    config: CopilotConfig,
    context_bundle: AnalysisContextResult,
    user_message: str | None = None,
) -> str:
    """Render markdown for one AI triage run."""
    if forced := forced_ai_triage_markdown(task_name, context_bundle.context.output_parameters):
        return forced

    result = asyncio.run(
        run_analysis(
            context=context_bundle.context,
            user_message=user_message or build_ai_triage_user_message(config),
            config=config,
            image_base64=context_bundle.image_base64,
            expected_images=context_bundle.expected_images,
            experiment_images=context_bundle.experiment_images,
            conversation_history=[],
            tool_executors=None,
        )
    )
    return blocks_to_markdown(result).strip()


def build_model_override(
    *,
    base_model: ModelConfig,
    provider: str | None = None,
    name: str | None = None,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
    reasoning_effort: str | None = None,
    api_style: str | None = None,
    base_url: str | None = None,
    api_key_env: str | None = None,
) -> ModelConfig:
    """Build a per-run model override from CLI-friendly scalar options."""
    updates: dict[str, Any] = {}
    if provider is not None:
        updates["provider"] = provider
    if name is not None:
        updates["name"] = name
    if temperature is not None:
        updates["temperature"] = temperature
    if max_output_tokens is not None:
        updates["max_output_tokens"] = max_output_tokens
    if reasoning_effort is not None:
        updates["reasoning_effort"] = reasoning_effort
    if api_style is not None:
        updates["api_style"] = api_style
    if base_url is not None:
        updates["base_url"] = base_url
    if api_key_env is not None:
        updates["api_key_env"] = api_key_env
    return base_model.model_copy(update=updates) if updates else base_model
