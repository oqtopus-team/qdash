"""Data models for calibration evaluations judged by the evaluation model.

One evaluation is a snapshot of a single `qcal_evaluate` call made without a
planner: what the evaluation model saw (evidence context, reference, figure
hashes, the exact prompt), what it answered, which model and extension version
answered, and the human verdict added afterwards. Runs group the evaluations
one bulk request produced so that two runs over the same task results can be
compared.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

EvaluationStatus = Literal["pending", "running", "completed", "failed"]
EvaluationRunStatus = Literal["running", "completed"]
# Who asked: the chip page for every entity, or a person for one task result.
EvaluationTrigger = Literal["bulk", "single"]
# How the evaluation was reached: the two tools run directly, or a planner turn that calls them.
EvaluationMode = Literal["direct", "planner"]


class EvaluationFigureModel(BaseModel):
    """One figure the evaluation model saw, by hash rather than by bytes."""

    sha256: str = Field(..., description="SHA-256 of the decoded image bytes")
    mime_type: str = Field(..., description="Image media type")
    bytes: int = Field(..., description="Decoded image size in bytes")


class EvaluationInputModel(BaseModel):
    """What the evaluation model was given."""

    context: str = Field(..., description="Evidence text passed as the experiment context")
    prompt: str | None = Field(
        default=None, description="The exact user turn sent to the evaluation model"
    )
    question: str | None = Field(default=None, description="Specific question, when one was asked")
    knowledge_chars: int | None = Field(
        default=None, description="Length of the host-supplied reference, when one was found"
    )
    knowledge_sha256: str | None = Field(
        default=None, description="SHA-256 of the host-supplied reference text"
    )
    figures: list[EvaluationFigureModel] = Field(default_factory=list)


class EvaluationOutputModel(BaseModel):
    """What the evaluation model answered."""

    model: str | None = Field(default=None, description="provider/modelId that judged the plot")
    fallback: bool = Field(
        default=False,
        description="True when no calibration VLM was configured and another model judged",
    )
    diagnosis: dict[str, Any] | None = Field(
        default=None, description="The parsed JSON diagnosis, when the answer was JSON"
    )
    raw: str | None = Field(default=None, description="The answer text when it was not JSON")
    parsed: bool = Field(default=False, description="Whether the answer parsed as the JSON object")
    duration_ms: int = Field(default=0, description="Wall time of the model call")
    usage: dict[str, Any] | None = Field(default=None, description="Token usage, as pi reports it")


class EvaluatorModel(BaseModel):
    """The extension that produced the evaluation."""

    name: str = Field(..., description="Package name, e.g. @orangekame3/pi-qcaleval")
    version: str = Field(..., description="Package version from its manifest")
    source: str = Field(..., description='"checkout" (mounted) or "package" (pinned install)')
    commit: str | None = Field(default=None, description="Checkout HEAD commit, when known")


class EvaluationVerdictModel(BaseModel):
    """A person's judgement of one evaluation, the ground truth for comparing runs."""

    agree: bool | None = Field(
        default=None,
        description="True when the person agrees with the evaluation, False when not, None to clear",
    )
    note: str | None = Field(default=None, description="Why, in the person's words")
    username: str = Field(..., description="Who judged")
    updated_at: datetime = Field(..., description="When the verdict was last changed")


class EvaluationPlannerModel(BaseModel):
    """What the planner did around the evaluation, in planner mode."""

    model: str = Field(..., description="provider/modelId of the planner")
    answer: str = Field(default="", description="The planner's final answer")
    tool_calls: list[str] = Field(
        default_factory=list, description="Tools the planner called, in order"
    )
    duration_ms: int = Field(default=0, description="Wall time of the whole planner turn")
