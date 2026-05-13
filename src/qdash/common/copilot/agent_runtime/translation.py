"""Translation helpers for Copilot analysis responses."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from openai import BadRequestError

from qdash.common.copilot.agent_runtime.client import build_client
from qdash.common.copilot.agent_runtime.parsing import strip_code_fences

if TYPE_CHECKING:
    from qdash.common.copilot.config import ModelConfig
    from qdash.common.copilot.contracts import AnalysisResponse

from qdash.common.copilot.config import CopilotConfig

logger = logging.getLogger(__name__)

_LANG_FULLNAME = {"ja": "Japanese (日本語)", "en": "English"}


def looks_like_target_language(text: str, lang: str) -> bool:
    """Cheap heuristic: does text already look like the target language."""
    if not text:
        return True
    if lang == "ja":
        return any("\u3040" <= ch <= "\u30ff" or "\u4e00" <= ch <= "\u9fff" for ch in text)
    if lang == "en":
        return all(ord(ch) < 0x3000 for ch in text)
    return True


async def translate_analysis_response(
    response: AnalysisResponse,
    target_lang: str,
    general_model: ModelConfig,
) -> AnalysisResponse:
    """Translate an AnalysisResponse via the general model when needed."""
    lang_key = "ja" if target_lang.startswith("ja") else "en"
    fields_needing = []
    if response.summary and not looks_like_target_language(response.summary, lang_key):
        fields_needing.append("summary")
    if response.explanation and not looks_like_target_language(response.explanation, lang_key):
        fields_needing.append("explanation")
    if any(i and not looks_like_target_language(i, lang_key) for i in response.potential_issues):
        fields_needing.append("potential_issues")
    if any(r and not looks_like_target_language(r, lang_key) for r in response.recommendations):
        fields_needing.append("recommendations")

    if not fields_needing:
        return response

    lang_name = _LANG_FULLNAME.get(lang_key, target_lang)
    payload = {
        "summary": response.summary or "",
        "explanation": response.explanation or "",
        "potential_issues": list(response.potential_issues),
        "recommendations": list(response.recommendations),
    }
    system = (
        f"You translate technical quantum-calibration analysis into natural, fluent {lang_name}. "
        "Preserve all numeric values, units, and technical terms like T1, T2, fidelity, Rabi, "
        "R², π-pulse, I/Q in their original form. Keep the same JSON shape. "
        "Do not add, remove, or reinterpret content — only translate."
    )
    user = (
        "Translate the string values in this JSON into "
        f"{lang_name}. Return a JSON object with the SAME keys and array lengths.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )

    try:
        translator_config = CopilotConfig(model=general_model)
        client = build_client(translator_config)
        kwargs: dict[str, Any] = {
            "model": general_model.name,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        if general_model.temperature is not None:
            kwargs["temperature"] = 0.2
        try:
            completion = await client.chat.completions.create(**kwargs)
        except BadRequestError as exc:
            if "temperature" in str(exc):
                kwargs.pop("temperature", None)
                completion = await client.chat.completions.create(**kwargs)
            else:
                raise
        content = completion.choices[0].message.content or "{}"
        data = json.loads(strip_code_fences(content))
    except Exception as exc:
        logger.warning("Translation to %s failed, using original text: %s", lang_key, exc)
        return response

    def _coerce_list(val: Any, fallback: list[str]) -> list[str]:
        if isinstance(val, list):
            return [str(x) for x in val if x]
        if isinstance(val, str) and val:
            return [val]
        return fallback

    return response.model_copy(
        update={
            "summary": str(data.get("summary") or response.summary),
            "explanation": str(data.get("explanation") or response.explanation),
            "potential_issues": _coerce_list(
                data.get("potential_issues"), list(response.potential_issues)
            ),
            "recommendations": _coerce_list(
                data.get("recommendations"), list(response.recommendations)
            ),
        }
    )
