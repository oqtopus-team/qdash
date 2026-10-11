"""Document model for one calibration evaluation of one task result."""

from datetime import datetime
from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from qdash.common.utils.datetime import now
from qdash.datamodel.evaluation import (
    EvaluationInputModel,
    EvaluationOutputModel,
    EvaluationPlannerModel,
    EvaluationStatus,
    EvaluationVerdictModel,
    EvaluatorModel,
)


class EvaluationDocument(Document):
    """A snapshot of one `qcal_evaluate` call and the human verdict on it.

    Input and output are stored as the runtime reported them, so the record
    stands on its own after the extension, model or task knowledge changes.
    """

    evaluation_id: str = Field(..., description="Evaluation identifier (ev_<hex>)")
    run_id: str = Field(..., description="Run this evaluation belongs to")
    project_id: str = Field(..., description="Owning project identifier")
    chip_id: str = Field(..., description="Chip of the task result")
    task_id: str = Field(..., description="Task result that was evaluated")
    task_name: str = Field(..., description="Calibration task name")
    qid: str = Field(..., description="Qubit or coupling id of the task result")
    execution_id: str = Field(default="", description="Execution the task result came from")
    status: EvaluationStatus = Field(default="pending")
    requested_at: datetime = Field(default_factory=now)
    started_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)
    error: str | None = Field(default=None, description="Why the evaluation failed, when it did")
    input: EvaluationInputModel | None = Field(default=None)
    output: EvaluationOutputModel | None = Field(default=None)
    evaluator: EvaluatorModel | None = Field(default=None)
    planner: EvaluationPlannerModel | None = Field(
        default=None, description="The planner turn, when the run used planner mode"
    )
    verdict: EvaluationVerdictModel | None = Field(default=None)

    model_config = ConfigDict(from_attributes=True)

    class Settings:
        """Mongo metadata."""

        name = "evaluation"
        indexes: ClassVar = [
            IndexModel(
                [("evaluation_id", ASCENDING)], unique=True, name="evaluation_id_unique_idx"
            ),
            IndexModel([("run_id", ASCENDING), ("qid", ASCENDING)], name="evaluation_run_qid_idx"),
            IndexModel(
                [("project_id", ASCENDING), ("task_id", ASCENDING), ("requested_at", DESCENDING)],
                name="evaluation_task_requested_idx",
            ),
        ]
