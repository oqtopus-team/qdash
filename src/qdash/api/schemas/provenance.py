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
    confidence : float
        Confidence score (1.0 = explicit, < 1.0 = inferred)
    inference_method : str | None
        Method used for inference if applicable
    created_at : datetime
        When this relation was recorded

    """

    relation_id: str
    relation_type: str
    source_type: str
    source_id: str
    target_type: str
    target_id: str
    confidence: float = 1.0
    inference_method: str | None = None
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

    """

    node_type: str
    node_id: str
    depth: int = 0
    entity: ParameterVersionResponse | None = None
    activity: ActivityResponse | None = None


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
    confidence : float
        Confidence score

    """

    relation_type: str
    source_id: str
    target_id: str
    confidence: float = 1.0


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
