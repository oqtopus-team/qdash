"""Provenance service for querying calibration data lineage.

This module provides the ProvenanceService class that handles business logic
for provenance queries, delegating to repositories for data access.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any, cast

from qdash.api.schemas.provenance import (
    ActivityResponse,
    ExecutionComparisonResponse,
    ExecutionIdResponse,
    ImpactResponse,
    LineageEdgeResponse,
    LineageNodeResponse,
    LineageResponse,
    ParameterChangeResponse,
    ParameterDiffResponse,
    ParameterHistoryResponse,
    ParameterVersionResponse,
    ProvenanceStatsResponse,
    RecalibrationRecommendationResponse,
    RecentChangesResponse,
    RecentExecutionsResponse,
    RecommendedTaskResponse,
)

if TYPE_CHECKING:
    from qdash.repository.provenance import (
        MongoActivityRepository,
        MongoParameterVersionRepository,
        MongoProvenanceRelationRepository,
    )

logger = logging.getLogger(__name__)


class ProvenanceService:
    """Service for provenance queries.

    This service provides methods for querying calibration data lineage,
    including ancestor/descendant traversal, execution comparison, and
    parameter history.

    Attributes
    ----------
    parameter_version_repo : MongoParameterVersionRepository
        Repository for parameter versions
    provenance_relation_repo : MongoProvenanceRelationRepository
        Repository for provenance relations
    activity_repo : MongoActivityRepository
        Repository for activities

    """

    def __init__(
        self,
        parameter_version_repo: MongoParameterVersionRepository,
        provenance_relation_repo: MongoProvenanceRelationRepository,
        activity_repo: MongoActivityRepository,
    ) -> None:
        """Initialize ProvenanceService.

        Parameters
        ----------
        parameter_version_repo : MongoParameterVersionRepository
            Repository for parameter versions
        provenance_relation_repo : MongoProvenanceRelationRepository
            Repository for provenance relations
        activity_repo : MongoActivityRepository
            Repository for activities

        """
        self.parameter_version_repo = parameter_version_repo
        self.provenance_relation_repo = provenance_relation_repo
        self.activity_repo = activity_repo

    def get_lineage(
        self,
        project_id: str,
        entity_id: str,
        max_depth: int = 10,
    ) -> LineageResponse:
        """Get the lineage (ancestors) of a parameter version.

        Parameters
        ----------
        project_id : str
            Project identifier
        entity_id : str
            Entity ID to trace lineage from
        max_depth : int
            Maximum depth to traverse

        Returns
        -------
        LineageResponse
            Lineage graph with nodes and edges

        """
        # Use provenance relation repo for graph traversal
        lineage_data = self.provenance_relation_repo.get_lineage(
            project_id=project_id,
            entity_id=entity_id,
            max_depth=max_depth,
        )

        nodes: list[LineageNodeResponse] = []
        edges: list[LineageEdgeResponse] = []

        # Convert nodes from LineageGraph format
        for node_item in lineage_data.get("nodes", []):
            node_dict = dict(node_item)  # Convert TypedDict to regular dict
            node = LineageNodeResponse(
                node_type=str(node_dict.get("type", "entity")),
                node_id=str(node_dict.get("id", "")),
                depth=0,
                entity=self._build_version_from_metadata(node_dict)
                if node_dict.get("type") == "entity"
                else None,
                activity=self._build_activity_from_metadata(node_dict)
                if node_dict.get("type") == "activity"
                else None,
            )
            nodes.append(node)

        # Convert edges
        for edge_item in lineage_data.get("edges", []):
            edge_dict = dict(edge_item)  # Convert TypedDict to regular dict
            edges.append(
                LineageEdgeResponse(
                    relation_type=str(edge_dict.get("relation_type", "")),
                    source_id=str(edge_dict.get("source", "")),
                    target_id=str(edge_dict.get("target", "")),
                )
            )

        # Find or create origin node
        origin = next(
            (n for n in nodes if n.node_id == entity_id),
            LineageNodeResponse(node_type="entity", node_id=entity_id, depth=0),
        )

        return LineageResponse(
            origin=origin,
            nodes=nodes,
            edges=edges,
            max_depth=max_depth,
        )

    def get_impact(
        self,
        project_id: str,
        entity_id: str,
        max_depth: int = 10,
    ) -> ImpactResponse:
        """Get the impact (descendants) of a parameter version.

        Parameters
        ----------
        project_id : str
            Project identifier
        entity_id : str
            Entity ID to trace impact from
        max_depth : int
            Maximum depth to traverse

        Returns
        -------
        ImpactResponse
            Impact graph with affected nodes and edges

        """
        # Use provenance relation repo for graph traversal
        impact_data = self.provenance_relation_repo.get_impact(
            project_id=project_id,
            entity_id=entity_id,
            max_depth=max_depth,
        )

        nodes: list[LineageNodeResponse] = []
        edges: list[LineageEdgeResponse] = []

        # Convert nodes from LineageGraph format
        for node_item in impact_data.get("nodes", []):
            node_dict = dict(node_item)  # Convert TypedDict to regular dict
            node = LineageNodeResponse(
                node_type=str(node_dict.get("type", "entity")),
                node_id=str(node_dict.get("id", "")),
                depth=0,
                entity=self._build_version_from_metadata(node_dict)
                if node_dict.get("type") == "entity"
                else None,
                activity=self._build_activity_from_metadata(node_dict)
                if node_dict.get("type") == "activity"
                else None,
            )
            nodes.append(node)

        # Convert edges
        for edge_item in impact_data.get("edges", []):
            edge_dict = dict(edge_item)  # Convert TypedDict to regular dict
            edges.append(
                LineageEdgeResponse(
                    relation_type=str(edge_dict.get("relation_type", "")),
                    source_id=str(edge_dict.get("source", "")),
                    target_id=str(edge_dict.get("target", "")),
                )
            )

        # Find or create origin node
        origin = next(
            (n for n in nodes if n.node_id == entity_id),
            LineageNodeResponse(node_type="entity", node_id=entity_id, depth=0),
        )

        return ImpactResponse(
            origin=origin,
            nodes=nodes,
            edges=edges,
            max_depth=max_depth,
        )

    def compare_executions(
        self,
        project_id: str,
        execution_id_before: str,
        execution_id_after: str,
    ) -> ExecutionComparisonResponse:
        """Compare parameter values between two executions.

        Parameters
        ----------
        project_id : str
            Project identifier
        execution_id_before : str
            First execution ID
        execution_id_after : str
            Second execution ID

        Returns
        -------
        ExecutionComparisonResponse
            Comparison of parameter values

        """
        # Use provenance relation repo for comparison
        diffs = self.provenance_relation_repo.compare_executions(
            project_id=project_id,
            execution_id_1=execution_id_before,
            execution_id_2=execution_id_after,
        )

        added: list[ParameterDiffResponse] = []
        removed: list[ParameterDiffResponse] = []
        changed: list[ParameterDiffResponse] = []
        unchanged_count = 0

        for diff in diffs:
            change_type = diff.get("change_type", "")
            before_data = diff.get("before")
            after_data = diff.get("after")

            value_before = before_data.get("value") if before_data else None
            value_after = after_data.get("value") if after_data else None

            # Calculate delta for numeric values
            delta = None
            delta_percent = None
            if (
                change_type == "changed"
                and isinstance(value_before, (int, float))
                and isinstance(value_after, (int, float))
            ):
                delta = value_after - value_before
                if value_before != 0:
                    delta_percent = (delta / value_before) * 100

            param_diff = ParameterDiffResponse(
                parameter_name=diff.get("parameter_name", ""),
                qid=diff.get("qid", ""),
                value_before=value_before,
                value_after=value_after,
                delta=delta,
                delta_percent=delta_percent,
            )

            if change_type == "added":
                added.append(param_diff)
            elif change_type == "removed":
                removed.append(param_diff)
            elif change_type == "changed":
                changed.append(param_diff)

        return ExecutionComparisonResponse(
            execution_id_before=execution_id_before,
            execution_id_after=execution_id_after,
            added_parameters=added,
            removed_parameters=removed,
            changed_parameters=changed,
            unchanged_count=unchanged_count,
        )

    def get_parameter_history(
        self,
        project_id: str,
        parameter_name: str,
        qid: str,
        limit: int = 50,
    ) -> ParameterHistoryResponse:
        """Get version history for a parameter.

        Parameters
        ----------
        project_id : str
            Project identifier
        parameter_name : str
            Name of the parameter
        qid : str
            Qubit or coupling identifier
        limit : int
            Maximum number of versions to return

        Returns
        -------
        ParameterHistoryResponse
            List of parameter versions

        """
        versions = self.parameter_version_repo.get_version_history(
            project_id=project_id,
            parameter_name=parameter_name,
            qid=qid,
            limit=limit,
        )

        version_responses = [self._build_version_response(v) for v in versions]

        return ParameterHistoryResponse(
            parameter_name=parameter_name,
            qid=qid,
            versions=version_responses,
            total_versions=len(version_responses),
        )

    def get_stats(self, project_id: str) -> ProvenanceStatsResponse:
        """Get provenance statistics for a project.

        Parameters
        ----------
        project_id : str
            Project identifier

        Returns
        -------
        ProvenanceStatsResponse
            Provenance statistics

        """
        try:
            # Get counts from repositories
            total_entities = self.parameter_version_repo.count(project_id)
            total_activities = self.activity_repo.count(project_id)
            total_relations = self.provenance_relation_repo.count(project_id)
            relation_counts = self.provenance_relation_repo.count_by_type(project_id)

            # Get recent parameter versions (100 to ensure we get multiple unique execution_ids)
            recent_docs = self.parameter_version_repo.get_recent(project_id, limit=100)
            recent_entities = [self._build_version_response(doc) for doc in recent_docs]
        except Exception as e:
            logger.warning(f"Failed to get provenance stats: {e}")
            # Return empty stats if queries fail (e.g., collections don't exist)
            return ProvenanceStatsResponse(
                total_entities=0,
                total_activities=0,
                total_relations=0,
                relation_counts={},
                recent_entities=[],
            )

        return ProvenanceStatsResponse(
            total_entities=total_entities,
            total_activities=total_activities,
            total_relations=total_relations,
            relation_counts=relation_counts,
            recent_entities=recent_entities,
        )

    def get_recent_executions(
        self,
        project_id: str,
        limit: int = 20,
    ) -> RecentExecutionsResponse:
        """Get recent unique execution IDs.

        Uses MongoDB aggregation to efficiently get distinct execution IDs
        without fetching all parameter versions.

        Parameters
        ----------
        project_id : str
            Project identifier
        limit : int
            Maximum number of execution IDs to return

        Returns
        -------
        RecentExecutionsResponse
            List of recent execution IDs

        """
        try:
            execution_data = self.parameter_version_repo.get_recent_execution_ids(
                project_id, limit=limit
            )
            executions = [
                ExecutionIdResponse(
                    execution_id=item.get("execution_id", ""),
                    valid_from=item.get("valid_from"),
                )
                for item in execution_data
                if item.get("execution_id")
            ]
        except Exception as e:
            logger.warning(f"Failed to get recent executions: {e}")
            executions = []

        return RecentExecutionsResponse(executions=executions)

    def get_recent_changes(
        self,
        project_id: str,
        limit: int = 20,
        within_hours: int = 24,
        parameter_names: list[str] | None = None,
    ) -> RecentChangesResponse:
        """Get recent parameter changes with delta from previous versions.

        Parameters
        ----------
        project_id : str
            Project identifier
        limit : int
            Maximum number of changes to return
        within_hours : int
            Time window in hours (default: 24)
        parameter_names : list[str] | None
            Filter by parameter names (e.g., from metrics.yaml config)

        Returns
        -------
        RecentChangesResponse
            Recent changes with delta information

        """
        try:
            # Get recent parameter versions (version > 1 means there was a change)
            # Fetch more if filtering by parameter names
            fetch_limit = limit * 5 if parameter_names else limit * 2
            recent_docs = self.parameter_version_repo.get_recent(project_id, limit=fetch_limit)

            changes: list[ParameterChangeResponse] = []

            for doc in recent_docs:
                if len(changes) >= limit:
                    break

                # Filter by parameter names if specified
                if parameter_names and doc.parameter_name not in parameter_names:
                    continue

                # Skip version 1 (first version has no previous)
                current_version = getattr(doc, "version", 1)
                if current_version <= 1:
                    continue

                # Get previous version
                previous = self.parameter_version_repo.get_version(
                    project_id=project_id,
                    parameter_name=doc.parameter_name,
                    qid=doc.qid,
                    version=current_version - 1,
                )

                current_value = getattr(doc, "value", None)
                previous_value = getattr(previous, "value", None) if previous else None

                # Calculate delta
                delta = None
                delta_percent = None
                if (
                    current_value is not None
                    and previous_value is not None
                    and isinstance(current_value, (int, float))
                    and isinstance(previous_value, (int, float))
                ):
                    delta = float(current_value) - float(previous_value)
                    if previous_value != 0:
                        delta_percent = (delta / float(previous_value)) * 100

                changes.append(
                    ParameterChangeResponse(
                        entity_id=doc.entity_id,
                        parameter_name=doc.parameter_name,
                        qid=doc.qid,
                        value=self._sanitize_value(current_value),
                        previous_value=self._sanitize_value(previous_value)
                        if previous_value is not None
                        else None,
                        unit=getattr(doc, "unit", ""),
                        delta=delta,
                        delta_percent=delta_percent,
                        version=current_version,
                        valid_from=getattr(doc, "valid_from", None),
                        task_name=getattr(doc, "task_name", ""),
                        execution_id=getattr(doc, "execution_id", ""),
                    )
                )

            return RecentChangesResponse(
                changes=changes,
                total_count=len(changes),
            )

        except Exception as e:
            logger.warning(f"Failed to get recent changes: {e}")
            return RecentChangesResponse(changes=[], total_count=0)

    def get_entity(
        self,
        project_id: str,
        entity_id: str,
    ) -> ParameterVersionResponse | None:
        """Get a specific parameter version by entity ID.

        Parameters
        ----------
        project_id : str
            Project identifier
        entity_id : str
            Entity ID

        Returns
        -------
        ParameterVersionResponse | None
            Parameter version or None if not found

        """
        entity = self.parameter_version_repo.get_by_entity_id(entity_id)
        if entity is None:
            return None
        # Verify project_id matches
        if getattr(entity, "project_id", "") != project_id:
            return None
        return self._build_version_response(entity)

    def get_recalibration_recommendations(
        self,
        project_id: str,
        entity_id: str,
        max_depth: int = 10,
    ) -> RecalibrationRecommendationResponse:
        """Get recalibration task recommendations based on impact analysis.

        When a parameter changes, this method analyzes the impact graph
        to recommend which calibration tasks should be re-run to maintain
        consistency across dependent parameters.

        Parameters
        ----------
        project_id : str
            Project identifier
        entity_id : str
            Entity ID of the changed parameter
        max_depth : int
            Maximum depth for impact traversal (default: 10)

        Returns
        -------
        RecalibrationRecommendationResponse
            Prioritized list of recommended tasks

        """
        # Get the source entity info
        source_entity = self.parameter_version_repo.get_by_entity_id(entity_id)
        source_param_name = ""
        source_qid = ""
        if source_entity:
            source_param_name = getattr(source_entity, "parameter_name", "")
            source_qid = getattr(source_entity, "qid", "")

        # Get impact graph
        impact_data = self.provenance_relation_repo.get_impact(
            project_id=project_id,
            entity_id=entity_id,
            max_depth=max_depth,
        )

        # Extract activities and their affected parameters
        # task_name -> {qids: set, parameters: set, min_depth: int}
        task_info: dict[str, dict[str, Any]] = {}
        affected_entity_count = 0

        for node_item in impact_data.get("nodes", []):
            node_dict = dict(node_item)
            node_type = str(node_dict.get("type", ""))
            metadata = cast(dict[str, Any], node_dict.get("metadata") or {})

            if node_type == "activity":
                task_name = str(metadata.get("task_name", ""))
                qid = str(metadata.get("qid", ""))
                if task_name:
                    if task_name not in task_info:
                        task_info[task_name] = {
                            "qids": set(),
                            "parameters": set(),
                            "min_depth": float("inf"),
                        }
                    if qid:
                        task_info[task_name]["qids"].add(qid)

            elif node_type == "entity":
                # Count affected entities (excluding source)
                if str(node_dict.get("id", "")) != entity_id:
                    affected_entity_count += 1

                # Track which parameters each task affects
                param_name = str(metadata.get("parameter_name", ""))
                task_name = str(metadata.get("task_name", ""))
                qid = str(metadata.get("qid", ""))
                if task_name and param_name:
                    if task_name not in task_info:
                        task_info[task_name] = {
                            "qids": set(),
                            "parameters": set(),
                            "min_depth": float("inf"),
                        }
                    task_info[task_name]["parameters"].add(param_name)
                    if qid:
                        task_info[task_name]["qids"].add(qid)

        # Calculate depth for each task based on edge traversal
        # For simplicity, we use the order of appearance (earlier = closer)
        for priority, task_name in enumerate(task_info.keys(), start=1):
            task_info[task_name]["min_depth"] = priority

        # Build recommendations sorted by proximity (min_depth)
        sorted_tasks = sorted(
            task_info.items(),
            key=lambda x: x[1]["min_depth"],
        )

        recommendations = []
        for priority, (task_name, info) in enumerate(sorted_tasks, start=1):
            qids = sorted(info["qids"])
            params = sorted(info["parameters"])

            reason = f"Re-run to update {len(params)} parameter(s)"
            if source_param_name:
                reason += f" affected by {source_param_name} change"

            recommendations.append(
                RecommendedTaskResponse(
                    task_name=task_name,
                    priority=priority,
                    affected_parameters=params,
                    affected_qids=qids,
                    reason=reason,
                )
            )

        return RecalibrationRecommendationResponse(
            source_entity_id=entity_id,
            source_parameter_name=source_param_name,
            source_qid=source_qid,
            recommended_tasks=recommendations,
            total_affected_parameters=affected_entity_count,
            max_depth_reached=max_depth,
        )

    def _build_version_from_metadata(self, item: dict[str, Any]) -> ParameterVersionResponse | None:
        """Build a ParameterVersionResponse from node metadata.

        Parameters
        ----------
        item : dict
            Node data with metadata

        Returns
        -------
        ParameterVersionResponse | None
            Version response or None

        """
        metadata = item.get("metadata", {})
        if not metadata:
            return None

        from qdash.common.datetime_utils import now

        return ParameterVersionResponse(
            entity_id=item.get("id", ""),
            parameter_name=metadata.get("parameter_name", ""),
            qid=metadata.get("qid", ""),
            value=self._sanitize_value(metadata.get("value", 0)),
            value_type="float",
            unit=metadata.get("unit", ""),
            error=0.0,
            version=metadata.get("version", 1),
            valid_from=now(),
            valid_until=None,
            execution_id="",
            task_id="",
            task_name=metadata.get("task_name", ""),
            project_id="",
            chip_id="",
        )

    def _build_activity_from_metadata(self, item: dict[str, Any]) -> ActivityResponse | None:
        """Build an ActivityResponse from node metadata.

        Parameters
        ----------
        item : dict
            Node data with metadata

        Returns
        -------
        ActivityResponse | None
            Activity response or None

        """
        metadata = item.get("metadata", {})
        if not metadata:
            return None

        return ActivityResponse(
            activity_id=item.get("id", ""),
            execution_id="",
            task_id=metadata.get("task_id", ""),
            task_name=metadata.get("task_name", ""),
            task_type="",
            qid=metadata.get("qid", ""),
            started_at=None,
            ended_at=None,
            status=metadata.get("status", ""),
            project_id="",
            chip_id="",
        )

    def _sanitize_value(self, value: Any) -> float | int | str:
        """Sanitize values for JSON serialization.

        Converts inf, -inf, nan to 0.0, and None to 0.

        Parameters
        ----------
        value : Any
            Value to sanitize

        Returns
        -------
        float | int | str
            Sanitized value

        """
        if value is None:
            return 0
        if isinstance(value, float):
            if math.isnan(value):
                return 0.0
            if math.isinf(value):
                return 0.0
            return value
        if isinstance(value, (int, str)):
            return value
        return str(value)

    def _sanitize_error(self, value: Any) -> float:
        """Sanitize error values for JSON serialization.

        Parameters
        ----------
        value : Any
            Value to sanitize

        Returns
        -------
        float
            Sanitized float value

        """
        if value is None:
            return 0.0
        if isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                return 0.0
            return value
        if isinstance(value, int):
            return float(value)
        return 0.0

    def _build_version_response(self, entity: object) -> ParameterVersionResponse:
        """Build a ParameterVersionResponse from an entity.

        Parameters
        ----------
        entity : object
            Entity document or dict

        Returns
        -------
        ParameterVersionResponse
            Version response object

        """
        if isinstance(entity, dict):
            return ParameterVersionResponse(
                entity_id=entity.get("entity_id", ""),
                parameter_name=entity.get("parameter_name", ""),
                qid=entity.get("qid", ""),
                value=self._sanitize_value(entity.get("value", 0)),
                value_type=entity.get("value_type", "float"),
                unit=entity.get("unit", ""),
                error=self._sanitize_error(entity.get("error", 0.0)),
                version=entity.get("version", 1),
                valid_from=entity.get("valid_from"),
                valid_until=entity.get("valid_until"),
                execution_id=entity.get("execution_id", ""),
                task_id=entity.get("task_id", ""),
                task_name=entity.get("task_name", ""),
                project_id=entity.get("project_id", ""),
                chip_id=entity.get("chip_id", ""),
            )
        return ParameterVersionResponse(
            entity_id=getattr(entity, "entity_id", ""),
            parameter_name=getattr(entity, "parameter_name", ""),
            qid=getattr(entity, "qid", ""),
            value=self._sanitize_value(getattr(entity, "value", 0)),
            value_type=getattr(entity, "value_type", "float"),
            unit=getattr(entity, "unit", ""),
            error=self._sanitize_error(getattr(entity, "error", 0.0)),
            version=getattr(entity, "version", 1),
            valid_from=getattr(entity, "valid_from", None),
            valid_until=getattr(entity, "valid_until", None),
            execution_id=getattr(entity, "execution_id", ""),
            task_id=getattr(entity, "task_id", ""),
            task_name=getattr(entity, "task_name", ""),
            project_id=getattr(entity, "project_id", ""),
            chip_id=getattr(entity, "chip_id", ""),
        )

    def _build_activity_response(self, activity: object) -> ActivityResponse:
        """Build an ActivityResponse from an activity.

        Parameters
        ----------
        activity : object
            Activity document or dict

        Returns
        -------
        ActivityResponse
            Activity response object

        """
        if isinstance(activity, dict):
            return ActivityResponse(
                activity_id=activity.get("activity_id", ""),
                execution_id=activity.get("execution_id", ""),
                task_id=activity.get("task_id", ""),
                task_name=activity.get("task_name", ""),
                task_type=activity.get("task_type", ""),
                qid=activity.get("qid", ""),
                started_at=activity.get("started_at"),
                ended_at=activity.get("ended_at"),
                status=activity.get("status", ""),
                project_id=activity.get("project_id", ""),
                chip_id=activity.get("chip_id", ""),
            )
        return ActivityResponse(
            activity_id=getattr(activity, "activity_id", ""),
            execution_id=getattr(activity, "execution_id", ""),
            task_id=getattr(activity, "task_id", ""),
            task_name=getattr(activity, "task_name", ""),
            task_type=getattr(activity, "task_type", ""),
            qid=getattr(activity, "qid", ""),
            started_at=getattr(activity, "started_at", None),
            ended_at=getattr(activity, "ended_at", None),
            status=getattr(activity, "status", ""),
            project_id=getattr(activity, "project_id", ""),
            chip_id=getattr(activity, "chip_id", ""),
        )
