"""Parsing helpers for Copilot LLM responses."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from qdash.copilot.agent_runtime.rendering import legacy_to_blocks
from qdash.copilot.contracts import AnalysisResponse

if TYPE_CHECKING:
    from qdash.copilot.config import CopilotConfig

logger = logging.getLogger(__name__)


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


def parse_response(content: str) -> AnalysisResponse:
    """Parse an LLM answer into AnalysisResponse: its JSON when it is, else as plain text."""
    text = strip_code_fences(content)
    try:
        return AnalysisResponse(**json.loads(text))
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    data = extract_first_json_object(text)
    if data is not None:
        try:
            return AnalysisResponse(**data)
        except ValueError:
            pass
    summary = text.strip().splitlines()[0].strip() if text.strip() else "Analysis complete"
    return AnalysisResponse(
        summary=summary[:200],
        assessment="warning",
        explanation=text.strip(),
        potential_issues=[],
        recommendations=[],
    )


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
