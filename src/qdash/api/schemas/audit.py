"""API schemas shared by the agent session and calibration session audits.

Both audits are read-time projections of QDash records into the same event schema, so the
event lives here rather than under either session. The OpenAPI component keeps its
``AgentAuditEvent`` name; ``qdash.api.schemas.agent_session`` re-exports it.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - Pydantic resolves this runtime annotation
from typing import Any, Literal

from pydantic import BaseModel, Field

from qdash.datamodel.agent_session import AgentModelIdentity  # noqa: TC001 - pydantic field

AgentAuditProvenance = Literal[
    "server_record",
    "server_computed",
    "agent_reported",
    "human_reported",
    "evaluator_reported",
    "client_reported",
]
AgentAuditActorKind = Literal["agent", "human", "server", "worker", "unknown"]


class AgentAuditEvent(BaseModel):
    """One entry of a session's experiment audit timeline, built from QDash's own records."""

    event_id: str = Field(description="Stable identifier: <kind>:<source record id>")
    sequence: int = Field(description="Position in the session's full timeline, from 0")
    at: datetime = Field(description="When the event happened, as its source record says")
    state_version: int = Field(
        description=(
            "Session state version the event belongs to: recorded by its source record, or "
            "inherited from its action or commit. Orders events that share a timestamp."
        )
    )
    kind: str = Field(
        description=(
            "session_created, action_proposed, measurement, evaluation, decision, "
            "candidate_commit, candidate_set_commit, backend_apply, intervention_opened, "
            "intervention_response, intervention_resumed, resume_outcome, or "
            "session_stopped; a calibration session's audit adds pipeline_requested, "
            "pipeline_dispatch, agent_session_linked, and session_closed"
        )
    )
    summary: str = Field(description="One readable line about the event")
    actor: str | None = Field(default=None, description="Who acted, when a record names them")
    actor_kind: AgentAuditActorKind = "unknown"
    provenance: AgentAuditProvenance = Field(
        description=(
            "server_record: QDash recorded it; server_computed: derived at read time from "
            "immutable records; agent_reported, human_reported, evaluator_reported: text "
            "that party supplied, recorded as given; client_reported: text a client sent "
            "without saying whether an agent or a person wrote it"
        )
    )
    status: str | None = Field(default=None, description="Status of the source record")
    status_is_current: bool = Field(
        default=False,
        description="Whether status is the source record's live status rather than frozen",
    )
    action_id: str | None = None
    execution_id: str | None = None
    task_id: str | None = None
    task_name: str | None = None
    qid: str | None = None
    commit_id: str | None = None
    evaluation_id: str | None = None
    intervention_id: str | None = None
    decision_id: str | None = None
    pipeline_run_id: str | None = Field(
        default=None,
        description="The calibration session pipeline run the event belongs to, if any",
    )
    agent_session_id: str | None = Field(
        default=None,
        description=(
            "In a calibration session's audit: the agent session an event comes from. Always "
            "null in an agent session's own audit"
        ),
    )
    model: AgentModelIdentity | None = Field(
        default=None,
        description=(
            "The model the client host reported for the record behind an agent event: the "
            "session's creation, an action proposal, a decision, an agent's intervention "
            "request, or a commit made under session authority (the model of the decision it "
            "rests on). Client reported, not verified by QDash; null when none was reported, "
            "and then named in missing"
        ),
    )
    missing: list[str] = Field(
        default_factory=list,
        description="Facts the records do not hold for this event; never filled in",
    )
    data: dict[str, Any] = Field(
        default_factory=dict, description="Kind-specific details; see the developer guide"
    )
