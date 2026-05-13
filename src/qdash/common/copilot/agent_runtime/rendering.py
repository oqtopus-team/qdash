"""Rendering helpers for Copilot LLM responses."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qdash.common.copilot.config import CopilotConfig
    from qdash.common.copilot.contracts import AnalysisResponse

_ASSESSMENT_LABELS_JA = {
    "good": ("✅", "良好"),
    "warning": ("⚠️", "要注意"),
    "warn": ("⚠️", "要注意"),
    "bad": ("❌", "不良"),
    "poor": ("❌", "不良"),
}
_ASSESSMENT_LABELS_EN = {
    "good": ("✅", "Good"),
    "warning": ("⚠️", "Warning"),
    "warn": ("⚠️", "Warning"),
    "bad": ("❌", "Bad"),
    "poor": ("❌", "Bad"),
}

_SECTION_LABELS = {
    "ja": {
        "summary": "概要",
        "explanation": "詳細",
        "issues": "潜在的な問題",
        "recommendations": "推奨アクション",
        "assessment": "評価",
    },
    "en": {
        "summary": "Summary",
        "explanation": "Details",
        "issues": "Potential Issues",
        "recommendations": "Recommendations",
        "assessment": "Assessment",
    },
}


def format_assessment_badge(assessment: str | None, lang: str) -> str:
    """Render a localized assessment badge."""
    if not assessment:
        return ""
    key = assessment.strip().lower()
    table = _ASSESSMENT_LABELS_JA if lang == "ja" else _ASSESSMENT_LABELS_EN
    emoji, label = table.get(key, ("", assessment))
    return f"{emoji} **{label}**".strip()


def legacy_to_blocks(
    response: AnalysisResponse, config: CopilotConfig | None = None
) -> dict[str, Any]:
    """Convert a legacy analysis response into the frontend blocks format."""
    lang_raw = (config.response_language if config else "ja") or "ja"
    lang = "ja" if lang_raw.startswith("ja") else "en"
    labels = _SECTION_LABELS[lang]

    blocks: list[dict[str, Any]] = []

    def _text_block(content: str) -> None:
        if content and content.strip():
            blocks.append({"type": "text", "content": content, "chart": None})

    summary = (response.summary or "").strip()
    explanation = (response.explanation or "").strip()
    normalized_explanation = explanation.lower().lstrip()
    explanation_starts_with_triage = normalized_explanation.startswith(
        ("**review triage**", "review triage", "**レビューのトリアージ**", "レビューのトリアージ")
    )
    if explanation and explanation != summary and explanation_starts_with_triage:
        _text_block(explanation)

    badge = format_assessment_badge(response.assessment, lang)
    if badge or summary:
        header = f"### {labels['assessment']}: {badge}" if badge else ""
        body = summary
        _text_block("\n\n".join(p for p in (header, body) if p))

    if explanation and explanation != summary and not explanation_starts_with_triage:
        _text_block(f"**{labels['explanation']}**\n\n{explanation}")

    issues = [i for i in response.potential_issues if i and str(i).strip()]
    if issues:
        issue_lines = "\n".join(f"- {issue}" for issue in issues)
        _text_block(f"**{labels['issues']}**\n\n{issue_lines}")

    recs = [r for r in response.recommendations if r and str(r).strip()]
    if recs:
        rec_lines = "\n".join(f"- {rec}" for rec in recs)
        _text_block(f"**{labels['recommendations']}**\n\n{rec_lines}")

    if not blocks:
        fallback = explanation or summary or ""
        blocks.append({"type": "text", "content": fallback, "chart": None})

    return {"blocks": blocks, "assessment": response.assessment}


def build_llm_summary(full_result: dict[str, Any], data_key: str) -> dict[str, Any]:
    """Replace large arrays with lightweight summaries before returning to the LLM."""
    summary: dict[str, Any] = {}
    for key, value in full_result.items():
        if isinstance(value, list):
            if value and isinstance(value[0], dict):
                summary[key] = {"_schema": list(value[0].keys()), "_rows": len(value)}
            else:
                summary[key] = {"_rows": len(value)}
        else:
            summary[key] = value
    summary["data_key"] = data_key
    summary["_note"] = (
        f"Full data available as data['{data_key}'] in execute_python_analysis. "
        f"Do NOT pass data manually."
    )
    return summary
