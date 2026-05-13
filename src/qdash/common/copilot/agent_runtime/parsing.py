"""Parsing helpers for Copilot LLM responses."""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

from qdash.common.copilot.agent_runtime.rendering import legacy_to_blocks
from qdash.common.copilot.contracts import AnalysisResponse

if TYPE_CHECKING:
    from qdash.common.copilot.config import CopilotConfig

logger = logging.getLogger(__name__)

_TRIAGE_DECISIONS = ("PASS_WITH_NOTE", "PASS", "REVIEW", "FAIL")
_TRIAGE_ASSESSMENT = {
    "PASS": "good",
    "PASS_WITH_NOTE": "warning",
    "REVIEW": "warning",
    "FAIL": "bad",
}
_TRIAGE_BLOCK_PREFIXES = (
    "**review triage**",
    "review triage",
    "**レビューのトリアージ**",
    "レビューのトリアージ",
)


def strip_code_fences(text: str) -> str:
    """Remove markdown code fences from text."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text


def extract_triage_fallback(content: str) -> AnalysisResponse | None:
    """Build a legacy response from a free-form review triage block."""
    fields = {
        "Decision": "",
        "Human label suggestion": "",
        "Accepted parameter(s)": "",
        "Needs review": "",
        "Primary reason": "",
        "Closest knowledge case": "",
        "Suggested labels": "",
        "Recommended action": "",
        "Optional note": "",
    }
    for field in fields:
        match = re.search(rf"^\s*[-*]\s+{re.escape(field)}:\s*(.*)$", content, re.M)
        if not match:
            continue
        value = match.group(1).strip().strip("`")
        if field == "Decision":
            for decision in _TRIAGE_DECISIONS:
                if re.search(rf"\b{decision}\b", value):
                    value = decision
                    break
        fields[field] = value

    decision = fields["Decision"]
    if not decision:
        return None

    triage = "\n".join(
        ["**Review triage**", *(f"- {field}: {value or 'none'}" for field, value in fields.items())]
    )
    return AnalysisResponse(
        summary=fields["Primary reason"] or "Analysis complete",
        assessment=_TRIAGE_ASSESSMENT.get(decision, "warning"),
        explanation=triage,
        potential_issues=[]
        if decision in {"PASS", "PASS_WITH_NOTE"}
        else [fields["Primary reason"]],
        recommendations=[fields["Recommended action"]] if fields["Recommended action"] else [],
    )


def has_triage_block(text: str) -> bool:
    """Return True when text starts with the required review-triage block."""
    return text.lower().lstrip().startswith(_TRIAGE_BLOCK_PREFIXES)


def missing_triage_response(_content: str) -> AnalysisResponse:
    """Return a safe review note when a local model omits required triage fields."""
    summary = "AI triage response did not include the required review block."
    triage = "\n".join(
        [
            "**Review triage**",
            "- Decision: `REVIEW`",
            "- Human label suggestion: `SUSPICIOUS`",
            "- Accepted parameter(s): `none`",
            "- Needs review: `all output parameters`",
            f"- Primary reason: {summary}",
            "- Closest knowledge case: `none`",
            "- Suggested labels: `model_format_error`",
            "- Recommended action: Open the task result and review the plot manually.",
            "- Optional note: The raw local-model response was missing the triage block.",
        ]
    )
    return AnalysisResponse(
        summary=summary,
        assessment="warning",
        explanation=triage,
        potential_issues=[summary],
        recommendations=["Open the task result and review the plot manually."],
    )


def parse_response(content: str) -> AnalysisResponse:
    """Parse LLM response into AnalysisResponse, handling JSON and plain text."""
    text = strip_code_fences(content)

    try:
        data = json.loads(text)
        response = AnalysisResponse(**data)
        if response.explanation and has_triage_block(response.explanation):
            return response
        fallback_response = extract_triage_fallback(response.explanation or content)
        if fallback_response is not None:
            return fallback_response
        logger.warning("Local model response omitted required review triage block: %s", content)
        return missing_triage_response(content)
    except (json.JSONDecodeError, ValueError):
        fallback_response = extract_triage_fallback(content)
        if fallback_response is not None:
            return fallback_response
        logger.warning("Local model response omitted required review triage block: %s", content)
        return missing_triage_response(content)


def extract_first_json_object(text: str) -> dict[str, Any] | None:
    """Scan text for the first balanced JSON object and parse it."""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
                    if isinstance(parsed, dict):
                        return parsed
                    break
        start = text.find("{", start + 1)
    return None


def has_real_blocks(parsed: dict[str, Any]) -> bool:
    """Return True when the parsed BLOCKS payload came from real JSON output."""
    blocks = parsed.get("blocks") if isinstance(parsed, dict) else None
    if not isinstance(blocks, list):
        return False
    if len(blocks) != 1:
        return True
    return parsed.get("assessment") is not None


def parse_blocks_response(content: str, config: CopilotConfig | None = None) -> dict[str, Any]:
    """Parse LLM response into blocks format dict, with fallback to legacy."""
    text = strip_code_fences(content)

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        data = extract_first_json_object(text)

    if isinstance(data, dict):
        if "blocks" in data and isinstance(data["blocks"], list):
            return dict(data)
        try:
            response = AnalysisResponse(**data)
            return legacy_to_blocks(response, config)
        except ValueError:
            pass

    return {
        "blocks": [{"type": "text", "content": content, "chart": None}],
        "assessment": None,
    }
