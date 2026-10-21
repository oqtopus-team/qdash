"""Schema definitions for calibration evaluation runs."""

from datetime import datetime

from pydantic import BaseModel, Field

from qdash.api.schemas.task import TaskReferenceResponse
from qdash.datamodel.evaluation import (
    EvaluationInputModel,
    EvaluationMode,
    EvaluationOutputModel,
    EvaluationPlannerModel,
    EvaluationRunStatus,
    EvaluationStatus,
    EvaluationTrigger,
    EvaluationVerdictIssue,
    EvaluationVerdictModel,
    EvaluatorModel,
)


class EvaluationModelSelection(BaseModel):
    """A configured model selected to judge calibration figures."""

    provider: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)


class CreateEvaluationRunRequest(BaseModel):
    """Evaluate the latest result of one task for every entity on a chip."""

    chip_id: str = Field(..., description="Chip ID")
    task: str = Field(..., description="Calibration task name")
    entity_type: str = Field(default="qubit", description='"qubit" or "coupling"')
    date: str | None = Field(
        default=None,
        description="YYYYMMDD to evaluate that day's results instead of the latest ones",
    )
    task_ids: list[str] | None = Field(
        default=None, description="Restrict the run to these task results"
    )
    qids: list[str] | None = Field(
        default=None,
        description="Restrict the run to the latest results of these qubits or couplings",
    )
    knowledge_draft_id: str | None = Field(
        default=None,
        description="Evaluate against this uploaded knowledge draft instead of the shared knowledge",
    )
    trigger: EvaluationTrigger = Field(
        default="bulk", description='"bulk" from the chip page, "single" for one task result'
    )
    with_examples: bool = Field(
        default=False,
        description="Show the task's expert-labeled example plots before the figure (in-context examples)",
    )
    mode: EvaluationMode = Field(
        default="direct",
        description='"direct" runs the evaluation tools; "planner" lets the chat planner call them',
    )
    evaluation_model: EvaluationModelSelection | None = Field(
        default=None,
        description="Configured evaluation model to use; defaults to evaluation_models[0]",
    )


class EvaluationRunSummary(BaseModel):
    """One run with its progress and agreement counts."""

    run_id: str
    chip_id: str
    task_name: str
    entity_type: str
    date: str | None = None
    question: str | None = None
    knowledge_draft_id: str | None = Field(
        default=None, description="The uploaded knowledge draft the run used, if any"
    )
    knowledge_draft_name: str | None = Field(
        default=None, description="File name of that draft's zip"
    )
    trigger: EvaluationTrigger
    mode: EvaluationMode
    with_examples: bool = False
    planner_model: str | None = None
    evaluation_model: str | None = Field(
        default=None, description="Configured provider/modelId requested for every evaluation"
    )
    requested_by: str
    requested_at: datetime
    completed_at: datetime | None = None
    status: EvaluationRunStatus
    total: int
    completed_count: int
    failed_count: int
    interrupted_count: int = Field(default=0, description="Evaluations interrupted by worker loss")
    cancelled_count: int = Field(default=0, description="Evaluations cancelled by a user")
    pending_count: int = Field(..., description="Evaluations not finished yet")
    parsed_count: int = Field(..., description="Completed evaluations whose answer was JSON")
    complete_count: int = Field(
        ..., description="Completed evaluations whose diagnosis carries all six keys"
    )
    elapsed_ms: int | None = Field(
        default=None, description="Wall time from the request to the run's completion"
    )
    duration_ms_total: int = Field(
        ..., description="Wall time of the completed evaluations' model calls, added up"
    )
    success_count: int = Field(
        ..., description="Completed evaluations whose diagnosis reports success"
    )
    agree_count: int = Field(..., description="Evaluations a person agreed with")
    disagree_count: int = Field(..., description="Evaluations a person disagreed with")
    reference_used_count: int = Field(
        default=0, description="Completed evaluations that actually used a task reference"
    )
    examples_used_count: int = Field(
        default=0, description="Completed evaluations that actually used in-context examples"
    )
    model: str | None = None
    models: list[str] = Field(
        default_factory=list, description="All evaluation models represented in the run"
    )
    evaluator: EvaluatorModel | None = None
    evaluators: list[EvaluatorModel] = Field(
        default_factory=list, description="All evaluator builds represented in the run"
    )


class EvaluationItem(BaseModel):
    """One evaluation of one task result."""

    evaluation_id: str
    run_id: str
    task_id: str
    task_name: str
    qid: str
    execution_id: str
    figure_path: list[str] = Field(
        default_factory=list, description="The task result's figures, for display"
    )
    json_figure_path: list[str] = Field(default_factory=list)
    status: EvaluationStatus
    requested_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    input: EvaluationInputModel | None = None
    output: EvaluationOutputModel | None = None
    evaluator: EvaluatorModel | None = None
    planner: EvaluationPlannerModel | None = None
    verdict: EvaluationVerdictModel | None = None
    verdicts: list[EvaluationVerdictModel] = Field(
        default_factory=list, description="Current verdict from each reviewer"
    )
    verdict_history: list[EvaluationVerdictModel] = Field(
        default_factory=list, description="Immutable verdict changes"
    )


class CreateEvaluationRunResponse(BaseModel):
    """The run that was started and what it covers."""

    run: EvaluationRunSummary
    task_ids: list[str] = Field(..., description="Task results queued for evaluation")
    skipped: dict[str, str] = Field(
        default_factory=dict, description="Entities not queued, by id, with the reason"
    )


class ListEvaluationRunsResponse(BaseModel):
    """Runs, newest first."""

    runs: list[EvaluationRunSummary]


class EvaluationRunDetailResponse(BaseModel):
    """One run with every evaluation in it."""

    run: EvaluationRunSummary
    evaluations: list[EvaluationItem]


class ListEvaluationsResponse(BaseModel):
    """Evaluations of one task result, newest first."""

    evaluations: list[EvaluationItem]


class SetEvaluationVerdictRequest(BaseModel):
    """A person's judgement of one evaluation."""

    agree: bool | None = Field(
        ..., description="True to agree, False to disagree, null to clear the verdict"
    )
    note: str | None = Field(default=None, max_length=2000, description="Why")
    issues: list[EvaluationVerdictIssue] = Field(
        default_factory=list, description="Parts of the evaluation that are wrong"
    )


class RetryEvaluationRunResponse(BaseModel):
    """A run reset for another attempt."""

    run: EvaluationRunSummary
    retried: int


class KnowledgeDraftResponse(BaseModel):
    """An uploaded task-knowledge draft and what an evaluation would read from it."""

    draft_id: str = Field(..., description="SHA-256 of the uploaded zip")
    task_name: str = Field(..., description="The task the draft describes (its H1)")
    filename: str
    uploaded_by: str
    created_at: datetime
    warnings: list[str] = Field(
        default_factory=list, description="What the knowledge repository's generator warned about"
    )
    reference: TaskReferenceResponse = Field(
        ..., description="The background and criteria the evaluation model would get"
    )
    example_count: int = Field(..., description="Labeled examples the draft holds")
    figure_count: int = Field(..., description="Figures of task.md and the examples")
