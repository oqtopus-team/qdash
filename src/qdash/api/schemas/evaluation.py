"""Schema definitions for calibration evaluation runs."""

from datetime import datetime

from pydantic import BaseModel, Field

from qdash.datamodel.evaluation import (
    EvaluationInputModel,
    EvaluationMode,
    EvaluationOutputModel,
    EvaluationPlannerModel,
    EvaluationRunStatus,
    EvaluationStatus,
    EvaluationTrigger,
    EvaluationVerdictModel,
    EvaluatorModel,
)


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
    question: str | None = Field(
        default=None,
        max_length=2000,
        description="A specific question for the evaluation model, on top of the diagnosis",
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


class EvaluationRunSummary(BaseModel):
    """One run with its progress and agreement counts."""

    run_id: str
    chip_id: str
    task_name: str
    entity_type: str
    date: str | None = None
    question: str | None = None
    trigger: EvaluationTrigger
    mode: EvaluationMode
    with_examples: bool = False
    planner_model: str | None = None
    requested_by: str
    requested_at: datetime
    completed_at: datetime | None = None
    status: EvaluationRunStatus
    total: int
    completed_count: int
    failed_count: int
    pending_count: int = Field(..., description="Evaluations not finished yet")
    parsed_count: int = Field(..., description="Completed evaluations whose answer was JSON")
    success_count: int = Field(
        ..., description="Completed evaluations whose diagnosis reports success"
    )
    agree_count: int = Field(..., description="Evaluations a person agreed with")
    disagree_count: int = Field(..., description="Evaluations a person disagreed with")
    model: str | None = None
    evaluator: EvaluatorModel | None = None


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
