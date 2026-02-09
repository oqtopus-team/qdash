"""Provenance API response schemas.

This module defines Pydantic models for provenance-related API responses,
including parameter versions, provenance relations, and lineage queries.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TCH003

from pydantic import BaseModel, Field


class ParameterVersionResponse(BaseModel):
    """Response model for a parameter version (entity).

    Attributes
    ----------
    entity_id : str
        Unique identifier for this parameter version
    parameter_name : str
        Name of the parameter
    qid : str
        Qubit or coupling identifier
    value : float | int | str
        The parameter value
    value_type : str
        Type of the value
    unit : str
        Physical unit
    error : float
        Measurement error/uncertainty
    version : int
        Version number
    valid_from : datetime
        When this version became valid
    valid_until : datetime | None
        When this version was superseded
    execution_id : str
        Execution that produced this value
    task_id : str
        Task that produced this value
    task_name : str
        Name of the task
    project_id : str
        Project identifier
    chip_id : str
        Chip identifier

    """

    entity_id: str
    parameter_name: str
    qid: str = ""
    value: float | int | str
    value_type: str = "float"
    unit: str = ""
    error: float = 0.0
    version: int
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    execution_id: str
    task_id: str
    task_name: str = ""
    project_id: str
    chip_id: str = ""


class ProvenanceRelationResponse(BaseModel):
    """Response model for a provenance relation.

    Attributes
    ----------
    relation_id : str
        Unique identifier for this relation
    relation_type : str
        Type of relation (wasGeneratedBy, used, wasDerivedFrom)
    source_type : str
        Type of source node (entity or activity)
    source_id : str
        Identifier of source node
    target_type : str
        Type of target node (entity or activity)
    target_id : str
        Identifier of target node
    created_at : datetime
        When this relation was recorded

    """

    relation_id: str
    relation_type: str
    source_type: str
    source_id: str
    target_type: str
    target_id: str
    created_at: datetime


class ActivityResponse(BaseModel):
    """Response model for an activity (task execution).

    Attributes
    ----------
    activity_id : str
        Unique identifier (execution_id:task_id)
    execution_id : str
        Parent execution ID
    task_id : str
        Task identifier
    task_name : str
        Name of the task
    task_type : str
        Type of task
    qid : str
        Qubit or coupling identifier
    started_at : datetime | None
        When the activity started
    ended_at : datetime | None
        When the activity ended
    status : str
        Execution status
    project_id : str
        Project identifier
    chip_id : str
        Chip identifier

    """

    activity_id: str
    execution_id: str
    task_id: str
    task_name: str
    task_type: str = ""
    qid: str = ""
    started_at: datetime | None = None
    ended_at: datetime | None = None
    status: str = ""
    project_id: str
    chip_id: str = ""


class LineageNodeResponse(BaseModel):
    """Response model for a node in the lineage graph.

    Attributes
    ----------
    node_type : str
        Type of node (entity or activity)
    node_id : str
        Identifier of the node
    depth : int
        Distance from the queried entity (0 = origin)
    entity : ParameterVersionResponse | None
        Entity details if node is an entity
    activity : ActivityResponse | None
        Activity details if node is an activity
    latest_version : int | None
        Current version of the parameter if newer than the node's version

    """

    node_type: str
    node_id: str
    depth: int = 0
    entity: ParameterVersionResponse | None = None
    activity: ActivityResponse | None = None
    latest_version: int | None = None


class LineageEdgeResponse(BaseModel):
    """Response model for an edge in the lineage graph.

    Attributes
    ----------
    relation_type : str
        Type of relation
    source_id : str
        Source node identifier
    target_id : str
        Target node identifier

    """

    relation_type: str
    source_id: str
    target_id: str


class LineageResponse(BaseModel):
    """Response model for lineage query.

    Attributes
    ----------
    origin : LineageNodeResponse
        The queried entity
    nodes : list[LineageNodeResponse]
        All nodes in the lineage graph
    edges : list[LineageEdgeResponse]
        All edges in the lineage graph
    max_depth : int
        Maximum depth traversed

    """

    origin: LineageNodeResponse
    nodes: list[LineageNodeResponse]
    edges: list[LineageEdgeResponse]
    max_depth: int


class ImpactResponse(BaseModel):
    """Response model for impact query.

    Attributes
    ----------
    origin : LineageNodeResponse
        The queried entity
    nodes : list[LineageNodeResponse]
        All nodes affected by this entity
    edges : list[LineageEdgeResponse]
        All edges in the impact graph
    max_depth : int
        Maximum depth traversed

    """

    origin: LineageNodeResponse
    nodes: list[LineageNodeResponse]
    edges: list[LineageEdgeResponse]
    max_depth: int


class ParameterDiffResponse(BaseModel):
    """Response model for parameter difference between executions.

    Attributes
    ----------
    parameter_name : str
        Name of the parameter
    qid : str
        Qubit or coupling identifier
    value_before : float | int | str | None
        Value in the first execution
    value_after : float | int | str | None
        Value in the second execution
    delta : float | None
        Numeric difference if applicable
    delta_percent : float | None
        Percentage change if applicable

    """

    parameter_name: str
    qid: str
    value_before: float | int | str | None = None
    value_after: float | int | str | None = None
    delta: float | None = None
    delta_percent: float | None = None


class ExecutionComparisonResponse(BaseModel):
    """Response model for execution comparison.

    Attributes
    ----------
    execution_id_before : str
        First execution ID
    execution_id_after : str
        Second execution ID
    added_parameters : list[ParameterDiffResponse]
        Parameters added in the second execution
    removed_parameters : list[ParameterDiffResponse]
        Parameters removed in the second execution
    changed_parameters : list[ParameterDiffResponse]
        Parameters with different values
    unchanged_count : int
        Count of unchanged parameters

    """

    execution_id_before: str
    execution_id_after: str
    added_parameters: list[ParameterDiffResponse]
    removed_parameters: list[ParameterDiffResponse]
    changed_parameters: list[ParameterDiffResponse]
    unchanged_count: int


class ParameterHistoryResponse(BaseModel):
    """Response model for parameter version history.

    Attributes
    ----------
    parameter_name : str
        Name of the parameter
    qid : str
        Qubit or coupling identifier
    versions : list[ParameterVersionResponse]
        List of all versions, newest first
    total_versions : int
        Total count of versions

    """

    parameter_name: str
    qid: str
    versions: list[ParameterVersionResponse]
    total_versions: int


class ProvenanceStatsResponse(BaseModel):
    """Response model for provenance statistics.

    Attributes
    ----------
    total_entities : int
        Total number of parameter versions
    total_activities : int
        Total number of activity records
    total_relations : int
        Total number of provenance relations
    relation_counts : dict[str, int]
        Count by relation type
    recent_entities : list[ParameterVersionResponse]
        Most recently created entities

    """

    total_entities: int = Field(..., description="Total parameter versions")
    total_activities: int = Field(..., description="Total activity records")
    total_relations: int = Field(..., description="Total provenance relations")
    relation_counts: dict[str, int] = Field(
        default_factory=dict, description="Count by relation type"
    )
    recent_entities: list[ParameterVersionResponse] = Field(
        default_factory=list, description="Recent entities"
    )


class ParameterChangeResponse(BaseModel):
    """Response model for a parameter change (with delta from previous version).

    Attributes
    ----------
    entity_id : str
        Unique identifier for this parameter version
    parameter_name : str
        Name of the parameter
    qid : str
        Qubit or coupling identifier
    value : float | int | str
        Current value
    previous_value : float | int | str | None
        Previous value (None if first version)
    unit : str
        Physical unit
    delta : float | None
        Numeric difference (value - previous_value)
    delta_percent : float | None
        Percentage change ((value - previous) / previous * 100)
    version : int
        Version number
    valid_from : datetime | None
        When this version became valid
    task_name : str
        Name of the task that produced this value
    execution_id : str
        Execution that produced this value
    error : float
        Measurement error/uncertainty for current value
    previous_error : float | None
        Measurement error/uncertainty for previous value (if available)

    """

    entity_id: str
    parameter_name: str
    qid: str = ""
    value: float | int | str
    previous_value: float | int | str | None = None
    unit: str = ""
    delta: float | None = None
    delta_percent: float | None = None
    version: int
    valid_from: datetime | None = None
    task_name: str = ""
    execution_id: str = ""
    error: float = 0.0
    previous_error: float | None = None


class RecentChangesResponse(BaseModel):
    """Response model for recent parameter changes.

    Attributes
    ----------
    changes : list[ParameterChangeResponse]
        List of recent parameter changes with delta
    total_count : int
        Total number of changes in the time window

    """

    changes: list[ParameterChangeResponse] = Field(
        default_factory=list, description="Recent parameter changes"
    )
    total_count: int = Field(0, description="Total changes in time window")


class ExecutionIdResponse(BaseModel):
    """Response model for a single execution ID with timestamp.

    Attributes
    ----------
    execution_id : str
        The unique execution identifier
    valid_from : datetime | None
        When parameters from this execution were created

    """

    execution_id: str = Field(..., description="Unique execution identifier")
    valid_from: datetime | None = Field(None, description="Latest parameter timestamp")


class RecentExecutionsResponse(BaseModel):
    """Response model for recent execution IDs.

    Attributes
    ----------
    executions : list[ExecutionIdResponse]
        List of recent execution IDs sorted by most recent first

    """

    executions: list[ExecutionIdResponse] = Field(
        default_factory=list, description="Recent execution IDs"
    )


class RecommendedTaskResponse(BaseModel):
    """Response model for a recommended recalibration task.

    Attributes
    ----------
    task_name : str
        Name of the task to re-run
    priority : int
        Priority level (1=highest, larger=lower priority)
    affected_parameters : list[str]
        Parameters that would be recalibrated by this task
    affected_qids : list[str]
        Qubit/coupling IDs affected
    reason : str
        Human-readable explanation

    """

    task_name: str = Field(..., description="Name of the task to re-run")
    priority: int = Field(..., description="Priority (1=highest)")
    affected_parameters: list[str] = Field(default_factory=list, description="Parameters affected")
    affected_qids: list[str] = Field(default_factory=list, description="Qubit IDs affected")
    reason: str = Field("", description="Explanation for recommendation")


class RecalibrationRecommendationResponse(BaseModel):
    """Response model for recalibration recommendations.

    When a parameter changes, this response provides a prioritized list
    of calibration tasks that should be re-run to maintain consistency.

    Attributes
    ----------
    source_entity_id : str
        The changed parameter that triggered recommendations
    source_parameter_name : str
        Name of the changed parameter
    source_qid : str
        Qubit/coupling ID of the changed parameter
    recommended_tasks : list[RecommendedTaskResponse]
        Prioritized list of tasks to re-run
    total_affected_parameters : int
        Total count of downstream parameters affected
    max_depth_reached : int
        Depth of impact graph traversed

    """

    source_entity_id: str = Field(..., description="Changed parameter entity ID")
    source_parameter_name: str = Field("", description="Changed parameter name")
    source_qid: str = Field("", description="Changed parameter QID")
    recommended_tasks: list[RecommendedTaskResponse] = Field(
        default_factory=list, description="Prioritized task recommendations"
    )
    total_affected_parameters: int = Field(0, description="Total downstream parameters affected")
    max_depth_reached: int = Field(0, description="Impact graph depth traversed")


class PolicyViolationResponse(BaseModel):
    """Response model for a policy violation on a current parameter version."""

    entity_id: str
    parameter_name: str
    qid: str = ""
    value: float | int | str
    unit: str = ""
    error: float = 0.0
    valid_from: datetime | None = None
    severity: str = Field(..., description="warn")
    check_type: str = Field(..., description="min|max|staleness_hours|uncertainty_ratio")
    message: str = ""
    warn_threshold: float | None = None
    measured: float | None = None


class PolicyViolationsResponse(BaseModel):
    """Response model for a list of policy violations."""

    violations: list[PolicyViolationResponse] = Field(default_factory=list)
    total_count: int = Field(0, description="Total violations matching query")


class DegradationTrendResponse(BaseModel):
    """Response model for a single degradation trend (consecutive worsening)."""

    parameter_name: str
    qid: str = ""
    evaluation_mode: str = Field(..., description="maximize or minimize")
    streak_count: int = Field(..., description="Consecutive worsening count")
    total_delta: float = Field(..., description="Cumulative change over streak")
    total_delta_percent: float = Field(..., description="Cumulative change in %")
    delta_per_step: float = Field(0.0, description="Average delta per step")
    current_value: float | int | str = 0
    current_entity_id: str = ""
    unit: str = ""
    values: list[float] = Field(
        default_factory=list, description="Recent values (oldest first) for sparkline"
    )
    valid_from: datetime | None = None


class DegradationTrendsResponse(BaseModel):
    """Response model for degradation trends."""

    trends: list[DegradationTrendResponse] = Field(default_factory=list)
    total_count: int = Field(0, description="Total trends matching query")
