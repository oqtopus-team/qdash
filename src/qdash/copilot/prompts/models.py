"""Pydantic models for Copilot prompt-builder boundaries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from qdash.copilot.config import ScoringThreshold
    from qdash.copilot.contracts import TaskAnalysisContext


class AnalysisPromptOptions(BaseModel):
    """Normalized inputs for rendering a task-analysis system prompt."""

    context: TaskAnalysisContext
    language_instruction: str
    scoring: dict[str, ScoringThreshold] = Field(default_factory=dict)
    include_response_format: bool = False
    has_expected_images: bool = False
    has_experiment_image: bool = False


class ChatPromptContext(BaseModel):
    """Normalized inputs for rendering a generic chat system prompt."""

    language_instruction: str
    scoring: dict[str, ScoringThreshold] = Field(default_factory=dict)
    chip_id: str | None = None
    qid: str | None = None
    qubit_params: dict[str, Any] = Field(default_factory=dict)


def _rebuild_models() -> None:
    from qdash.copilot.config import ScoringThreshold as _ScoringThreshold
    from qdash.copilot.contracts import TaskAnalysisContext as _TaskAnalysisContext

    namespace = {
        "TaskAnalysisContext": _TaskAnalysisContext,
        "ScoringThreshold": _ScoringThreshold,
    }
    AnalysisPromptOptions.model_rebuild(_types_namespace=namespace)
    ChatPromptContext.model_rebuild(_types_namespace=namespace)


_rebuild_models()
