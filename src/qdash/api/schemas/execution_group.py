"""Schemas of the Execution list grouped by agent session, and of one session's journey.

An agent session is not an execution: it is the policy, budget, and pause authority of one
agent request. Each measurement it dispatched is an ordinary execution with its own status and
task results. These schemas present the two together without merging them: a group row carries
the session's own state and the real executions its actions dispatched, linked through the
session's action records rather than through execution tags.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from qdash.api.schemas.execution import ExecutionAgentSessionLink, ExecutionResponseSummary
from qdash.datamodel.agent_session import AgentSessionStatus

__all__ = ["ExecutionAgentSessionLink"]

ExecutionGroupItemKind = Literal["execution", "agent_session"]


class AgentSessionGroupCounts(BaseModel):
    """What one agent session has done, counted from its own records."""

    actions: int = Field(description="Actions the session counted against its budget")
    max_actions: int = Field(description="The session's action budget")
    measurements: int = Field(
        description="Dispatched measurements linked to a real execution on the session's chip"
    )
    pending_dispatch: int = Field(
        description=(
            "Authorized measurements without an execution yet: not dispatched, being "
            "dispatched, queued, or whose execution record was not found"
        )
    )
    dispatch_failed: int = Field(
        default=0, description="Authorized measurements whose dispatch failed before an execution"
    )
    in_flight: int = Field(
        description=(
            "Measurements being dispatched or queued, or whose execution is scheduled, "
            "running, or cancelling"
        )
    )
    rejected_proposals: int = Field(
        description="Proposals the session policy rejected; they never reached hardware"
    )
    open_interventions: int = Field(description="Requests for an expert not answered yet")
    decisions: int = Field(description="Agent decisions recorded in the session")


class AgentSessionGroupSummary(BaseModel):
    """One agent session as a group of the Execution list.

    ``status`` is the session's own state, not an execution status: a session waiting for an
    expert, or active between measurements, holds no hardware and is not failed for it.
    """

    session_id: str
    project_id: str
    chip_id: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    status: AgentSessionStatus = Field(
        description=(
            "The session's state; an active or paused session past its expiry reads as "
            "expired even before a write records it"
        )
    )
    stored_status: AgentSessionStatus = Field(description="The status the session record holds")
    active_intervention_id: str | None = Field(
        default=None, description="The intervention the session waits on, when paused"
    )
    qids: list[str]
    allowed_tasks: list[str]
    autonomy: str
    skill_name: str = ""
    model_name: str = ""
    counts: AgentSessionGroupCounts
    latest_activity_at: datetime = Field(
        description="The session's latest measurement start, or its creation before the first"
    )
    missing: list[str] = Field(
        default_factory=list,
        description=(
            "Facts the records do not hold, such as a dispatched execution not found, an "
            "execution held by another action, or a record the session has not written yet"
        ),
    )


class AgentSessionChildExecution(BaseModel):
    """A real execution one action of the session dispatched."""

    action_id: str
    sequence: int = Field(description="1-based dispatch order of the measurement in the session")
    attempt: int = Field(
        description="1-based count of measurements of this task on this target so far"
    )
    task_name: str | None = None
    qid: str | None = None
    in_filter: bool = Field(
        description="Whether the execution matches the list's day filter; true without one"
    )
    execution: ExecutionResponseSummary


class ExecutionGroupItem(BaseModel):
    """One row of the grouped Execution list: an execution, or an agent session."""

    kind: ExecutionGroupItemKind
    sort_at: datetime | None = Field(
        default=None,
        description=(
            "Time the row is ordered by: the execution start, or the session's latest "
            "activity within the day filter"
        ),
    )
    execution: ExecutionResponseSummary | None = Field(
        default=None, description="Set for an execution row"
    )
    agent_session: AgentSessionGroupSummary | None = Field(
        default=None, description="Set for an agent session row"
    )
    children: list[AgentSessionChildExecution] = Field(
        default_factory=list,
        description="The session's latest executions in dispatch order; at most children_limit",
    )
    children_total: int = Field(default=0, description="Every execution the session dispatched")
    children_in_filter: int = Field(
        default=0, description="The session's executions that match the day filter"
    )
    children_omitted: int = Field(
        default=0, description="Earlier executions left out of children; the journey lists all"
    )


class ListExecutionGroupsResponse(BaseModel):
    """A page of the Execution list with agent sessions grouped on the server.

    Grouping happens before pagination, so a session is one row on one page with all its
    executions, and no execution appears both in a group and as its own row. ``total`` counts
    rows; ``total_executions`` counts real executions, the number the ungrouped list reports.
    """

    items: list[ExecutionGroupItem]
    total: int = Field(description="Rows: agent sessions plus executions outside a session")
    total_executions: int = Field(
        description="Real executions that match the filter, grouped or not"
    )
    grouped_executions: int = Field(
        description="Executions that match the filter and are shown inside a session row"
    )
    agent_sessions: int = Field(description="Agent session rows that match the filter")
    skip: int
    limit: int
    children_limit: int = Field(description="Most executions one session row lists")


# ---------------------------------------------------------------------- journey

AgentJourneyNodeKind = Literal[
    "measurement", "proposal", "session_action", "decision", "intervention"
]
AgentJourneyEdgeKind = Literal[
    "sequence", "evidence", "next_action", "retry_of", "escalation", "follow_up"
]


class AgentJourneyMeasurement(BaseModel):
    """A measurement the session authorized, and what its real execution reports."""

    action_id: str
    task_name: str | None = None
    qid: str | None = None
    sequence: int | None = Field(
        default=None,
        description="1-based dispatch order among the session's measurements; null before dispatch",
    )
    attempt: int | None = Field(
        default=None,
        description="1-based count of dispatched measurements of this task on this target",
    )
    repeat_of_action_id: str | None = Field(
        default=None, description="The measurement this one repeats, as the agent declared it"
    )
    dispatch_status: str = Field(description="The action's own dispatch state")
    execution_id: str | None = None
    execution_status: str | None = Field(
        default=None, description="The real execution's status; null before it exists"
    )
    task_id: str | None = None
    task_status: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    figure_count: int = 0
    evaluation_id: str | None = Field(default=None, description="The latest evaluation of the task")
    evaluation_status: str | None = None
    intent: str = Field(default="", description="The agent's stated intent; agent reported")


class AgentJourneyProposal(BaseModel):
    """An action that did not reach hardware: rejected by the policy."""

    action_id: str
    action_type: str
    task_name: str | None = None
    qids: list[str] = Field(default_factory=list)
    reason: str = Field(default="", description="Why the policy rejected it")
    intent: str = Field(default="", description="The agent's stated intent; agent reported")


class AgentJourneySessionAction(BaseModel):
    """An authorized action other than a measurement: asking for an expert, or completing."""

    action_id: str
    action_type: str
    reason: str = ""


class AgentJourneyDecision(BaseModel):
    """The agent's reading of earlier results and the step it chose; agent reported."""

    decision_id: str
    assessment: str | None = None
    interpretation: str
    next_action: str
    next_detail: str = ""
    evidence_action_ids: list[str] = Field(default_factory=list)
    evaluation_ids: list[str] = Field(default_factory=list)
    next_action_id: str | None = None
    superseded_by_decision_id: str | None = None
    supersedes_decision_id: str | None = None


class AgentJourneyIntervention(BaseModel):
    """A stop for an expert and the expert's answer."""

    intervention_id: str
    reason: str
    status: str
    question: str
    summary: str = ""
    pauses_session: bool = False
    response_decision: str | None = None
    response_guidance: str = ""
    responded_by: str | None = None
    responded_at: datetime | None = None
    resumed_at: datetime | None = None
    resume_outcome: str | None = None


class AgentJourneyNode(BaseModel):
    """One step of the journey. Exactly the field named by ``kind`` is set."""

    node_id: str = Field(description="Stable id: the kind and the id of its record")
    kind: AgentJourneyNodeKind
    order: int = Field(description="0-based position in time among all nodes of the journey")
    at: datetime
    label: str
    status: str = Field(
        description=(
            "Measurement: the execution status, or the dispatch state before one exists; "
            "link_claimed or link_ambiguous when the action was dispatched but no execution "
            "can be attributed to it. Proposal: rejected. Decision: recorded or superseded. "
            "Intervention: its status"
        )
    )
    status_is_current: bool = Field(
        default=False, description="The status is read live from a record that can still change"
    )
    missing: list[str] = Field(
        default_factory=list,
        description=(
            "Facts the records do not hold, such as execution, execution_on_session_chip, "
            "execution_link_claimed, execution_link_ambiguous, task_result, or action_record "
            "(shown from the session's pending payload, not written yet)"
        ),
    )
    measurement: AgentJourneyMeasurement | None = None
    proposal: AgentJourneyProposal | None = None
    session_action: AgentJourneySessionAction | None = None
    decision: AgentJourneyDecision | None = None
    intervention: AgentJourneyIntervention | None = None


class AgentJourneyEdge(BaseModel):
    """A typed link between two nodes.

    ``sequence`` is temporal only: the next measurement dispatched. Every other kind comes from
    an explicit reference in a record (a decision's evidence or next action, a declared repeat,
    an intervention's action or predecessor); no scientific dependency is inferred from time.
    """

    edge_id: str
    kind: AgentJourneyEdgeKind
    source: str
    target: str


class AgentSessionJourneyResponse(BaseModel):
    """One agent session as an experiment journey over its real executions.

    A live read of the session's records, collected one after another: statuses can move while
    it is read, and it is not a snapshot. The full audit, with its consistency check and export,
    stays on the session's audit endpoints.
    """

    generated_at: datetime
    session: AgentSessionGroupSummary
    nodes: list[AgentJourneyNode]
    edges: list[AgentJourneyEdge]
    total_nodes: int
    omitted_nodes: int = Field(
        description="Earliest nodes left out to bound the response; the audit holds them all"
    )
    complete: bool
    notes: list[str]
