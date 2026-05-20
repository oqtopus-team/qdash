"""Typed models for AI review replay bundles."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from datetime import datetime

    from qdash.copilot.contracts import TaskAnalysisContext


class AIReviewBundleSource(BaseModel):
    """Source task result and trigger metadata for one replay bundle."""

    project_id: str | None = None
    chip_id: str
    qid: str
    task_name: str
    task_id: str
    execution_id: str | None = None
    trigger: Literal["workflow", "chip_page", "bulk_request"]


class AIReviewKnowledgeRef(BaseModel):
    """Reference to the task-knowledge source used to build the prompt/context."""

    repo_url: str | None = None
    commit: str | None = None
    task_path: str | None = None
    task_name: str


class AIReviewModelRef(BaseModel):
    """Compact model metadata stored in replay bundles."""

    provider: str
    name: str
    api_style: str
    temperature: float | None = None
    max_output_tokens: int
    reasoning_effort: str | None = None


class AIReviewBundleInputs(BaseModel):
    """Canonical file layout inside a replay bundle archive."""

    context_path: str = "context.json"
    prompt_path: str = "prompt.txt"
    copilot_config_path: str = "copilot_config.json"
    expected_image_paths: list[str] = Field(default_factory=list)
    experiment_image_paths: list[str] = Field(default_factory=list)
    figure_paths: list[str] = Field(default_factory=list)
    extra_paths: list[str] = Field(default_factory=list)


class AIReviewBundleManifest(BaseModel):
    """Archive manifest for an AI review replay bundle."""

    schema_version: int = 1
    bundle_type: Literal["ai_review_replay"] = "ai_review_replay"
    created_at: datetime
    source: AIReviewBundleSource
    selected_model: AIReviewModelRef
    knowledge: AIReviewKnowledgeRef
    inputs: AIReviewBundleInputs


class AIReviewImageEntry(BaseModel):
    """Embedded image entry written into a replay bundle."""

    path: str
    alt_text: str = ""
    base64_data: str


class AIReviewFigureEntry(BaseModel):
    """External figure file copied into a replay bundle."""

    source_path: str
    archive_path: str


class AIReviewBundleContext(BaseModel):
    """Serialized review context and image payloads for replay."""

    context: TaskAnalysisContext
    image_base64: str | None = None
    experiment_images: list[AIReviewImageEntry] = Field(default_factory=list)
    expected_images: list[AIReviewImageEntry] = Field(default_factory=list)
    figures: list[AIReviewFigureEntry] = Field(default_factory=list)


class AIReviewRuntimeConfig(BaseModel):
    """Triage-relevant subset of Copilot config stored with the bundle."""

    enabled: bool
    response_language: str
    thinking_language: str
    model: AIReviewModelRef
    analysis_model: AIReviewModelRef | None = None
    ai_review_message: str
    max_expected_images: int | None = None
    ai_review_max_expected_images: int | None = None
    ai_review_max_output_tokens: int | None = None


AIReviewBundleManifest.model_rebuild(_types_namespace={"datetime": __import__("datetime").datetime})
AIReviewBundleContext.model_rebuild(
    _types_namespace={
        "TaskAnalysisContext": __import__(
            "qdash.copilot.contracts", fromlist=["TaskAnalysisContext"]
        ).TaskAnalysisContext
    }
)
