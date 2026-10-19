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

from pydantic import BaseModel, Field, model_validator

EvaluationStatus = Literal["pending", "running", "completed", "failed"]
EvaluationRunStatus = Literal["running", "completed"]
# Who asked: the chip page for every entity, a person for one task result, or
# the chat planner judging a figure on its own.
EvaluationTrigger = Literal["bulk", "single", "chat"]
# How the evaluation was reached: the two tools run directly, or a planner turn that calls them.
EvaluationMode = Literal["direct", "planner"]
# The keys of a diagnosis, as pi-qcaleval asks the evaluation model for them.
# An answer is complete when it carries all six.
DIAGNOSIS_KEYS: tuple[str, ...] = (
    "technical_description",
    "experimental_conclusion",
    "experimental_significance",
    "fit_quality",
    "parameter_extraction",
    "success",
)


class EvaluationFigureModel(BaseModel):
    """One figure the evaluation model saw, by hash rather than by bytes."""

    sha256: str = Field(..., description="SHA-256 of the decoded image bytes")
    mime_type: str = Field(..., description="Image media type")
    bytes: int = Field(..., description="Decoded image size in bytes")
    path: str | None = Field(
        default=None, description="Path in the knowledge repository, for an example figure"
    )


class EvaluationExampleModel(BaseModel):
    """One labeled example shown before the figure, by identity and figure hashes."""

    id: str = Field(default="", description="Example file stem in the knowledge repository")
    title: str = Field(default="")
    outcome: str = Field(default="", description="The example's labeled outcome")
    figures: list[EvaluationFigureModel] = Field(default_factory=list)


class EvaluationInputModel(BaseModel):
    """What the evaluation model was given."""

    context: str = Field(..., description="Evidence text passed as the experiment context")
    prompt: str | None = Field(
        default=None,
        description="The exact user turn sent to the evaluation model; [figure] marks an image",
    )
    system_prompt: str | None = Field(
        default=None, description="The system prompt sent to the evaluation model"
    )
    question: str | None = Field(default=None, description="Specific question, when one was asked")
    knowledge_chars: int | None = Field(
        default=None, description="Length of the host-supplied reference, when one was found"
    )
    knowledge_sha256: str | None = Field(
        default=None, description="SHA-256 of the host-supplied reference text"
    )
    figures: list[EvaluationFigureModel] = Field(default_factory=list)
    examples: list[EvaluationExampleModel] = Field(
        default_factory=list,
        description="Labeled examples shown before the figure; empty for a zero-shot evaluation",
    )


class EvaluationCallModel(BaseModel):
    """One model call made for an answer: how long it took and how it ended."""

    duration_ms: int = Field(..., description="Wall time of the call")
    stop_reason: str = Field(..., description="Why the model stopped, as pi reports it")
    structured: bool = Field(
        default=False, description="Whether the call was constrained to the diagnosis schema"
    )
    output_tokens: int | None = Field(default=None, description="Output tokens of the call")
    missing_keys: list[str] = Field(
        default_factory=list, description="Diagnosis keys the call's answer lacked"
    )


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
    raw: str | None = Field(
        default=None,
        description="The answer text when it was not JSON, or not all of the diagnosis",
    )
    parsed: bool = Field(default=False, description="Whether the answer parsed as the JSON object")
    complete: bool = Field(
        default=False, description="Whether the diagnosis carries all six keys (derived)"
    )
    missing_keys: list[str] = Field(
        default_factory=list, description="Diagnosis keys the parsed answer lacks (derived)"
    )
    attempts: int | None = Field(
        default=None, description="Model calls made for the answer: 1, or 2 after an incomplete one"
    )
    structured: bool | None = Field(
        default=None, description="Whether decoding was constrained to the diagnosis schema"
    )
    stop_reason: str | None = Field(
        default=None, description="Why the model stopped, as pi reports it"
    )
    calls: list[EvaluationCallModel] = Field(
        default_factory=list,
        description="Every model call made for the answer, in order, when the evaluator reports them",
    )
    duration_ms: int = Field(
        default=0, description="Wall time of the evaluation call, every model call included"
    )
    usage: dict[str, Any] | None = Field(default=None, description="Token usage, as pi reports it")

    @model_validator(mode="after")
    def _derive_completeness(self) -> "EvaluationOutputModel":
        # Derived from the diagnosis on every load, so records stored before
        # these fields existed carry them too.
        if isinstance(self.diagnosis, dict):
            self.missing_keys = [key for key in DIAGNOSIS_KEYS if key not in self.diagnosis]
        else:
            self.missing_keys = []
        self.complete = isinstance(self.diagnosis, dict) and not self.missing_keys
        return self


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
