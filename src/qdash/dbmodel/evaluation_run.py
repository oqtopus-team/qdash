"""Document model for one bulk calibration evaluation run."""

from datetime import datetime
from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from qdash.common.utils.datetime import now
from qdash.datamodel.evaluation import (
    EvaluationMode,
    EvaluationRunStatus,
    EvaluationTrigger,
    EvaluatorModel,
)


class EvaluationRunDocument(Document):
    """One request to evaluate the latest result of a task across a chip.

    The run is the unit of comparison: the same selection evaluated again
    after a change to the evaluation model, the extension or the task's
    reference yields a second run with the same shape.
    """

    run_id: str = Field(..., description="Run identifier (evr_<hex>)")
    project_id: str = Field(..., description="Owning project identifier")
    chip_id: str = Field(..., description="Chip the task results belong to")
    task_name: str = Field(..., description="Calibration task that was evaluated")
    entity_type: str = Field(..., description='"qubit" or "coupling"')
    date: str | None = Field(
        default=None, description="YYYYMMDD when a historical day was evaluated; None for latest"
    )
    question: str | None = Field(
        default=None, description="Specific question asked on top of the standard diagnosis"
    )
    trigger: EvaluationTrigger = Field(default="bulk")
    mode: EvaluationMode = Field(default="direct")
    with_examples: bool = Field(
        default=False, description="Labeled examples were shown before each figure"
    )
    planner_model: str | None = Field(
        default=None, description="provider/modelId of the planner, in planner mode"
    )
    requested_by: str = Field(..., description="Username that requested the run")
    requested_at: datetime = Field(default_factory=now)
    completed_at: datetime | None = Field(default=None)
    status: EvaluationRunStatus = Field(default="running")
    total: int = Field(default=0, description="Evaluations in the run")
    completed_count: int = Field(default=0)
    failed_count: int = Field(default=0)
    model: str | None = Field(default=None, description="provider/modelId of the first evaluation")
    evaluator: EvaluatorModel | None = Field(
        default=None, description="Extension that produced the first evaluation"
    )

    model_config = ConfigDict(from_attributes=True)

    class Settings:
        """Mongo metadata."""

        name = "evaluation_run"
        indexes: ClassVar = [
            IndexModel([("run_id", ASCENDING)], unique=True, name="evaluation_run_id_unique_idx"),
            IndexModel(
                [("project_id", ASCENDING), ("chip_id", ASCENDING), ("requested_at", DESCENDING)],
                name="evaluation_run_chip_requested_idx",
            ),
        ]
