"""Models for the copilot task analysis feature.

Defines the structured context sent to the LLM and the expected response format.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TaskAnalysisContext(BaseModel):
    """Full context for LLM-based task result analysis.

    Constructed by the analysis endpoint from DB data and TaskKnowledge,
    then injected into the Pydantic AI agent as ``deps``.
    """

    # Task knowledge (pre-rendered prompt)
    task_knowledge_prompt: str = Field(description="Markdown text from TaskKnowledge.to_prompt()")

    # Qubit / coupling identity
    chip_id: str
    qid: str

    # Current qubit parameters from QubitModel.data
    qubit_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Current qubit parameters (frequency, T1, T2, etc.)",
    )

    # Experiment parameters
    input_parameters: dict[str, Any] = Field(default_factory=dict)
    output_parameters: dict[str, Any] = Field(default_factory=dict)
    run_parameters: dict[str, Any] = Field(default_factory=dict)

    # Result summary
    metric_value: float | None = None
    metric_unit: str = ""
    r2_value: float | None = None

    # Historical trend (most recent values for this metric)
    recent_values: list[float] = Field(
        default_factory=list,
        description="Recent metric values for trend analysis",
    )

    # Dynamic context from TaskKnowledge.related_context
    history_results: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Recent completed runs: [{output_parameters, start_at, execution_id}]",
    )
    neighbor_qubit_params: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Neighbor qubit parameters: {qid: {param: value}}",
    )
    coupling_params: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Coupling parameters: {coupling_id: {param: value}}",
    )


class AnalysisResponse(BaseModel):
    """Structured analysis returned by the LLM."""

    summary: str = Field(description="One-line result summary")
    assessment: str = Field(description="Overall assessment: good / warning / bad")
    explanation: str = Field(description="Detailed analysis and interpretation")
    potential_issues: list[str] = Field(
        default_factory=list,
        description="Detected potential issues",
    )
    recommendations: list[str] = Field(
        default_factory=list,
        description="Recommended next actions",
    )


class ContentBlock(BaseModel):
    """A single content block in a blocks response."""

    type: str = Field(description="Block type: 'text' or 'chart'")
    content: str | None = Field(default=None, description="Text content (for text blocks)")
    chart: dict[str, Any] | None = Field(
        default=None,
        description="Plotly chart spec with 'data' and 'layout' keys (for chart blocks)",
    )


class BlocksAnalysisResponse(BaseModel):
    """Extended analysis response with mixed text/chart content blocks."""

    blocks: list[ContentBlock] = Field(description="Ordered list of content blocks")
    assessment: str | None = Field(
        default=None,
        description="Overall assessment: good / warning / bad / null",
    )


class AnalyzeRequest(BaseModel):
    """Request body for POST /copilot/analyze."""

    task_name: str = Field(description="Task class name (e.g. CheckT1)")
    chip_id: str
    qid: str
    execution_id: str
    task_id: str
    message: str = Field(description="User question / message")
    image_base64: str | None = Field(
        default=None,
        description="Base64-encoded result figure (for multimodal analysis)",
    )
    conversation_history: list[dict[str, str]] = Field(
        default_factory=list,
        description="Previous conversation messages [{role, content}, ...]",
    )


class ChatRequest(BaseModel):
    """Request body for POST /copilot/chat/stream."""

    message: str = Field(description="User question / message")
    chip_id: str | None = None
    qid: str | None = None
    conversation_history: list[dict[str, str]] = Field(
        default_factory=list,
        description="Previous conversation messages [{role, content}, ...]",
    )
    image_base64: str | None = None
