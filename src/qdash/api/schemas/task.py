"""Schema definitions for task router."""

from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from qdash.common.utils.datetime import format_elapsed_time, parse_elapsed_time
from qdash.datamodel.evaluation import EvaluationExampleModel
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
    run_parameter_overrides: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Run parameter values keyed by name. A bare value takes the task's declared "
            "type. A parameter that declares a generated range also takes "
            '{"value": [...], "value_type": ...} with np.linspace, np.logspace, '
            "np.arange, range, or list to run the sweep in another form."
        ),
    )
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
    status: str = Field(
        default="", description="The task's status code the example demonstrates, e.g. SUCCESS"
    )
    suggested_range: str = Field(
        default="", description="The corrective range the example's status calls for"
    )
    parameters: str = Field(
        default="", description="JSON of the values read from the example's plot"
    )
    figures: list[KnowledgeFigureResponse] = []
    diagnosis: str = ""
    label: str = Field(
        default="", description="The demonstration label: outcome, fit quality, verdict, diagnosis"
    )


class NextActionResponse(BaseModel):
    """One autonomous-plan step, keyed by the evaluation status that triggers it."""

    action: str = Field(description="continue, retry, run_task, or request_human")
    task: str | None = Field(default=None, description="The task to run next, for run_task")
    overrides: dict[str, float] = Field(default_factory=dict)
    suggested_range_parameter: str | None = Field(
        default=None,
        description="Input set from the midpoint of the evaluation's suggested range, for retry",
    )
    note: str = ""


class TaskReferenceResponse(BaseModel):
    """The task's reference for the evaluation model, in QCalEval's shape.

    The background goes before every question; the other fields fill the
    family-specific parts of the question templates.
    """

    background: str = Field(
        default="", description="What the experiment does and what a successful result looks like"
    )
    guidance: list[str] = Field(
        default_factory=list, description="Points the significance question asks to explain"
    )
    parameters: dict[str, str] = Field(
        default_factory=dict, description="Extraction schema: parameter name -> JSON type"
    )
    statuses: dict[str, str] = Field(
        default_factory=dict,
        description="Decision criteria: status code -> criterion, SUCCESS first",
    )
    range_format: str | None = Field(
        default=None, description="How a suggested corrective range is written"
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
    next_actions: dict[str, NextActionResponse] = Field(
        default_factory=dict,
        description=(
            "Autonomous-plan step per evaluation status code, from task.md's frontmatter. "
            "A status without an entry stops the plan for human review."
        ),
    )
    reference: TaskReferenceResponse = Field(
        default_factory=TaskReferenceResponse,
        description="The background and question-template parts for the evaluation model",
    )


class EvaluationPromptQuestion(BaseModel):
    """One question's prompt, as the evaluation model would receive it."""

    key: str = Field(description="The question key, e.g. fit_reliability")
    prompt: str = Field(description="The user turn; [figure] marks where an image goes")


class EvaluationPromptPreviewResponse(BaseModel):
    """The prompts an evaluation of a task would send, built without a figure or a model call."""

    task_name: str
    with_examples: bool = Field(
        default=False, description="Whether the task's labeled examples were laid out"
    )
    model: str | None = Field(
        default=None, description="provider/modelId of the model that would judge, when configured"
    )
    questions: list[EvaluationPromptQuestion] = Field(default_factory=list)
    knowledge_chars: int | None = Field(
        default=None, description="Length of the reference the prompts were built from"
    )
    knowledge_sha256: str | None = Field(
        default=None, description="SHA-256 of that reference, to tell two versions apart"
    )
    examples: list[EvaluationExampleModel] = Field(
        default_factory=list, description="The labeled examples fetched for the preview"
    )
    examples_used: int = Field(default=0, description="How many of them the prompts show")

    @classmethod
    def from_runtime(cls, payload: dict[str, Any]) -> "EvaluationPromptPreviewResponse":
        """Build the response from the runtime's preview body."""
        knowledge = payload.get("knowledge")
        if not isinstance(knowledge, dict):
            knowledge = {}
        questions = payload.get("questions")
        examples = payload.get("examples")
        examples_used = payload.get("examples_used")
        return cls(
            task_name=str(payload.get("task_name") or ""),
            with_examples=payload.get("with_examples") is True,
            model=payload.get("model") if isinstance(payload.get("model"), str) else None,
            questions=[
                EvaluationPromptQuestion(
                    key=str(q.get("key") or ""), prompt=str(q.get("prompt") or "")
                )
                for q in (questions if isinstance(questions, list) else [])
                if isinstance(q, dict)
            ],
            knowledge_chars=knowledge.get("chars")
            if isinstance(knowledge.get("chars"), int)
            else None,
            knowledge_sha256=knowledge.get("sha256")
            if isinstance(knowledge.get("sha256"), str)
            else None,
            examples=[
                EvaluationExampleModel.model_validate(e)
                for e in (examples if isinstance(examples, list) else [])
                if isinstance(e, dict)
            ],
            examples_used=examples_used if isinstance(examples_used, int) else 0,
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
