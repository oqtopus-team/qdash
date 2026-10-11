"""Prompt builders for chats about a task result."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from qdash.copilot.config import CopilotConfig, ScoringThreshold
    from qdash.copilot.prompts.models import AnalysisPromptOptions


def build_language_instruction(config: CopilotConfig | None) -> str:
    """Build the response/thinking language instruction for a prompt.

    Lives here rather than in ``agent.py`` so the Pi backend can build a prompt
    without importing the LiteLLM agent.
    """
    if config is None:
        return "Respond in the same language as the user's message."

    response_lang = config.response_language
    thinking_lang = config.thinking_language
    parts: list[str] = []

    if thinking_lang != response_lang and not config.model.disable_thinking_instruction:
        parts.append(f"Think and reason internally in {thinking_lang} for technical precision.")

    if response_lang == "auto":
        parts.append(
            "Respond in the same language as the user's latest message, "
            "unless the user asks for another language."
        )
    elif response_lang == "ja":
        parts.append(
            "Always respond in Japanese (日本語). "
            "Use technical terms in English where appropriate (e.g., T1, T2, fidelity)."
        )
    elif response_lang == "en":
        parts.append("Always respond in English.")
    else:
        parts.append(f"Always respond in {response_lang}.")

    return " ".join(parts)


ANALYSIS_SYSTEM_PROMPT_BASE = """\
You are an expert in superconducting qubit calibration.
You analyze calibration results for fixed-frequency transmon qubits
on a square-lattice chip with fixed couplers.

Your role:
- Interpret experimental results (graphs, parameters, metrics)
- Diagnose potential issues based on the data
- Cross-reference with past cases provided in the "Past cases" section to identify similar patterns or recurring issues
- Provide actionable recommendations
- Explain findings clearly to experimentalists

Always ground your analysis in the provided experimental context.
When discussing results, reference specific parameter values and thresholds.
IMPORTANT: If a "Past cases" section is provided, you MUST discuss those cases in your
analysis. Compare the current result with each past case, noting similarities and
differences. Even if no case exactly matches, explain which case is most relevant and why.

You have access to tools that can fetch data from the calibration database.
When the user asks about parameters or results from other experiments,
use the available tools to retrieve the data rather than saying it's unavailable.
The current qubit context (chip_id, qid) is provided in the system prompt below.

Tool results are returned in JSON format.
Some tools (get_chip_parameter_timeseries, get_chip_summary) store full data
server-side and return only a summary with a `data_key` field.
In execute_python_analysis, access stored data via data["<data_key>"]
(e.g., data["t1"]). Do NOT pass context_data manually.
"""

RESPONSE_FORMAT_INSTRUCTION = """\

You MUST respond with a valid JSON object (no prose, no code fences) matching this schema:
{
  "summary": "One-line result summary",
  "assessment": "good" | "warning" | "bad",
  "explanation": "Detailed analysis and interpretation",
  "potential_issues": ["issue1", "issue2"],
  "recommendations": ["action1", "action2"]
}

Rules:
- `potential_issues` and `recommendations` MUST be JSON arrays of strings. Use an empty array `[]` when nothing applies — never a single string or null.
- `assessment` MUST be exactly one of `good`, `warning`, `bad` (lowercase).
- Write the user-facing text fields (`summary`, `explanation`, items in `potential_issues` and `recommendations`) in the user's response language as instructed above. Keep technical terms like T1, T2, fidelity in English.
- Put the review fields inside `explanation`; do not add extra JSON keys for them.
- Keep `assessment` consistent with the review decision: `good` for `PASS`, `warning` for `PASS_WITH_NOTE` or `REVIEW`, and `bad` for `FAIL`.
- Keep the response concise for interactive use: after the review block, write at most 6 short bullets or 3 short paragraphs in `explanation`, at most 3 potential issues, and at most 3 recommendations.
- Do not add keys outside this schema.
"""


def _build_scoring_threshold_section(scoring: Mapping[str, ScoringThreshold] | None) -> str | None:
    """Render deployment-specific scoring thresholds for prompts."""
    if not scoring:
        return None

    threshold_lines = ["\n## Scoring thresholds (deployment-specific)"]
    for metric, thresh in scoring.items():
        range_parts = []
        if thresh.bad is not None:
            range_parts.append(f"bad < {thresh.bad} {thresh.unit}")
        range_parts.append(f"good > {thresh.good} {thresh.unit}")
        range_parts.append(f"excellent > {thresh.excellent} {thresh.unit}")
        if not thresh.higher_is_better:
            range_parts.append("(lower is better)")
        threshold_lines.append(f"- {metric}: {', '.join(range_parts)}")
    return "\n".join(threshold_lines)


def build_analysis_system_prompt(options: AnalysisPromptOptions) -> str:
    """Build the full system prompt for a chat about a task result."""
    context = options.context
    parts = [ANALYSIS_SYSTEM_PROMPT_BASE, options.language_instruction]

    if options.has_expected_images or options.has_experiment_image:
        img_instructions = ["\n## Image analysis"]
        if options.has_expected_images and options.has_experiment_image:
            img_instructions.append(
                "Reference images showing expected results are provided along with "
                "the actual experimental result image. Compare the actual result with "
                "these references to identify deviations, anomalies, or quality issues."
            )
        elif options.has_expected_images:
            img_instructions.append(
                "Reference images showing expected results are provided. "
                "Use them to understand what a good result looks like for this task."
            )
        elif options.has_experiment_image:
            img_instructions.append(
                "The actual experimental result image is provided. "
                "Analyze the graph/figure for quality, fit accuracy, and anomalies."
            )
        parts.append("\n".join(img_instructions))

    parts.append(context.task_knowledge_prompt)

    scoring_section = _build_scoring_threshold_section(options.scoring)
    if scoring_section:
        parts.append(scoring_section)

    lines = [f"\n## Target: Qubit {context.qid} (Chip: {context.chip_id})"]
    if context.qubit_params:
        lines.append("\n### Current qubit parameters")
        for key, val in context.qubit_params.items():
            if isinstance(val, dict) and "value" in val:
                lines.append(f"- {key}: {val['value']} {val.get('unit', '')}")
            else:
                lines.append(f"- {key}: {val}")
    parts.append("\n".join(lines))

    exp_lines = ["\n## Experiment results"]
    if context.metric_value is not None:
        exp_lines.append(f"**Metric value**: {context.metric_value} {context.metric_unit}")
    if context.r2_value is not None:
        exp_lines.append(f"**Fit R²**: {context.r2_value}")
    if context.recent_values:
        exp_lines.append(f"**Recent values**: {context.recent_values}")
    if context.output_parameters:
        exp_lines.append("\n### Output parameters")
        for key, val in context.output_parameters.items():
            if isinstance(val, dict) and "value" in val:
                exp_lines.append(f"- {key}: {val['value']} {val.get('unit', '')}")
            else:
                exp_lines.append(f"- {key}: {val}")
    if context.run_parameters:
        exp_lines.append("\n### Run parameters")
        for key, val in context.run_parameters.items():
            if isinstance(val, dict) and "value" in val:
                exp_lines.append(f"- {key}: {val['value']} {val.get('unit', '')}")
            else:
                exp_lines.append(f"- {key}: {val}")
    parts.append("\n".join(exp_lines))

    if context.history_results:
        hist_lines = ["\n## Historical results (recent runs)"]
        for i, run in enumerate(context.history_results, 1):
            hist_lines.append(f"\n### Run {i}")
            if run.get("start_at"):
                hist_lines.append(f"- start_at: {run['start_at']}")
            if run.get("execution_id"):
                hist_lines.append(f"- execution_id: {run['execution_id']}")
            for key, val in run.get("output_parameters", {}).items():
                if isinstance(val, dict) and "value" in val:
                    hist_lines.append(f"- {key}: {val['value']} {val.get('unit', '')}")
                else:
                    hist_lines.append(f"- {key}: {val}")
        parts.append("\n".join(hist_lines))

    if context.neighbor_qubit_params:
        nb_lines = ["\n## Neighbor qubit parameters"]
        for nb_qid, params in context.neighbor_qubit_params.items():
            nb_lines.append(f"\n### Qubit {nb_qid}")
            for key, val in params.items():
                if isinstance(val, dict) and "value" in val:
                    nb_lines.append(f"- {key}: {val['value']} {val.get('unit', '')}")
                else:
                    nb_lines.append(f"- {key}: {val}")
        parts.append("\n".join(nb_lines))

    if context.coupling_params:
        cp_lines = ["\n## Coupling parameters"]
        for coupling_id, params in context.coupling_params.items():
            cp_lines.append(f"\n### Coupling {coupling_id}")
            for key, val in params.items():
                if isinstance(val, dict) and "value" in val:
                    cp_lines.append(f"- {key}: {val['value']} {val.get('unit', '')}")
                else:
                    cp_lines.append(f"- {key}: {val}")
        parts.append("\n".join(cp_lines))

    if options.include_response_format:
        parts.append(RESPONSE_FORMAT_INSTRUCTION)

    return "\n\n".join(parts)
