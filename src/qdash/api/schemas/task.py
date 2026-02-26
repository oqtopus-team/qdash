"""Schema definitions for task router."""

from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator
from qdash.common.datetime_utils import format_elapsed_time, parse_elapsed_time


class InputParameterModel(BaseModel):
    """Input parameter class."""

    unit: str = ""
    value_type: str = "float"
    value: tuple[int | float, ...] | int | float | None = None
    description: str = ""


class TaskResponse(BaseModel):
    """Response model for a task."""

    name: str
    description: str
    backend: str | None = None
    task_type: str
    input_parameters: dict[str, InputParameterModel]
    output_parameters: dict[str, InputParameterModel]


class ListTaskResponse(BaseModel):
    """Response model for a list of tasks."""

    tasks: list[TaskResponse]


class FailureModeResponse(BaseModel):
    """Response model for a structured failure mode."""

    severity: str
    description: str
    cause: str = ""
    visual: str = ""
    next_action: str = ""


class OutputParameterInfoResponse(BaseModel):
    """Response model for output parameter description."""

    name: str
    description: str


class ExpectedResultResponse(BaseModel):
    """Response model for expected result description."""

    description: str
    result_type: str = ""
    x_axis: str = ""
    y_axis: str = ""
    z_axis: str = ""
    fit_model: str = ""
    typical_range: str = ""
    good_visual: str = ""


class KnowledgeImageResponse(BaseModel):
    """Response model for a task knowledge image reference."""

    alt_text: str
    relative_path: str
    section: str
    base64_data: str = ""


class KnowledgeCaseResponse(BaseModel):
    """Response model for a knowledge case (postmortem)."""

    title: str
    date: str = ""
    severity: str = "warning"
    chip_id: str = ""
    qid: str = ""
    status: str = "resolved"
    symptom: str = ""
    root_cause: str = ""
    resolution: str = ""
    lesson_learned: list[str] = []


class TaskKnowledgeResponse(BaseModel):
    """Response model for task knowledge (LLM-oriented domain knowledge)."""

    name: str
    category: str = ""
    summary: str
    what_it_measures: str
    physical_principle: str
    expected_result: ExpectedResultResponse
    evaluation_criteria: str
    check_questions: list[str] = []
    failure_modes: list[FailureModeResponse]
    tips: list[str]
    output_parameters_info: list[OutputParameterInfoResponse] = []
    analysis_guide: list[str] = []
    prerequisites: list[str] = []
    images: list[KnowledgeImageResponse] = []
    cases: list[KnowledgeCaseResponse] = []
    prompt_text: str


class TaskKnowledgeSummaryResponse(BaseModel):
    """Summary response for list endpoint (no heavy fields)."""

    name: str
    category: str = ""
    summary: str
    failure_mode_count: int = 0
    case_count: int = 0
    image_count: int = 0
    has_analysis_guide: bool = False


class ListTaskKnowledgeResponse(BaseModel):
    """Response model for listing all task knowledge entries."""

    items: list[TaskKnowledgeSummaryResponse]
    categories: dict[str, str] = {}  # slug -> display name


class ReExecutionEntry(BaseModel):
    """A child task result created by re-execution."""

    task_id: str
    task_name: str
    qid: str
    status: str
    start_at: datetime | None = None


class TaskResultResponse(BaseModel):
    """Response model for task result by task_id.

    Attributes
    ----------
        task_id (str): The task ID.
        task_name (str): The name of the task.
        qid (str): The qubit or coupling ID.
        status (str): The task status.
        execution_id (str): The execution ID.
        figure_path (list[str]): List of figure paths.
        json_figure_path (list[str]): List of JSON figure paths.
        input_parameters (dict): Input parameters.
        output_parameters (dict): Output parameters.
        start_at (datetime | None): Start time.
        end_at (datetime | None): End time.
        elapsed_time (timedelta | None): Elapsed time.
        source_task_id (str | None): Parent task ID this was re-executed from.
        re_executions (list[ReExecutionEntry]): Child task results from re-executions.

    """

    task_id: str
    task_name: str
    qid: str
    status: str
    execution_id: str
    flow_name: str = ""
    figure_path: list[str]
    json_figure_path: list[str]
    input_parameters: dict[str, Any]
    output_parameters: dict[str, Any]
    run_parameters: dict[str, Any] = {}
    tags: list[str] = []
    source_task_id: str | None = None
    re_executions: list[ReExecutionEntry] = []
    start_at: datetime | None = None
    end_at: datetime | None = None
    elapsed_time: timedelta | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("elapsed_time", mode="before")
    @classmethod
    def _parse_elapsed_time(cls, v: Any) -> timedelta | None:
        """Parse elapsed_time from various formats."""
        return parse_elapsed_time(v)

    @field_serializer("elapsed_time")
    @classmethod
    def _serialize_elapsed_time(cls, v: timedelta | None) -> str | None:
        """Serialize elapsed_time to H:MM:SS format."""
        return format_elapsed_time(v) if v else None
