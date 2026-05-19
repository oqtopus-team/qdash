"""Prompt builders for task-result analysis and AI review flows."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from qdash.copilot.config import ScoringThreshold
    from qdash.copilot.prompts.models import AnalysisPromptOptions

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

AI_REVIEW_INSTRUCTION = """\
## AI review output

When answering about a calibration task result, begin your first text block with
a short AI review summary before the detailed explanation. Keep it concise
and use the following markdown shape:

**AI review**
- Decision: `PASS` | `PASS_WITH_NOTE` | `REVIEW` | `FAIL`
- Human label suggestion: `CORRECT` | `SUSPICIOUS` | `MISASSIGNMENT` | `NO_SIGNAL` | `ANOMALY`
- Accepted parameter(s): parameter names and values that are well supported, or `none`
- Needs review: parameter names and values that are weak, ambiguous, or risky, or `none`
- Primary reason: one short sentence grounded in the plot/data
- Closest knowledge case: case title or `none`
- Suggested labels: comma-separated labels such as `weak_signal`, `boundary_case`, `model_overconservative`, `model_missed_issue`, or `none`
- Recommended action: one short operator action
- Optional note: one short caveat only when useful, otherwise `none`

For reliable parsing, the JSON `explanation` string MUST start exactly with
`**AI review**`. Every review field line MUST begin with hyphen-space
(`- `). Do not omit the hyphens, do not bold the field names, and do not put
ordinary prose before the review block. Use this exact skeleton before any
detailed explanation:

**AI review**
- Decision: `PASS` | `PASS_WITH_NOTE` | `REVIEW` | `FAIL`
- Human label suggestion: `CORRECT` | `SUSPICIOUS` | `MISASSIGNMENT` | `NO_SIGNAL` | `ANOMALY`
- Accepted parameter(s): ...
- Needs review: ...
- Primary reason: ...
- Closest knowledge case: ...
- Suggested labels: ...
- Recommended action: ...
- Optional note: ...

Keep the review fields internally consistent:
- Use `PASS` only when all important output parameters are visually and physically supported.
  For `PASS`, set `Needs review: none`, `Suggested labels: none`, and make the recommended
  action an accept/use action rather than a remeasurement action.
- Use `PASS_WITH_NOTE` only when all output parameters that would be updated are
  acceptable without human intervention, but there is a minor caveat or optional
  follow-up. Put non-blocking caveats in `Optional note`, not in `Needs review`.
- Use `REVIEW` when any important output parameter should not be auto-accepted without a
  human check. If you use labels such as `weak_signal`, `boundary_case`, `ambiguous_doublet`,
  or `frequency_offset` for a parameter that affects acceptance, prefer `REVIEW`.
- If the detailed explanation says a parameter should be treated cautiously, maintained
  from history, not overwritten, rechecked before update, or used only as a reference value,
  then that parameter MUST appear in `Needs review` and the decision MUST be `REVIEW`.
- Do not set `Needs review: none` if the recommended action includes rechecking,
  maintaining, withholding, or not overwriting any output parameter.
- In `Accepted parameter(s)`, list only parameters you would allow the workflow to update
  automatically from this result. If a parameter is plausible but not update-safe, put it
  in `Needs review`, not in `Accepted parameter(s)`.
- Use `FAIL` for no visible signal, clear misassignment, measurement failure, or anomaly.
- Assessment consistency: set the top-level assessment to `good` for `PASS`,
  `warning` for `PASS_WITH_NOTE` or `REVIEW`, and `bad` for `FAIL`.

Then continue with the detailed explanation. In the detailed explanation:
- Separate visual support for each key parameter instead of giving one blended confidence.
- If f01/f12, resonator/Purcell, or similar paired features are involved, evaluate each feature independently.
- Use past cases as operational knowledge: state which case is closest, which lessons apply, and which lessons do not apply.
- Avoid overclaiming from visual plausibility alone; distinguish "visually supported", "plausible from history/physics", and "needs review".
- End with action-oriented recommendations that an operator can execute.
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
- The `explanation` field MUST begin with the exact AI review markdown described above, starting with `**AI review**`.
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
    """Build the full system prompt for task analysis and AI review."""
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
    parts.append(AI_REVIEW_INSTRUCTION)

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
