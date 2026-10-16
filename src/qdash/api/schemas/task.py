"""Schema definitions for task router."""

from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from qdash.common.utils.datetime import format_elapsed_time, parse_elapsed_time
from qdash.datamodel.task import TaskResultInputParameter, TaskResultOutputParameter


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


class QuickRunTaskRequest(BaseModel):
    """Request to execute one task directly from the task catalog."""

    chip_id: str
    qid: str
    backend_name: str | None = None
    source_task_id: str | None = Field(
        default=None,
        description="Source result for provenance only; execution uses current task definitions",
    )
    input_parameter_overrides: dict[str, Any] = Field(default_factory=dict)
    run_parameter_overrides: dict[str, Any] = Field(default_factory=dict)
    reconfigure: bool = False
    persist_output_parameters: bool = False
    update_params: bool = False


class KnowledgeFigureResponse(BaseModel):
    """A figure of the knowledge, inlined so the UI can show it without another request."""

    alt: str = ""
    path: str
    base64_data: str = ""
    mime_type: str = ""


class KnowledgeExampleResponse(BaseModel):
    """An expert-labeled example plot of the task."""

    id: str
    title: str
    date: str = ""
    chip: str = ""
    qid: str = ""
    outcome: str
    fit_quality: str = ""
    verdict: str = ""
    source: str = ""
    figures: list[KnowledgeFigureResponse] = []
    diagnosis: str = ""
    label: str = Field(
        default="", description="The demonstration label: outcome, fit quality, verdict, diagnosis"
    )


class TaskKnowledgeResponse(BaseModel):
    """Task knowledge: the background, its figures, labeled examples, and the rendered prompt."""

    name: str
    category: str = Field(default="", description="calibtasks package, e.g. one_qubit_coarse")
    background: str = ""
    figures: list[KnowledgeFigureResponse] = []
    examples: list[KnowledgeExampleResponse] = []
    prompt_text: str = Field(
        description="The background as Markdown, headed by the experiment name"
    )


class TaskKnowledgeSummaryResponse(BaseModel):
    """Summary response for list endpoint (no heavy fields)."""

    name: str
    category: str = ""
    summary: str
    example_count: int = 0
    figure_count: int = 0


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
        user_id (str | None): Internal ID of the user who executed the task.
        username (str): Username snapshot of the user who executed the task.
        figure_path (list[str]): List of figure paths.
        json_figure_path (list[str]): List of JSON figure paths.
        raw_data_path (list[str]): List of raw data artifact paths.
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
    chip_id: str = ""
    status: str
    execution_id: str
    flow_name: str = ""
    user_id: str | None = None
    username: str = ""
    figure_path: list[str]
    json_figure_path: list[str]
    raw_data_path: list[str]
    input_parameters: dict[str, TaskResultInputParameter]
    output_parameters: dict[str, TaskResultOutputParameter]
    output_parameter_names: list[str] = Field(default_factory=list)
    run_parameters: dict[str, Any] = {}
    note: dict[str, Any] = {}
    tags: list[str] = []
    message: str = ""
    stack_trace: str = ""
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
