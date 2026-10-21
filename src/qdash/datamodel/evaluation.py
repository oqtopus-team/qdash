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

EvaluationStatus = Literal["pending", "running", "completed", "failed", "interrupted", "cancelled"]
EvaluationRunStatus = Literal["running", "completed", "interrupted", "cancelled"]
# Who asked: the chip page for every entity, a person for one task result, or
# the chat planner judging a figure on its own.
EvaluationTrigger = Literal["bulk", "single", "chat"]
# How the evaluation was reached: the two tools run directly, or a planner turn that calls them.
EvaluationMode = Literal["direct", "planner"]
EvaluationVerdictIssue = Literal[
    "parameter_extraction",
    "diagnosis",
    "recommendation",
    "insufficient_evidence",
    "other",
]
# The six QCalEval questions, keyed as pi-qcaleval keys the diagnosis (and as
# the benchmark scripts key their responses). An answer is complete when every
# question asked was answered; by default all six are.
DIAGNOSIS_KEYS: tuple[str, ...] = (
    "technical_description",
    "experimental_conclusion",
    "experimental_significance",
    "fit_reliability",
    "parameter_extraction",
    "calibration_diagnosis",
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
    status: str = Field(default="", description="The status code the example demonstrated")
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
    reference_requested: bool = Field(
        default=True, description="Whether the host attempted to load a task reference"
    )
    reference_used: bool = Field(
        default=False, description="Whether a task reference was actually included in the prompt"
    )
    examples_requested: bool = Field(
        default=False, description="Whether in-context examples were requested"
    )
    examples_used: int = Field(
        default=0, description="Number of in-context examples actually included in the prompt"
    )
    figures: list[EvaluationFigureModel] = Field(default_factory=list)
    examples: list[EvaluationExampleModel] = Field(
        default_factory=list,
        description="Labeled examples shown before the figure; empty for a zero-shot evaluation",
    )


class EvaluationCallModel(BaseModel):
    """One model call made for an answer: how long it took and how it ended."""

    question: str | None = Field(
        default=None, description="The diagnosis question the call asked, when one per call"
    )
    duration_ms: int = Field(..., description="Wall time of the call")
    stop_reason: str = Field(..., description="Why the model stopped, as pi reports it")
    structured: bool = Field(
        default=False, description="Whether the call was constrained to the diagnosis schema"
    )
    input_tokens: int | None = Field(
        default=None, description="Prompt tokens the model counted for the call, images included"
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
    answers: dict[str, str] | None = Field(
        default=None, description="Each answered question's text as the model returned it"
    )
    questions: list[str] = Field(
        default_factory=list,
        description="The questions asked, in order; empty means all six",
    )
    parsed: bool = Field(default=False, description="Whether the answer parsed as the JSON object")
    complete: bool = Field(
        default=False,
        description="Whether the diagnosis answers every question asked (derived)",
    )
    missing_keys: list[str] = Field(
        default_factory=list, description="Questions asked that the diagnosis lacks (derived)"
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
    context_window: int | None = Field(
        default=None,
        description="Context window of the judging model, from the evaluation config when recorded",
    )

    @model_validator(mode="after")
    def _derive_completeness(self) -> "EvaluationOutputModel":
        # Derived from the diagnosis on every load, so records stored before
        # these fields existed carry them too.
        if isinstance(self.diagnosis, dict):
            asked = self.questions or DIAGNOSIS_KEYS
            self.missing_keys = [key for key in asked if key not in self.diagnosis]
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
    issues: list[EvaluationVerdictIssue] = Field(
        default_factory=list, description="Parts of the evaluation the reviewer disputed"
    )
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
