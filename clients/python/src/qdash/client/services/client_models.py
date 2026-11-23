"""Handwritten client models that the generated OpenAPI models do not cover.

``models.py`` is generated from ``docs/oas/openapi.json`` by ``task generate``; never edit it.
This module keeps the client's own representations so the public API stays stable when the
generated schemas change:

- Agent session and evaluation responses that the client validates leniently, with plain
  strings instead of generated enums, so a new server-side value does not break parsing.
- List wrappers for endpoints that return bare JSON arrays.
- Legacy issue models whose endpoints are no longer in the OpenAPI document.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class AgentSessionPolicy(BaseModel):
    """Client representation of an authorized agent session policy."""

    qids: list[str]
    allowed_tasks: list[str]
    allowed_actions: list[str]
    allowed_overrides: dict[str, dict[str, float | None]]
    quality_gates: dict[str, dict[str, float | None]] = Field(default_factory=dict)
    task_quality_gates: dict[str, dict[str, dict[str, float | None]]] = Field(default_factory=dict)
    allow_reconfigure: bool = False
    max_actions: int
    autonomy: str = "confirm_each"
    max_rounds_per_target: int = 3
    evaluation: str | None = None


class AgentSessionResponse(BaseModel):
    """Client representation of a bounded agent session."""

    session_id: str
    project_id: str
    chip_id: str
    created_by: str
    policy: AgentSessionPolicy
    skill_name: str
    skill_version: str
    skill_hash: str
    # The model the creating host reported (client reported, not verified); None when none.
    model: dict[str, str] | None = None
    model_name: str = ""
    status: str
    state_version: int
    action_count: int
    created_at: AwareDatetime
    updated_at: AwareDatetime
    expires_at: AwareDatetime
    active_intervention_id: str | None = None
    calibration_session_id: str | None = None
    calibration_admission: str | None = None


class AgentActionResponse(BaseModel):
    """Client representation of an authorized or rejected agent action."""

    action_id: str
    session_id: str
    idempotency_key: str
    action_type: str
    task_name: str | None
    qids: list[str]
    parameter_overrides: dict[str, float]
    diagnosis: str
    decision: str
    reason: str
    execution_status: str
    operation_id: str | None = None
    execution_id: str | None = None
    state_version_before: int
    state_version_after: int
    created_at: AwareDatetime
    intervention_id: str | None = None


class AgentActionListResponse(BaseModel):
    """Client representation of a session action audit list."""

    items: list[AgentActionResponse]
    total: int


class AgentInterventionResponse(BaseModel):
    """Client representation of a recorded agent intervention.

    Nested records stay plain dictionaries so a new server-side field does not break parsing;
    ``checkpoint`` has the shape ``AgentPlanRunner`` writes and ``resume-plan`` reads.
    """

    intervention_id: str
    project_id: str
    session_id: str
    chip_id: str
    reason: str
    summary: str
    question: str
    status: str
    node_id: str | None = None
    task_name: str | None = None
    qids: list[str] = Field(default_factory=list)
    attempts: list[dict[str, Any]] = Field(default_factory=list)
    action_id: str | None = None
    previous_intervention_id: str | None = None
    checkpoint: dict[str, Any] | None = None
    plan_hash: str = ""
    pauses_session: bool = False
    response: dict[str, Any] | None = None
    resume_claim_key: str | None = None
    resume_outcome: dict[str, Any] | None = None
    notification: dict[str, Any] = Field(default_factory=dict)
    session_status: str = ""
    session_state_version: int = 0
    can_resume: bool = False
    resume_blockers: list[str] = Field(default_factory=list)
    resume_command: str | None = None
    page_path: str = ""
    created_at: AwareDatetime
    updated_at: AwareDatetime


class AgentInterventionListResponse(BaseModel):
    """Client representation of a session's interventions."""

    items: list[AgentInterventionResponse]
    total: int


class CandidateGateResponse(BaseModel):
    """Client representation of a deterministic candidate gate decision."""

    session_id: str
    parameter_name: str
    value: float
    accepted: bool
    reason: str
    minimum: float | None = None
    maximum: float | None = None


class AgentCandidateResponse(BaseModel):
    """Client representation of a server-derived task-result candidate."""

    session_id: str
    action_id: str
    execution_id: str
    task_id: str
    task_name: str
    qid: str
    source_parameter_name: str
    parameter_name: str
    value: float
    error: float = 0.0
    unit: str = ""
    value_type: str = "float"
    quality_metrics: dict[str, float] = Field(default_factory=dict)
    accepted: bool
    reason: str
    minimum: float | None = None
    maximum: float | None = None


class AgentCandidateListResponse(BaseModel):
    """Client representation of action candidates and gate decisions."""

    items: list[AgentCandidateResponse]
    total: int


class AgentCandidateCommitResponse(BaseModel):
    """Client representation of an audited candidate commit."""

    commit_id: str
    session_id: str
    action_id: str
    idempotency_key: str
    execution_id: str
    task_id: str
    task_name: str
    qid: str
    parameter_name: str
    value: float
    status: str
    reason: str
    before_snapshot: dict[str, Any] | None = None
    after_snapshot: dict[str, Any] | None = None
    committed_by: str
    state_version_before: int
    state_version_after: int
    created_at: AwareDatetime
    committed_at: AwareDatetime | None = None
    backend_status: str = "not_started"
    backend_operation_id: str | None = None
    backend_name: str = ""
    backend_target_files: list[str] = Field(default_factory=list)
    backend_changed_files: list[str] = Field(default_factory=list)
    backend_verified: bool = False
    backend_base_git_commit: str | None = None
    backend_git_commit: str | None = None
    backend_error: str = ""
    backend_requested_at: AwareDatetime | None = None
    backend_applied_at: AwareDatetime | None = None


class AgentCandidateSetCommitResponse(BaseModel):
    """Client representation of an audited final candidate-set commit."""

    commit_id: str
    session_id: str
    idempotency_key: str
    chip_id: str
    qid: str
    candidates: list[AgentCandidateResponse]
    status: str
    reason: str
    before_snapshot: dict[str, Any] = Field(default_factory=dict)
    after_snapshot: dict[str, Any] = Field(default_factory=dict)
    committed_by: str
    state_version_before: int
    state_version_after: int
    created_at: AwareDatetime
    committed_at: AwareDatetime | None = None


class TaskNextAction(BaseModel):
    """One autonomous-plan step from a task's knowledge, keyed by evaluation status."""

    model_config = ConfigDict(extra="ignore")

    action: str
    task: str | None = None
    overrides: dict[str, float] = Field(default_factory=dict)
    suggested_range_parameter: str | None = None
    note: str = ""


class EvaluationRunSummary(BaseModel):
    """Client representation of a calibration evaluation run."""

    model_config = ConfigDict(extra="ignore")

    run_id: str
    status: str
    total: int = 0
    completed_count: int = 0
    failed_count: int = 0
    pending_count: int = 0


class CreateEvaluationRunResponse(BaseModel):
    """What a requested evaluation run queued and skipped."""

    model_config = ConfigDict(extra="ignore")

    run: EvaluationRunSummary
    task_ids: list[str] = Field(default_factory=list)
    skipped: dict[str, str] = Field(default_factory=dict)


class EvaluationOutput(BaseModel):
    """The evaluation model's parsed answers."""

    model_config = ConfigDict(extra="ignore")

    model: str | None = None
    diagnosis: dict[str, Any] | None = None


class EvaluationItem(BaseModel):
    """Client representation of one task result's evaluation."""

    model_config = ConfigDict(extra="ignore")

    evaluation_id: str
    run_id: str
    task_id: str
    task_name: str = ""
    qid: str = ""
    status: str
    error: str | None = None
    output: EvaluationOutput | None = None


class EvaluationRunDetailResponse(BaseModel):
    """An evaluation run with its evaluations."""

    model_config = ConfigDict(extra="ignore")

    run: EvaluationRunSummary
    evaluations: list[EvaluationItem] = Field(default_factory=list)


class ListEvaluationsResponse(BaseModel):
    """Evaluations of one task result."""

    model_config = ConfigDict(extra="ignore")

    evaluations: list[EvaluationItem] = Field(default_factory=list)


# Legacy issue models. The issue endpoints are not in the current OpenAPI document.


class IssueResponse(BaseModel):
    """
    Response schema for a single issue.
    """

    id: Annotated[str, Field(title="Id")]
    """
    Issue document ID
    """
    task_id: Annotated[str, Field(title="Task Id")]
    """
    Associated task ID
    """
    user_id: Annotated[str | None, Field(title="User Id")] = None
    """
    Issue author user ID
    """
    username: Annotated[str, Field(title="Username")]
    """
    Issue author username
    """
    avatar_key: Annotated[str | None, Field(title="Avatar Key")] = None
    """
    Issue author avatar preset key
    """
    title: Annotated[str | None, Field(title="Title")] = None
    """
    Issue title
    """
    content: Annotated[str, Field(title="Content")]
    """
    Issue text content
    """
    created_at: Annotated[AwareDatetime, Field(title="Created At")]
    """
    When the issue was created
    """
    updated_at: Annotated[AwareDatetime, Field(title="Updated At")]
    """
    When the issue was last updated
    """
    parent_id: Annotated[str | None, Field(title="Parent Id")] = None
    """
    Parent issue ID for replies
    """
    reply_count: Annotated[int, Field(title="Reply Count")] = 0
    """
    Number of replies to this issue
    """
    is_closed: Annotated[bool, Field(title="Is Closed")] = False
    """
    Whether this thread is closed
    """
    is_ai_reply: Annotated[bool, Field(title="Is Ai Reply")] = False
    """
    Whether this reply was generated by AI
    """


class IssueKnowledgeResponse(BaseModel):
    """
    Response schema for a knowledge case.
    """

    id: Annotated[str, Field(title="Id")]
    """
    Document ID
    """
    issue_id: Annotated[str, Field(title="Issue Id")]
    """
    Source issue ID
    """
    task_id: Annotated[str, Field(title="Task Id")]
    """
    Associated task result ID
    """
    task_name: Annotated[str, Field(title="Task Name")]
    """
    Calibration task class name
    """
    status: Annotated[str, Field(title="Status")]
    """
    Lifecycle status: draft, approved, rejected
    """
    title: Annotated[str, Field(title="Title")]
    """
    Short descriptive title
    """
    date: Annotated[str, Field(title="Date")] = ""
    """
    Date of the incident
    """
    severity: Annotated[str, Field(title="Severity")] = "warning"
    """
    Severity level
    """
    chip_id: Annotated[str, Field(title="Chip Id")] = ""
    """
    Chip identifier
    """
    qid: Annotated[str, Field(title="Qid")] = ""
    """
    Qubit identifier
    """
    resolution_status: Annotated[str, Field(title="Resolution Status")] = "resolved"
    """
    Case outcome
    """
    human_label: Annotated[str, Field(title="Human Label")] = ""
    """
    Human review label
    """
    failure_mode_labels: Annotated[list[str] | None, Field(title="Failure Mode Labels")] = None
    """
    Failure labels
    """
    case_type: Annotated[list[str] | None, Field(title="Case Type")] = None
    """
    Knowledge case type labels
    """
    model_error_type: Annotated[str, Field(title="Model Error Type")] = ""
    """
    Verifier error/outcome type
    """
    resolution_label: Annotated[str, Field(title="Resolution Label")] = ""
    """
    Structured resolution label
    """
    symptom: Annotated[str, Field(title="Symptom")] = ""
    """
    Observed symptom
    """
    model_prediction: Annotated[str, Field(title="Model Prediction")] = ""
    """
    Verifier/model prediction summary
    """
    human_review_decision: Annotated[str, Field(title="Human Review Decision")] = ""
    """
    Human review decision summary
    """
    root_cause: Annotated[str, Field(title="Root Cause")] = ""
    """
    Identified root cause
    """
    resolution: Annotated[str, Field(title="Resolution")] = ""
    """
    How the issue was resolved
    """
    boundary_criteria: Annotated[str, Field(title="Boundary Criteria")] = ""
    """
    Boundary criteria
    """
    lesson_learned: Annotated[list[str] | None, Field(title="Lesson Learned")] = None
    """
    Key takeaways
    """
    applicability: Annotated[str, Field(title="Applicability")] = ""
    """
    When this case should be retrieved
    """
    counterexample: Annotated[str, Field(title="Counterexample")] = ""
    """
    What rule this case counters
    """
    prompt_guidance: Annotated[str, Field(title="Prompt Guidance")] = ""
    """
    Prompt/checklist guidance
    """
    figure_paths: Annotated[list[str] | None, Field(title="Figure Paths")] = None
    """
    Task result figure paths
    """
    thread_image_urls: Annotated[list[str] | None, Field(title="Thread Image Urls")] = None
    """
    Image URLs from issue thread
    """
    reviewed_by_user_id: Annotated[str | None, Field(title="Reviewed By User Id")] = None
    """
    Reviewer user ID
    """
    reviewed_by: Annotated[str | None, Field(title="Reviewed By")] = None
    """
    Reviewer username snapshot
    """
    pr_url: Annotated[str | None, Field(title="Pr Url")] = None
    """
    GitHub PR URL (set on approve)
    """
    created_at: Annotated[AwareDatetime, Field(title="Created At")]
    """
    When the draft was created
    """
    updated_at: Annotated[AwareDatetime, Field(title="Updated At")]
    """
    When the draft was last updated
    """


class ListIssuesResponse(BaseModel):
    """
    Paginated list of issues.
    """

    issues: Annotated[list[IssueResponse], Field(title="Issues")]
    total: Annotated[int, Field(title="Total")]
    skip: Annotated[int, Field(title="Skip")]
    limit: Annotated[int, Field(title="Limit")]


class ListIssueKnowledgeResponse(BaseModel):
    """
    Paginated list of knowledge cases.
    """

    items: Annotated[list[IssueKnowledgeResponse], Field(title="Items")]
    total: Annotated[int, Field(title="Total")]
    skip: Annotated[int, Field(title="Skip")]
    limit: Annotated[int, Field(title="Limit")]
